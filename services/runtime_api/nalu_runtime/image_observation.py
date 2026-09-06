"""Read-only provider queries for durably accepted image tasks."""

from dataclasses import asdict

from .giggle_task_query import GiggleTaskQuery
from .image_submission import ImageSubmissionService
from .repository import ConflictError, Repository
from .video_preparation import digest


class ImageObservationService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def _binding(self, run_id: str, submission_id: str):
        run = self.repository.get_run(run_id)
        if self.repository.get_project(run.project_id).archived_at:
            raise ConflictError("archived project is read-only")
        event = self.repository.get_run_event(submission_id)
        record = event.payload
        if (event.run_id != run_id or event.event_type != "image_task_submitted"
                or record.get("state") != "submitted" or not record.get("provider_task_id")):
            raise ConflictError("image query requires a saved accepted image task from this run")
        with self.repository.db.connect() as db:
            current = ImageSubmissionService(self.repository)._latest(db, run_id, record.get("task_key"))
        receipt = record.get("receipt", {})
        if (not current or current[0]["id"] != submission_id
                or receipt.get("provider_task_id") != record["provider_task_id"]
                or receipt.get("request_sha256") != record.get("request_sha256")
                or receipt.get("endpoint") != record.get("endpoint")):
            raise ConflictError("image task receipt requires reconciliation")
        return event

    def refresh(self, run_id: str, submission_id: str, query: GiggleTaskQuery):
        binding = self._binding(run_id, submission_id)
        observed = query.query(binding.payload["provider_task_id"])
        if observed.task_id != binding.payload["provider_task_id"] or observed.billing_verified:
            raise ConflictError("image observation identity or billing mismatch")
        if self._binding(run_id, submission_id).payload != binding.payload:
            raise ConflictError("image receipt changed during query")
        payload = {**asdict(observed), "run_id": run_id, "submission_id": submission_id,
                   "task_key": binding.payload["task_key"], "request_sha256": binding.payload["request_sha256"],
                   "generation_performed": False, "image_downloaded": False,
                   "visual_semantics_verified": False, "master_accepted": False}
        payload["observation_sha256"] = digest(payload)
        return self.repository.append_run_event_once(
            run_id, "image_task_observed", dedupe_key="observation_sha256",
            dedupe_value=payload["observation_sha256"],
            message="Image provider status observed; download, visual review and billing remain separate.",
            payload=payload,
        )
