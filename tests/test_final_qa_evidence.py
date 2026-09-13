import pytest
from nalu_runtime.models import FinalQAEvidence
from pydantic import ValidationError

CHECKS = (
    "original_resolution_reviewed", "picture_passed", "audio_sync_passed",
    "captions_passed", "continuity_passed", "safety_passed",
)


def evidence():
    return {
        "schema_version": "nalu.final-qa-evidence/v1",
        "run_id": "run_review", "master_sha256": "a" * 64,
        **dict.fromkeys(CHECKS, True), "reviewed_by": "human-reviewer",
        "review_channel": "human_original_resolution",
        "reviewed_at": "2026-09-13T12:00:00Z",
    }


@pytest.mark.parametrize("field", CHECKS)
@pytest.mark.parametrize("value", ["true", "yes", 1, False, None])
def test_final_attestation_requires_explicit_true(field, value):
    payload = evidence()
    payload[field] = value
    with pytest.raises(ValidationError):
        FinalQAEvidence.model_validate(payload)


def test_explicit_attestations_round_trip():
    parsed = FinalQAEvidence.model_validate(evidence())
    assert FinalQAEvidence.model_validate_json(parsed.model_dump_json()) == parsed
