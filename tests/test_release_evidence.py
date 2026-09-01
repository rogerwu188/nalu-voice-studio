import pytest
from nalu_runtime.release_evidence import (
    DisabledReleaseEvidenceVerifier,
    ReleaseEvidenceVerificationError,
)


def test_packaged_release_evidence_verifier_fails_closed() -> None:
    with pytest.raises(
        ReleaseEvidenceVerificationError,
        match="no authorized release evidence verifier",
    ):
        DisabledReleaseEvidenceVerifier().lookup_release_evidence(
            feedback_id="fb_test",
            release_linkage_sha256="a" * 64,
            ci_run_url="https://github.com/example/nalu/actions/runs/42",
            artifact_sha256="b" * 64,
            installed_version="0.2.0",
            installed_build=20,
        )
