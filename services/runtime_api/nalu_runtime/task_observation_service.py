"""Refresh only an existing local binding; never manufacture task identity or billing."""

import hashlib
import json
from dataclasses import asdict

from .giggle_task_query import GiggleTaskQuery
from .repository import ConflictError, Repository


class TaskObservationService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def refresh(self, run_id: str, binding_id: str, query: GiggleTaskQuery):
        run = self.repository.get_run(run_id)
        binding = self.repository.get_remote_task_binding(binding_id)
        if binding.run_id != run_id or binding.provider != "giggle" or not binding.provider_task_id:
            raise ConflictError("query requires a Giggle task already bound to this run")
        if self.repository.get_project(run.project_id).archived_at:
            raise ConflictError("archived project is read-only")
        observed = query.query(binding.provider_task_id)
        if observed.task_id != binding.provider_task_id or observed.billing_verified:
            raise ConflictError("task observation identity or billing boundary mismatch")
        # Queries cannot mutate accepted task, charge classification or run state.
        current = self.repository.get_remote_task_binding(binding_id)
        if current.provider_task_id != binding.provider_task_id or current.run_id != run_id:
            raise ConflictError("task binding changed during query")
        payload = {**asdict(observed), "binding_id": binding_id,
                   "generation_performed": False, "master_accepted": False}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        payload["observation_sha256"] = digest
        return self.repository.append_run_event_once(
            run_id, "provider_task_observed", dedupe_key="observation_sha256", dedupe_value=digest,
            message="Provider task status observed; billing and media QA remain separate.", payload=payload,
        )
