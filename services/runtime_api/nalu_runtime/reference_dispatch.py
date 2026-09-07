"""Reference-specific source and spending checks for single-attempt submission.

References follow the pinned asset factory, not the shot/keyframe contract.
The price verifier must be runtime-owned and validate an applicable saved quote;
no HTTP request can supply it and there is no permissive default.
"""

import json
from collections.abc import Callable

import httpx

from .asset_service import AssetService
from .image_budget import ImageBudgetApproval, ImageBudgetService
from .image_preparation import ImagePreparationRequest, ImagePreparationService
from .image_submission import ImageSubmissionService
from .repository import ConflictError, Repository
from .video_preparation import digest


class ReferenceDispatchService:
    def __init__(self, repository: Repository, assets: AssetService):
        self.repository, self.assets = repository, assets

    def dispatch(self, run_id: str, reservation_id: str, *, secret: Callable[[], str],
                 verify_price: Callable[[str, dict, dict], None],
                 transport: httpx.BaseTransport | None = None):
        """No generic image or video approval can substitute for a reference.

        Pricing is intentionally still a required trusted dependency. Until its
        production implementation exists this service is not exposed as an API.
        Synthetic tests must not be described as activated paid generation.
        """
        event = self.repository.get_run_event(reservation_id)
        reservation = event.payload
        if (event.run_id != run_id or event.event_type != "image_estimate_reserved"
                or reservation.get("run_id") != run_id
                or reservation.get("reservation_sha256") != digest({k: v for k, v in reservation.items()
                    if k != "reservation_sha256"})):
            raise ConflictError("reference dispatch requires an intact image reservation")
        source = self.repository.get_run_event(reservation["preparation_id"])
        saved = source.payload
        if (source.run_id != run_id or source.event_type != "image_task_prepared"
                or saved.get("purpose") != "visual_reference"
                or saved.get("record_sha256") != digest({k: v for k, v in saved.items() if k != "record_sha256"})
                or saved.get("preparation_sha256") != reservation.get("preparation_sha256")
                or saved.get("request_sha256") != reservation.get("request_sha256")
                or saved.get("image_task_key") != reservation.get("task_key")):
            raise ConflictError("reference reservation does not bind its preparation")
        # Replay a prior outcome without price/credential access, including an
        # uncertain attempt. Never recompile it into a replacement request.
        submitter = ImageSubmissionService(self.repository)
        with self.repository.db.connect() as db:
            existing = submitter._latest(db, run_id, reservation["task_key"])
            if existing:
                if existing[1]["request_sha256"] != reservation["request_sha256"]:
                    raise ConflictError("reference attempt differs from this reservation")
                return self.repository.get_run_event(existing[0]["id"])
        incoming = ImagePreparationRequest.model_validate({k: saved[k] for k in ImagePreparationRequest.model_fields
                                                           if k in saved})
        approval = ImageBudgetApproval.model_validate({k: reservation[k] for k in ImageBudgetApproval.model_fields
                                                      if k in reservation})

        def authorize(actual_run, task_key, request_sha):
            if (actual_run != run_id or task_key != reservation["task_key"]
                    or request_sha != reservation["request_sha256"]):
                raise ConflictError("reference transport changed after spending review")
            submitter._eligible(run_id)
            run = self.repository.get_run(run_id)
            project = self.repository.get_project(run.project_id)
            if (run.estimated_budget_credits != approval.confirmed_run_budget_credits
                    or (project.audience_mode == "child" and not approval.guardian_approval)):
                raise ConflictError("reference budget or guardian approval changed")
            # Read-only: this callback also runs inside the submitter's SQLite
            # intent transaction, so it must not start a nested write transaction.
            with self.repository.db.connect() as db:
                rows = db.execute("SELECT payload_json FROM run_events WHERE run_id=? AND event_type IN "
                                  "('image_estimate_reserved','video_estimate_reserved')", (run_id,)).fetchall()
            records = [json.loads(row["payload_json"]) for row in rows]
            if (any(record.get("run_id") != run_id
                    or record.get("reservation_sha256") != digest({k: v for k, v in record.items() if k != "reservation_sha256"})
                    or type(record.get("estimated_credits")) is not int or record["estimated_credits"] <= 0
                    for record in records)
                    or len({record.get("task_key") for record in records}) != len(records)
                    or sum(record["estimated_credits"] for record in records) > approval.confirmed_run_budget_credits
                    or reservation not in records):
                raise ConflictError("shared production budget requires reconciliation")
            current, _ = ImagePreparationService(self.repository, self.assets).materialize(run_id, incoming)
            if current != {k: v for k, v in saved.items() if k != "record_sha256"}:
                raise ConflictError("reference design changed after spending review")
            verify_price(run_id, reservation, current)

        # Validate before reading a secret or persisting a provider intent. The
        # submitter repeats these checks immediately before its single POST.
        ImageBudgetService(self.repository, self.assets).reserve(run_id, source.id, approval)
        authorize(run_id, reservation["task_key"], reservation["request_sha256"])
        _, request = ImagePreparationService(self.repository, self.assets).materialize(run_id, incoming)
        return submitter.submit(run_id, reservation["task_key"], request, secret=secret,
                                authorize=authorize, transport=transport)
