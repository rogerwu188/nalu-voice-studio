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


def test_candidate_audit_is_quarantined_and_fail_closed() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())

    assert checker.verify_candidate_audit(manifest, audit) == []
    assert audit["promotion_status"] == "QUARANTINED"
    assert audit["paid_execution_allowed"] is False
    assert audit["replaces_active_pin"] is False
    assert len(audit["failures"]) == 8


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
