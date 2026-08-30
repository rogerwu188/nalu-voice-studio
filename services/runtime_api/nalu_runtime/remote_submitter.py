from __future__ import annotations

from typing import Any

from .models import RemoteTaskBinding, RemoteTaskState
from .repository import Repository


class DurableRemoteTaskSubmitter:
    """The runtime's single authority for durable paid-provider task writes.

    Provider adapters must record an immutable intent here before making a paid
    request, then atomically bind the response evidence through ``record_response``.
    The repository does not expose public mutation methods for these records.
    """

    authority_name = "nalu.durable-remote-task-submitter/v1"

    def __init__(self, repository: Repository):
        self._repository = repository
        self.__write_authority = repository._bind_remote_task_submitter()

    def prepare(
        self,
        run_id: str,
        *,
        task_key: str,
        provider: str,
        model: str,
        submission_fingerprint: str,
        request_sha256: str,
    ) -> RemoteTaskBinding:
        return self._repository._prepare_remote_task_binding(
            self.__write_authority,
            run_id,
            task_key=task_key,
            provider=provider,
            model=model,
            submission_fingerprint=submission_fingerprint,
            request_sha256=request_sha256,
        )

    def record_response(
        self,
        binding_id: str,
        *,
        target_state: RemoteTaskState,
        response_sha256: str,
        provider_task_id: str | None = None,
        result_uri: str | None = None,
        receipt: dict[str, Any] | None = None,
        charge_classification: str,
        actual_charged_credits: int | None = None,
    ) -> RemoteTaskBinding:
        return self._repository._transition_remote_task_binding(
            self.__write_authority,
            binding_id,
            target_state=target_state,
            response_sha256=response_sha256,
            provider_task_id=provider_task_id,
            result_uri=result_uri,
            receipt=receipt,
            charge_classification=charge_classification,
            actual_charged_credits=actual_charged_credits,
        )
