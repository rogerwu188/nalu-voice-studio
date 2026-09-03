from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


class WriterProviderVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class WriterProviderVerification:
    provider: str
    model_id: str
    session_or_task_id: str
    state: Literal["completed"]
    receipt_sha256: str
    started_at: str
    completed_at: str
    evidence: dict[str, Any]


class WriterProviderVerifier(Protocol):
    """Read-only authenticated lookup; implementations must never submit generation."""

    def lookup_writer_task(
        self,
        *,
        provider: str,
        model_id: str,
        session_or_task_id: str,
        receipt_sha256: str,
    ) -> WriterProviderVerification: ...


class DisabledWriterProviderVerifier:
    def lookup_writer_task(
        self,
        *,
        provider: str,
        model_id: str,
        session_or_task_id: str,
        receipt_sha256: str,
    ) -> WriterProviderVerification:
        raise WriterProviderVerificationError(
            "no authorized read-only Writer provider verifier is configured"
        )
