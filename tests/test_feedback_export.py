import json
from pathlib import Path

import pytest
from nalu_runtime.feedback_export import (
    DisabledIssueTrackerReconciliationVerifier,
    DisabledIssueTrackerTransport,
    FeedbackExportPolicy,
    FeedbackExportPolicyError,
)


def write_policy(path: Path, **changes) -> Path:
    value = {
        "schema_version": "nalu.feedback-export-policy/v1",
        "enabled": False,
        "administrator_authorized": False,
        "provider": "github_issues",
        "endpoint": "",
        "repository": "",
        "max_payload_bytes": 65536,
        **changes,
    }
    path.write_text(json.dumps(value))
    return path


def test_packaged_feedback_export_policy_is_disabled() -> None:
    policy = FeedbackExportPolicy.load(Path("configs/feedback-export.json"))
    assert policy.enabled is False
    assert policy.administrator_authorized is False
    assert policy.endpoint == ""
    assert policy.repository == ""


def test_distributed_issue_clients_deny_write_and_reconciliation() -> None:
    with pytest.raises(FeedbackExportPolicyError):
        DisabledIssueTrackerTransport().create_issue(
            endpoint="https://issues.example.test/api/issues",
            repository="example/nalu",
            payload={},
            idempotency_key="disabled-export-0001",
        )
    with pytest.raises(FeedbackExportPolicyError):
        DisabledIssueTrackerReconciliationVerifier().lookup_issue(
            endpoint="https://issues.example.test/api/issues",
            repository="example/nalu",
            payload_sha256="0" * 64,
            idempotency_key="disabled-export-0001",
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": True, "administrator_authorized": False},
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "http://issues.example.test/api/issues",
            "repository": "example/nalu",
        },
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "https://user@issues.example.test/api/issues",
            "repository": "example/nalu",
        },
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "https://issues.example.test/api/issues?token=secret",
            "repository": "example/nalu",
        },
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "https://issues.example.test/api/issues",
            "repository": "../other",
        },
        {"enabled": False, "endpoint": "https://issues.example.test/api/issues"},
    ],
)
def test_feedback_export_policy_rejects_unsafe_configuration(
    tmp_path: Path, changes: dict
) -> None:
    with pytest.raises(FeedbackExportPolicyError):
        FeedbackExportPolicy.load(write_policy(tmp_path / "policy.json", **changes))
