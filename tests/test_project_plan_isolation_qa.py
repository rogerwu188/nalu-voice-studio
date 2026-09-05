import importlib.util
from pathlib import Path

import pytest


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts/qa-project-plan-isolation.py"
    spec = importlib.util.spec_from_file_location("project_plan_isolation_qa", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_report(module) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "nalu.project-plan-isolation-qa/v1",
        "status": "PASS",
        "source_commit": "1" * 40,
        "runtime_mode": "packaged",
        "runtime_schema_version": "27",
        "project_count": 3,
        "episodes_per_project": 10,
        "concurrent_atomic_planning": True,
        "identifier_sets_disjoint": True,
        "cross_project_edit_isolated": True,
        "approved_episode_immutable": True,
        "export_restore_preserved": True,
        "structural_cross_project_restore_rejected": True,
        "project_snapshot_sha256": "2" * 64,
        "backup_payload_sha256": ["3" * 64, "4" * 64, "5" * 64],
        "sanitized_environment_names": [],
        "network_scope": "loopback only",
        "paid_call_performed": False,
        "publication_performed": False,
        "external_write_performed": False,
        "human_acceptance_performed": False,
        "project_complete": False,
    }
    return {**body, "report_sha256": module.digest(body)}


def test_complete_project_plan_isolation_report_passes() -> None:
    module = load_module()
    report = valid_report(module)
    assert module.validate_report(report) == report


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("identifier_sets_disjoint", False, "safety claim"),
        ("external_write_performed", True, "external write"),
        ("project_count", 2, "matrix"),
        ("project_snapshot_sha256", "bad", "snapshot digest"),
        ("report_sha256", "0" * 64, "canonical digest"),
    ],
)
def test_project_plan_isolation_report_tampering_fails_closed(
    field: str, value: object, message: str
) -> None:
    module = load_module()
    report = valid_report(module)
    report[field] = value
    with pytest.raises(RuntimeError, match=message):
        module.validate_report(report)
