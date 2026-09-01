import importlib.util
import json
from copy import deepcopy
from pathlib import Path


def load_checker():
    path = Path(__file__).resolve().parents[1] / "scripts/check_qingshan_upstream.py"
    spec = importlib.util.spec_from_file_location("check_qingshan_upstream", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_isolated_auditor():
    path = Path(__file__).resolve().parents[1] / "scripts/audit_qingshan_candidate.py"
    spec = importlib.util.spec_from_file_location("audit_qingshan_candidate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_audit_is_quarantined_and_fail_closed() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())

    assert checker.verify_candidate_audit(manifest, audit) == []
    assert audit["promotion_status"] == "QUARANTINED"
    assert audit["paid_execution_allowed"] is False
    assert audit["replaces_active_pin"] is False
    assert len(audit["failures"]) == 9
    assert any(item.startswith("nonportable_absolute_path:") for item in audit["failures"])


def test_latest_release_is_covered_only_by_active_or_reviewed_record() -> None:
    checker = load_checker()
    manifest = {"release": "stable"}
    audit = {"candidate_release": "reviewed"}

    assert checker.release_requires_review("stable", manifest, audit) is False
    assert checker.release_requires_review("reviewed", manifest, audit) is False
    assert checker.release_requires_review("new", manifest, audit) is True


def test_candidate_audit_rejects_false_promotion_and_unknown_failures() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())
    tampered = deepcopy(audit)
    tampered["promotion_status"] = "PROMOTED"
    tampered["paid_execution_allowed"] = True
    tampered["replaces_active_pin"] = True
    tampered["failures"] = ["ignored_failure:unsafe"]

    failures = checker.verify_candidate_audit(manifest, tampered)
    assert "candidate audit contains an unsupported failure classification" in failures
    assert "failed candidate audit must remain quarantined and fail closed" in failures


def test_portable_auditor_rejects_absolute_path_even_when_file_exists() -> None:
    auditor = load_isolated_auditor()
    existing_absolute_path = str(Path(__file__).resolve())
    registry = {
        "gates": [
            {
                "gate_id": "TEST-GATE",
                "stage": "TEST",
                "implementation_type": "CODED",
                "code_paths": ["runner.py"],
                "test_paths": [existing_absolute_path],
                "stage_runner_paths": ["runner.py"],
                "parameters": {},
                "authorization_ref": "none",
                "last_backtest_date": "2026-09-01",
            }
        ]
    }
    report = auditor.validate_registry(registry, Path("/tmp/does-not-matter"))
    assert any(item.startswith("nonportable_absolute_path:TEST-GATE:") for item in report["failures"])
