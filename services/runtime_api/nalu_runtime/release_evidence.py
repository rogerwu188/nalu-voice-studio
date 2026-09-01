from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


class ReleaseEvidenceVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseEvidenceVerification:
    ci_run_url: str
    ci_head_sha: str
    ci_conclusion: Literal["success"]
    artifact_sha256: str
    ci_completed_at: str
    version: str
    build: int
    product_commit: str
    provenance_sha256: str
    developer_id_team_id: str
    notarization_submission_id: str
    code_signature_verified: bool
    notarization_verified: bool
    gatekeeper_accepted: bool
    installed_at: str
    previous_version: str
    previous_build: int
    rollback_evidence_sha256: str
    project_data_preserved: bool
    rollback_verified_at: str
    evidence: dict[str, Any]


class ReleaseEvidenceVerifier(Protocol):
    def lookup_release_evidence(
        self,
        *,
        feedback_id: str,
        release_linkage_sha256: str,
        ci_run_url: str,
        artifact_sha256: str,
        installed_version: str,
        installed_build: int,
    ) -> ReleaseEvidenceVerification: ...


class DisabledReleaseEvidenceVerifier:
    def lookup_release_evidence(
        self,
        *,
        feedback_id: str,
        release_linkage_sha256: str,
        ci_run_url: str,
        artifact_sha256: str,
        installed_version: str,
        installed_build: int,
    ) -> ReleaseEvidenceVerification:
        raise ReleaseEvidenceVerificationError(
            "no authorized release evidence verifier is configured"
        )
