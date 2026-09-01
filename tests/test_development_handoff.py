import json
from pathlib import Path

import pytest
from nalu_runtime.development_handoff import (
    DevelopmentHandoffPolicy,
    DevelopmentHandoffPolicyError,
    DisabledDevelopmentHandoffReconciliationVerifier,
    DisabledDevelopmentHandoffTransport,
)


def write_policy(path: Path, **changes) -> Path:
    value = {
        "schema_version": "nalu.development-handoff-policy/v1",
        "enabled": False,
        "administrator_authorized": False,
        "provider": "development_agent",
        "endpoint": "",
        "max_payload_bytes": 65536,
        **changes,
    }
    path.write_text(json.dumps(value))
    return path


def test_packaged_development_handoff_is_disabled_and_target_free() -> None:
    policy = DevelopmentHandoffPolicy.load(Path("configs/development-handoff.json"))
    assert policy.enabled is False
    assert policy.administrator_authorized is False
    assert policy.endpoint == ""
    with pytest.raises(DevelopmentHandoffPolicyError):
        DisabledDevelopmentHandoffTransport().submit_work_order(
            endpoint="https://developer.example.test/api/development-work-orders",
            payload={},
            idempotency_key="disabled-handoff-0001",
        )
    with pytest.raises(DevelopmentHandoffPolicyError):
        DisabledDevelopmentHandoffReconciliationVerifier().lookup_work_order(
            endpoint="https://developer.example.test/api/development-work-orders",
            payload_sha256="0" * 64,
            idempotency_key="disabled-handoff-0001",
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": True, "administrator_authorized": False},
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "http://developer.example.test/api/development-work-orders",
        },
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "https://user@developer.example.test/api/development-work-orders",
        },
        {
            "enabled": True,
            "administrator_authorized": True,
            "endpoint": "https://developer.example.test/api/development-work-orders?token=x",
        },
        {
            "enabled": False,
            "endpoint": "https://developer.example.test/api/development-work-orders",
        },
    ],
)
def test_development_handoff_policy_rejects_unsafe_configuration(
    tmp_path: Path, changes: dict
) -> None:
    with pytest.raises(DevelopmentHandoffPolicyError):
        DevelopmentHandoffPolicy.load(write_policy(tmp_path / "policy.json", **changes))
