from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .models import RemoteTaskBinding, RemoteTaskState
from .qingshan_compilers import ModelCompilerRegistry
from .repository import ConflictError, Repository


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True)
class PaidProviderAcceptance:
    provider_task_id: str
    receipt: dict[str, Any] = field(default_factory=dict)


class AmbiguousPaidProviderResponse(RuntimeError):
    """The provider might have accepted a paid request, but identity is unknown."""

    def __init__(self, classification: str, evidence: dict[str, Any]):
        super().__init__(classification)
        self.classification = classification
        self.evidence = evidence


class PaidProviderTransport(Protocol):
    provider_name: str
    supports_idempotency: bool

    def post_paid_task(
        self, *, request: dict[str, Any], idempotency_key: str
    ) -> PaidProviderAcceptance: ...


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

    def submit_paid_task(
        self,
        run_id: str,
        *,
        task_key: str,
        provider: str,
        model: str,
        request: dict[str, Any],
        transport: PaidProviderTransport,
    ) -> RemoteTaskBinding:
        """Submit once through an idempotent provider boundary and bind its evidence.

        No concrete network transport is registered by default. Production adapters may
        call this method only after credentialed provider QA and explicit authorization.
        """
        package_sha256, package = self._authorized_package(run_id, model)
        if transport.provider_name != provider:
            raise ConflictError("paid transport does not match the requested provider")
        if not transport.supports_idempotency:
            raise ConflictError("paid transport must guarantee provider idempotency")
        boundary_failures = ModelCompilerRegistry().validate_paid_boundary_request(
            model,
            request,
            production_package=package,
            package_sha256=package_sha256,
        )
        if boundary_failures:
            raise ConflictError("paid boundary contract failed: " + "; ".join(boundary_failures))
        request_sha256 = _canonical_sha256(request)
        submission_fingerprint = _canonical_sha256(
            {
                "run_id": run_id,
                "task_key": task_key,
                "provider": provider,
                "model": model,
                "package_sha256": package_sha256,
                "request_sha256": request_sha256,
            }
        )
        binding = self.prepare(
            run_id,
            task_key=task_key,
            provider=provider,
            model=model,
            submission_fingerprint=submission_fingerprint,
            request_sha256=request_sha256,
        )
        if binding.state != RemoteTaskState.PREPARED:
            return binding
        try:
            accepted = transport.post_paid_task(
                request=request,
                idempotency_key=submission_fingerprint,
            )
        except AmbiguousPaidProviderResponse as exc:
            evidence = {
                "classification": exc.classification,
                "evidence": exc.evidence,
            }
            return self.record_response(
                binding.id,
                target_state=RemoteTaskState.AMBIGUOUS_CHARGE,
                response_sha256=_canonical_sha256(evidence),
                receipt=evidence,
                charge_classification=exc.classification,
            )
        if not accepted.provider_task_id.strip():
            raise ConflictError("paid provider acceptance omitted its task identity")
        response = {
            "provider_task_id": accepted.provider_task_id,
            "receipt": accepted.receipt,
        }
        return self.record_response(
            binding.id,
            target_state=RemoteTaskState.SUBMITTED,
            provider_task_id=accepted.provider_task_id,
            response_sha256=_canonical_sha256(response),
            receipt=accepted.receipt,
            charge_classification="TASK_ID_BOUND_CHARGE_PENDING",
        )

    def _authorized_package(self, run_id: str, model: str) -> tuple[str, dict[str, Any]]:
        run = self._repository.get_run(run_id)
        if run.dry_run:
            raise ConflictError("dry runs cannot use the paid submitter")
        package_path = Path(run.package_path)
        if not package_path.is_file() or package_path.is_symlink():
            raise ConflictError("paid submission requires an immutable production package")
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConflictError("paid submission production package is unreadable") from exc
        package_sha256 = package.get("package_sha256", "")
        package_body = {key: value for key, value in package.items() if key != "package_sha256"}
        if not package_sha256 or _canonical_sha256(package_body) != package_sha256:
            raise ConflictError("paid submission production package integrity failed")
        policy = package.get("production_policy", {})
        if (
            policy.get("paid_generation_approved") is not True
            or not str(policy.get("approved_by", "")).strip()
        ):
            raise ConflictError("paid submission requires explicit package-bound approval")
        if policy.get("requested_model") != model or run.requested_model != model:
            raise ConflictError("paid submission model does not match its approved package")
        return package_sha256, package
