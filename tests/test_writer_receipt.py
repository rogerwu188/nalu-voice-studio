import hashlib
import json
from copy import deepcopy

import pytest
from nalu_runtime.writer_receipt import (
    WriterReceiptVerificationError,
    verify_writer_receipt,
)

CONTENT = "Writer 权威输出"


def receipt_fixture() -> tuple[dict, dict]:
    declared = {
        "declared_provider": "anthropic",
        "declared_model_id": "claude-opus-4-1-20250805",
        "declared_session_or_task_id": "writer-task-001",
        "declared_input_bundle_sha256": "a" * 64,
        "declared_writer_rules_sha256": "b" * 64,
        "declared_started_at": "2026-09-03T20:00:00+00:00",
        "declared_completed_at": "2026-09-03T20:01:00+00:00",
        "script_content_sha256": hashlib.sha256(CONTENT.encode()).hexdigest(),
    }
    receipt = {
        "schema": "qingshan.canonical_writer_run_receipt.v1",
        "status": "COMPLETED",
        "writer_run_id": "WRITER-E1-V3-ABC123",
        "episode": "E1",
        "version": 3,
        "agent_id": "qingshan-claude-writer-agent",
        "provider": declared["declared_provider"],
        "model_id": declared["declared_model_id"],
        "session_or_task_id": declared["declared_session_or_task_id"],
        "started_at": declared["declared_started_at"],
        "completed_at": declared["declared_completed_at"],
        "input_bundle": {"sha256": declared["declared_input_bundle_sha256"]},
        "writer_rules": {"combined_sha256": declared["declared_writer_rules_sha256"]},
        "authority_output": {"sha256": declared["script_content_sha256"]},
    }
    return receipt, declared


def verify(receipt: dict, declared: dict) -> dict:
    receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
    return verify_writer_receipt(
        receipt_bytes,
        declared_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        **declared,
    )


def test_writer_receipt_verifier_normalizes_only_bound_evidence() -> None:
    receipt, declared = receipt_fixture()
    receipt["untrusted_path"] = "/private/source/session.json"
    receipt["warnings"] = ["inert upstream note"]
    normalized = verify(receipt, declared)

    assert normalized["writer_run_id"] == "WRITER-E1-V3-ABC123"
    assert normalized["authority_output_sha256"] == declared["script_content_sha256"]
    assert "untrusted_path" not in normalized
    assert "warnings" not in normalized


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("schema", "unsupported"), "schema is not supported"),
        (("status", "FAILED"), "is not COMPLETED"),
        (("agent_id", "unknown-writer"), "agent is not authorized"),
        (("writer_run_id", "WRITER-E2-V3-ABC123"), "does not bind episode and version"),
        (("model_id", "different-model"), "declared model_id"),
        (("session_or_task_id", "different-task"), "declared session_or_task_id"),
    ],
)
def test_writer_receipt_verifier_rejects_untrusted_identity_and_state(
    mutation: tuple[str, str], message: str
) -> None:
    receipt, declared = receipt_fixture()
    receipt[mutation[0]] = mutation[1]
    with pytest.raises(WriterReceiptVerificationError, match=message):
        verify(receipt, declared)


def test_writer_receipt_verifier_rejects_digest_and_time_mismatches() -> None:
    receipt, declared = receipt_fixture()
    cases = []

    bad_input = deepcopy(receipt)
    bad_input["input_bundle"]["sha256"] = "c" * 64
    cases.append((bad_input, declared, "input bundle does not match"))

    bad_rules = deepcopy(receipt)
    bad_rules["writer_rules"]["combined_sha256"] = "d" * 64
    cases.append((bad_rules, declared, "rules do not match"))

    bad_output = deepcopy(receipt)
    bad_output["authority_output"]["sha256"] = "e" * 64
    cases.append((bad_output, declared, "authority output does not match script"))

    reversed_receipt = deepcopy(receipt)
    reversed_declared = deepcopy(declared)
    reversed_declared["declared_started_at"] = "2026-09-03T20:02:00+00:00"
    reversed_receipt["started_at"] = reversed_declared["declared_started_at"]
    cases.append((reversed_receipt, reversed_declared, "completion precedes start"))

    naive_receipt = deepcopy(receipt)
    naive_declared = deepcopy(declared)
    naive_declared["declared_started_at"] = "2026-09-03T20:00:00"
    naive_declared["declared_completed_at"] = "2026-09-03T20:01:00"
    naive_receipt["started_at"] = naive_declared["declared_started_at"]
    naive_receipt["completed_at"] = naive_declared["declared_completed_at"]
    cases.append((naive_receipt, naive_declared, "timestamps require a UTC offset"))

    for candidate, candidate_declaration, message in cases:
        with pytest.raises(WriterReceiptVerificationError, match=message):
            verify(candidate, candidate_declaration)


def test_writer_receipt_verifier_rejects_raw_digest_mismatch_and_duplicate_keys() -> None:
    receipt, declared = receipt_fixture()
    receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
    with pytest.raises(WriterReceiptVerificationError, match="SHA-256 does not match"):
        verify_writer_receipt(
            receipt_bytes,
            declared_receipt_sha256="0" * 64,
            **declared,
        )

    duplicate = b'{"schema":"first","schema":"second"}'
    with pytest.raises(WriterReceiptVerificationError, match="repeats JSON key"):
        verify_writer_receipt(
            duplicate,
            declared_receipt_sha256=hashlib.sha256(duplicate).hexdigest(),
            **declared,
        )
