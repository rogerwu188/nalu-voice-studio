from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DevelopmentResultVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class DevelopmentResult:
    repository_url: str
    branch_name: str
    commit_sha: str
    review_url: str
    test_evidence_sha256: str
    evidence: dict[str, Any]


class DevelopmentResultVerifier(Protocol):
    def lookup_result(
        self,
        *,
        endpoint: str,
        remote_task_id: str,
        remote_task_url: str,
    ) -> DevelopmentResult: ...


class DisabledDevelopmentResultVerifier:
    def lookup_result(
        self,
        *,
        endpoint: str,
        remote_task_id: str,
        remote_task_url: str,
    ) -> DevelopmentResult:
        raise DevelopmentResultVerificationError(
            "no authorized development result verifier is configured"
        )
