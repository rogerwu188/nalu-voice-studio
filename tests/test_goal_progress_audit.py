import copy
import json
from pathlib import Path
from runpy import run_path

audit_goal_progress = run_path("scripts/audit_goal_progress.py")[
    "audit_goal_progress"
]


def repository_inputs() -> tuple[dict, str]:
    progress = json.loads(Path("docs/GOAL_PROGRESS.json").read_text(encoding="utf-8"))
    sop_text = Path("docs/PRODUCT_SOP.md").read_text(encoding="utf-8")
    return progress, sop_text


def test_repository_goal_progress_is_consistent_with_product_sop() -> None:
    progress, sop_text = repository_inputs()
    result = audit_goal_progress(progress, sop_text, Path.cwd())
    assert result["status"] == "PASS", result["failures"]
    assert result["project_complete"] is False
    assert result["current_checkpoint"] == progress["current_checkpoint"]["sop"]
    assert result["next_action"] == progress["next_action"]["id"]
    assert progress["next_action"]["requires_user_authorization"] is False


def test_nonexistent_evidence_commit_is_rejected() -> None:
    progress, sop_text = repository_inputs()
    progress["last_closed_checkpoint"]["evidence_commit"] = "f" * 40
    result = audit_goal_progress(progress, sop_text, Path.cwd())
    assert result["status"] == "FAIL"
    assert "evidence commit does not resolve to a repository commit" in result["failures"]


def test_sop_count_drift_and_false_completion_are_rejected() -> None:
    progress, sop_text = repository_inputs()
    progress["sop_counts"]["PASS"] += 1
    progress["project_complete"] = True
    result = audit_goal_progress(progress, sop_text)
    assert result["status"] == "FAIL"
    assert "goal progress SOP counts do not match PRODUCT_SOP" in result["failures"]
    assert "goal progress completion flag does not match PRODUCT_SOP" in result["failures"]


def test_execution_cannot_pause_while_safe_work_exists() -> None:
    progress, sop_text = repository_inputs()
    progress["execution_policy"]["paused"] = True
    progress["next_action"]["requires_user_authorization"] = False
    result = audit_goal_progress(progress, sop_text)
    assert result["status"] == "FAIL"
    assert "execution cannot pause while a safe next action exists" in result["failures"]


def test_paid_and_external_idempotency_guards_cannot_be_relaxed() -> None:
    progress, sop_text = repository_inputs()
    unsafe = copy.deepcopy(progress)
    unsafe["external_write_policy"]["stable_idempotency_key_required"] = False
    unsafe["external_write_policy"][
        "automatic_retry_after_ambiguous_charge_or_publication"
    ] = True
    result = audit_goal_progress(unsafe, sop_text)
    assert result["status"] == "FAIL"
    assert any("stable_idempotency_key_required" in item for item in result["failures"])
    assert any("must never auto-retry" in item for item in result["failures"])
