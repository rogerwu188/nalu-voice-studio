"""User-confirmed image estimates share the episode's video budget envelope."""

import json

from pydantic import BaseModel, ConfigDict, Field

from .asset_service import AssetService
from .image_preparation import ImagePreparationRequest, ImagePreparationService
from .image_submission import ImageSubmissionService
from .repository import ConflictError, Repository, encode, new_id, utc_now
from .video_preparation import digest


class ImageBudgetApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preparation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimated_credits: int = Field(strict=True, gt=0)
    confirmed_run_budget_credits: int = Field(strict=True, gt=0)
    approved_by: str = Field(min_length=1, max_length=160, pattern=r"\S")
    confirmation: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    guardian_approval: bool = False


class ImageBudgetService:
    def __init__(self, repository: Repository, assets: AssetService):
        self.repository, self.assets = repository, assets

    def reserve(self, run_id: str, preparation_id: str, approval: ImageBudgetApproval):
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            ImageSubmissionService(self.repository)._eligible(run_id)
            run = self.repository.get_run(run_id)
            project = self.repository.get_project(run.project_id)
            if project.audience_mode == "child" and not approval.guardian_approval:
                raise ConflictError("child image spending requires guardian approval")
            if run.estimated_budget_credits != approval.confirmed_run_budget_credits:
                raise ConflictError("run budget changed; review again")
            source = self.repository.get_run_event(preparation_id)
            saved = source.payload
            if (source.run_id != run_id or source.event_type != "image_task_prepared"
                    or saved.get("record_sha256") != digest({k: v for k, v in saved.items() if k != "record_sha256"})):
                raise ConflictError("image estimate requires an intact saved preparation")
            incoming = ImagePreparationRequest.model_validate({key: saved.get(key) for key in ImagePreparationRequest.model_fields})
            prepared, _ = ImagePreparationService(self.repository, self.assets).materialize(run_id, incoming)
            if (prepared["preparation_sha256"] != approval.preparation_sha256
                    or prepared != {k: v for k, v in saved.items() if k != "record_sha256"}):
                raise ConflictError("image inputs changed; prepare and review again")
            task_key = prepared["image_task_key"]
            rows = db.execute("SELECT * FROM run_events WHERE run_id=? AND event_type IN "
                              "('video_estimate_reserved','image_estimate_reserved')", (run_id,)).fetchall()
            reservations = [(row, json.loads(row["payload_json"])) for row in rows]
            for _, record in reservations:
                if (record.get("run_id") != run_id
                        or record.get("reservation_sha256") != digest({k: v for k, v in record.items() if k != "reservation_sha256"})
                        or type(record.get("estimated_credits")) is not int or record["estimated_credits"] <= 0):
                    raise ConflictError("existing production estimates require reconciliation")
            keys = {record["task_key"] for _, record in reservations}
            if len(keys) != len(reservations):
                raise ConflictError("duplicate production estimates require reconciliation")
            reserved_total = sum(record["estimated_credits"] for _, record in reservations)
            if reserved_total > approval.confirmed_run_budget_credits:
                raise ConflictError("existing production estimates exceed the current run budget")
            prior = next(((row, record) for row, record in reservations if record["task_key"] == task_key), None)
            if prior:
                if (prior[0]["event_type"] != "image_estimate_reserved" or prior[1]["preparation_id"] != preparation_id
                        or prior[1]["preparation_sha256"] != approval.preparation_sha256
                        or prior[1]["estimated_credits"] != approval.estimated_credits):
                    raise ConflictError("image already reserves different inputs or cost; reconcile first")
                return self.repository.get_run_event(prior[0]["id"])
            if ImageSubmissionService(self.repository)._latest(db, run_id, task_key):
                raise ConflictError("image already submitted without this reservation; reconcile cost first")
            total = reserved_total + approval.estimated_credits
            if total > approval.confirmed_run_budget_credits:
                raise ConflictError("combined image and video estimates exceed the run budget")
            record = {**approval.model_dump(), "run_id": run_id, "preparation_id": preparation_id,
                      "task_key": task_key, "request_sha256": prepared["request_sha256"],
                      "production_package_sha256": prepared["production_package_sha256"],
                      "total_reserved_estimate_credits": total, "provider_price_verified": False,
                      "provider_charge_cap_guaranteed": False, "generation_performed": False,
                      "upstream_image_contract_verified": False}
            record["reservation_sha256"] = digest(record)
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)",
                       (event_id, run_id, sequence, "image_estimate_reserved", None, None,
                        "Image estimate reserved; no generation or upstream contract approval.", encode(record), utc_now()))
        return self.repository.get_run_event(event_id)
