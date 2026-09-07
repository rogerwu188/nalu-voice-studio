"""Advance an accepted image task to local review without ever generating again."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .giggle_task_query import GiggleTaskQuery
from .image_materialization import ImageMaterializationService
from .image_observation import ImageObservationService
from .repository import ConflictError, Repository
from .video_preparation import digest


class ImageProgressResult(BaseModel):
    run_id: str
    submission_id: str
    observation_id: str
    phase: Literal["waiting", "provider_failed", "ready_for_review"]
    materialization_id: str | None = None
    generation_performed: Literal[False] = False
    visual_semantics_verified: Literal[False] = False
    billing_verified: Literal[False] = False


class ImageProgressService:
    def __init__(self, repository: Repository, data_root: Path):
        self.repository, self.data_root = repository, data_root

    def advance(self, run_id: str, submission_id: str, query: GiggleTaskQuery):
        """One explicit polling step, with restart reuse of terminal observations.

        No submitter, provider POST, new task identity or automatic polling loop.
        A failed download leaves the completed observation durable for resumption.
        The result exposes local IDs, not provider result URLs or credentials.
        """
        observer = ImageObservationService(self.repository)
        binding = observer._binding(run_id, submission_id)
        run = self.repository.get_run(run_id)
        if run.status == "cancelled":
            raise ConflictError("cancelled run cannot advance media production; read-only status queries remain available")
        observation = None
        for event in self.repository.list_run_events(run_id):
            if event.event_type != "image_task_observed" or event.payload.get("submission_id") != submission_id:
                continue
            record = event.payload
            if (record.get("run_id") != run_id or record.get("task_id") != binding.payload["provider_task_id"]
                    or record.get("request_sha256") != binding.payload["request_sha256"]
                    or record.get("task_key") != binding.payload["task_key"]
                    or record.get("status") not in {"pending", "processing", "completed", "failed", "error"}
                    or record.get("billing_verified") is not False
                    or record.get("observation_sha256") != digest({k: v for k, v in record.items() if k != "observation_sha256"})):
                raise ConflictError("saved image progress requires reconciliation")
            observation = event
        if observation is None or observation.payload["status"] not in {"completed", "failed", "error"}:
            observation = observer.refresh(run_id, submission_id, query)
        # Cancellation or archival during the GET must not turn into a download.
        observer._binding(run_id, submission_id)
        if self.repository.get_run(run_id).status == "cancelled":
            raise ConflictError("run cancelled during image progress query")
        status = observation.payload["status"]
        if status == "completed":
            # Exactly one image was requested. Do not silently choose among
            # unexpected alternatives or make the user's choice for them.
            if len(observation.payload.get("result_urls", [])) != 1:
                raise ConflictError("single-frame production returned multiple images; reconcile before choosing")
            materialized = ImageMaterializationService(self.repository, self.data_root).materialize(run_id, observation.id)
            if self.repository.get_run(run_id).status == "cancelled":
                raise ConflictError("run cancelled during image download; saved bytes retained without advancing")
            return ImageProgressResult(run_id=run_id, submission_id=submission_id, observation_id=observation.id,
                                       phase="ready_for_review", materialization_id=materialized.id)
        return ImageProgressResult(run_id=run_id, submission_id=submission_id, observation_id=observation.id,
                                   phase="provider_failed" if status in {"failed", "error"} else "waiting")
