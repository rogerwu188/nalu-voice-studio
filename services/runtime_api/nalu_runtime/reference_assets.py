"""Register a reviewed generated reference; never imply likeness or production QA."""

import fcntl
import hashlib
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .image_materialization import ImageMaterializationService
from .image_preparation import ImagePreparationRequest, ImagePreparationService
from .models import AssetKind, ConsentScope
from .repository import ConflictError
from .secure_files import secure_directory
from .video_preparation import digest


class ReferenceAssetConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    consent_granted: Literal[True]
    confirmed_by: str = Field(min_length=1, max_length=160)
    statement: str = Field(min_length=1, max_length=2000)
    guardian_approved: bool = False


def validate_registered_reference(repository, asset):
    """Recheck a generated asset when reused, including in a later episode."""
    source = asset.metadata.get("generation_provenance")
    if source is None:
        return
    if (not isinstance(source, dict) or source.get("schema") != "nalu.generated-reference/v1" or not asset.consent_granted
            or any(not isinstance(source.get(key), str) or not source[key] for key in ("run_id", "review_id", "registration_id"))
            or source.get("image_sha256") != asset.metadata.get("sha256")):
        raise ConflictError("generated reference provenance or permission is invalid")
    run = repository.get_run(source["run_id"])
    if run.project_id != asset.project_id:
        raise ConflictError("generated reference belongs to another project")
    events = repository.list_run_events(run.id)
    registrations = [e for e in events if e.event_type == "reference_asset_registered"
                     and e.payload.get("registration_id") == source["registration_id"]]
    if len(registrations) != 1 or registrations[0].payload != {**source, "asset_id": asset.id}:
        raise ConflictError("generated reference registration is incomplete; reconcile before reuse")
    review = repository.get_run_event(source["review_id"])
    latest = [e for e in events if e.event_type == "image_frame_reviewed"
              and e.payload.get("task_key") == review.payload.get("task_key")]
    if (review.run_id != run.id or not latest or latest[-1].id != review.id
            or review.payload.get("decision") != "accept"
            or review.payload.get("image_sha256") != source["image_sha256"]
            or review.payload.get("review_sha256") != digest({k: v for k, v in review.payload.items() if k != "review_sha256"})):
        raise ConflictError("generated reference approval changed; review before reuse")


class ReferenceAssetService:
    def __init__(self, repository, assets, data_root):
        self.repository, self.assets, self.data_root = repository, assets, data_root

    def _source(self, run_id, review_id):
        repo = self.repository
        run = repo.get_run(run_id)
        review = repo.get_run_event(review_id)
        value = review.payload
        if (review.run_id != run_id or review.event_type != "image_frame_reviewed"
                or value.get("decision") != "accept" or value.get("user_approved") is not True
                or value.get("review_sha256") != digest({k: v for k, v in value.items() if k != "review_sha256"})):
            raise ConflictError("registration requires an intact accepted reference review")
        reviews = [e for e in repo.list_run_events(run_id) if e.event_type == "image_frame_reviewed"
                   and e.payload.get("task_key") == value["task_key"]]
        if not reviews or reviews[-1].id != review_id:
            raise ConflictError("reference review changed; confirm the current image")
        prepared = repo.get_run_event(value["preparation_id"])
        saved = prepared.payload
        if (prepared.run_id != run_id or prepared.event_type != "image_task_prepared"
                or saved.get("purpose") != "visual_reference"
                or saved.get("record_sha256") != digest({k: v for k, v in saved.items() if k != "record_sha256"})):
            raise ConflictError("only a reference design may become a reusable reference asset")
        incoming = ImagePreparationRequest.model_validate({k: saved[k] for k in ImagePreparationRequest.model_fields if k in saved})
        current, _ = ImagePreparationService(repo, self.assets).materialize(run_id, incoming)
        materialized, raw = ImageMaterializationService(repo, self.data_root).read_saved(run_id, value["materialization_id"])
        image = materialized.payload
        if (current != {k: v for k, v in saved.items() if k != "record_sha256"}
                or value["preparation_sha256"] != current["preparation_sha256"]
                or image["materialization_sha256"] != value["materialization_sha256"]
                or image["image"]["sha256"] != value["image_sha256"]
                or image["request_sha256"] != current["request_sha256"]
                or image["task_key"] != current["image_task_key"]):
            raise ConflictError("reference result no longer matches its reviewed design")
        return run, current, image, raw

    def register(self, run_id, review_id, confirmation):
        # Cross-process, nonblocking serialization, without holding a SQLite
        # transaction across the existing recoverable asset importer.
        identity = digest({"run_id": run_id, "review_id": review_id})
        directory = self.data_root / "reference-registration-locks"
        secure_directory(directory)
        descriptor = os.open(directory / f"{identity}.lock",
                             os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ConflictError("reference registration is already in progress; reload before continuing") from None
            run, prepared, image, raw = self._source(run_id, review_id)
            project = self.repository.get_project(run.project_id)
            if project.audience_mode == "child" and not confirmation.guardian_approved:
                raise ConflictError("child reference registration requires guardian confirmation")
            provenance = {"schema": "nalu.generated-reference/v1", "registration_id": identity,
                "run_id": run_id, "review_id": review_id, "visual_asset_key": prepared["visual_asset_key"],
                "design_sha256": prepared["design_sha256"], "approved_plan_event_id": prepared["approved_plan_event_id"],
                "preparation_sha256": prepared["preparation_sha256"], "materialization_sha256": image["materialization_sha256"],
                "image_sha256": image["image"]["sha256"], "confirmation_sha256": digest(confirmation.model_dump()),
                "authentic_historical_photo": False, "identity_qa_verified": False}
            matches = [a for a in self.repository.list_assets(run.project_id)
                       if isinstance(a.metadata.get("generation_provenance"), dict)
                       and a.metadata["generation_provenance"].get("registration_id") == identity]
            if len(matches) > 1:
                raise ConflictError("duplicate reference assets require reconciliation")
            if matches:
                asset = matches[0]
                path = self.assets.managed_path(run.project_id, asset.local_uri)
                if (asset.metadata.get("generation_provenance") != provenance or not asset.consent_granted
                        or asset.kind != prepared["design"]["kind"] or asset.season_id is not None or asset.episode_id is not None
                        or asset.metadata.get("sha256") != image["image"]["sha256"]
                        or not path.is_file() or path.stat().st_size != len(raw)
                        or hashlib.sha256(path.read_bytes()).hexdigest() != image["image"]["sha256"]):
                    raise ConflictError("registered reference or its permission changed; do not duplicate it")
            else:
                design = prepared["design"]
                extension = image["image"]["extension"]
                asset = self.assets.import_bytes(run.project_id, content=raw, filename=f"reference.{extension}",
                    content_type="image/png" if extension == "png" else "image/jpeg", kind=AssetKind(design["kind"]),
                    name=design["name"], subject_name=design["name"], season_id=None, episode_id=None,
                    consent_granted=True, consent_scope=ConsentScope.PROJECT_ONLY,
                    guardian_approved=confirmation.guardian_approved, consent_granted_by=confirmation.confirmed_by,
                    consent_statement=confirmation.statement, generation_provenance=provenance)
            # A changed review during disk/DB work cannot produce an active binding.
            self._source(run_id, review_id)
            self.repository.bind_run_assets(run_id, [asset])
            self.repository.append_run_event_once(run_id, "reference_asset_registered", dedupe_key="registration_id",
                dedupe_value=identity, message="Reviewed generated reference registered for this project; no identity QA claimed.",
                payload={**provenance, "asset_id": asset.id})
            return asset
        finally:
            os.close(descriptor)
