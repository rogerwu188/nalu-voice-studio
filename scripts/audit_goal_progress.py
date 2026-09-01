from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from runpy import run_path
from typing import Any

VALID_CHECKPOINT_STATES = {"READY", "IN_PROGRESS", "AWAITING_CI", "BLOCKED"}
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SOP_PATTERN = re.compile(r"^SOP-(0[0-9]|1[0-3])$")

audit_sop = run_path("scripts/audit_product_sop.py")["audit_sop"]


def audit_goal_progress(
    progress: dict[str, Any], sop_text: str, repository: Path | None = None
) -> dict[str, Any]:
    failures: list[str] = []
    sop_result = audit_sop(sop_text)
    if sop_result["status"] != "PASS":
        failures.append("PRODUCT_SOP audit must pass before progress can be trusted")

    if progress.get("schema_version") != "nalu.goal-progress/v1":
        failures.append("unsupported goal progress schema")
    if progress.get("sop_source") != "docs/PRODUCT_SOP.md":
        failures.append("goal progress must name the authoritative SOP source")
    if progress.get("sop_counts") != sop_result["counts"]:
        failures.append("goal progress SOP counts do not match PRODUCT_SOP")
    if progress.get("project_complete") != sop_result["project_complete"]:
        failures.append("goal progress completion flag does not match PRODUCT_SOP")

    observed_head = progress.get("observed_head", "")
    if not COMMIT_PATTERN.fullmatch(observed_head):
        failures.append("observed_head must be a full Git commit")

    closed = progress.get("last_closed_checkpoint") or {}
    if not SOP_PATTERN.fullmatch(closed.get("sop", "")):
        failures.append("last closed checkpoint must name SOP-00 through SOP-13")
    if not COMMIT_PATTERN.fullmatch(closed.get("product_commit", "")):
        failures.append("last closed checkpoint must bind a full product commit")
    for field in ("ci_run", "qa_evidence"):
        value = closed.get(field, "")
        if not value.startswith("https://github.com/"):
            failures.append(f"last closed checkpoint {field} must be GitHub evidence")
    if closed.get("result") != "PASS":
        failures.append("last closed checkpoint must record a PASS result")
    if repository is not None:
        product_commit = closed.get("product_commit", "")
        evidence_commit = closed.get("evidence_commit", "")
        for label, commit in (
            ("observed head", observed_head),
            ("product commit", product_commit),
            ("evidence commit", evidence_commit),
        ):
            check = subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=repository,
                capture_output=True,
                check=False,
            )
            if check.returncode != 0:
                failures.append(f"{label} does not resolve to a repository commit")
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", product_commit, evidence_commit],
            cwd=repository,
            capture_output=True,
            check=False,
        )
        if ancestry.returncode != 0:
            failures.append("evidence commit must descend from the product commit")
        evidence_paths = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", evidence_commit],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        if "docs/PRODUCT_SOP.md" not in evidence_paths.stdout.splitlines():
            failures.append("evidence commit must update docs/PRODUCT_SOP.md")

    checkpoint = progress.get("current_checkpoint") or {}
    if not SOP_PATTERN.fullmatch(checkpoint.get("sop", "")):
        failures.append("current checkpoint must name SOP-00 through SOP-13")
    if checkpoint.get("status") not in VALID_CHECKPOINT_STATES:
        failures.append("current checkpoint has an unsupported state")

    next_action = progress.get("next_action") or {}
    if not SOP_PATTERN.fullmatch(next_action.get("sop", "")):
        failures.append("next action must name SOP-00 through SOP-13")
    if not isinstance(next_action.get("requires_user_authorization"), bool):
        failures.append("next action must declare whether user authorization is required")

    execution = progress.get("execution_policy") or {}
    required_execution_guards = (
        "checkpoint_requires_implementation_tests_native_qa_docs_commit_push_ci_evidence",
        "pause_allowed_only_when_all_remaining_items_are_blocked",
        "chat_context_is_not_authoritative_progress_storage",
    )
    for guard in required_execution_guards:
        if execution.get(guard) is not True:
            failures.append(f"execution guard {guard} must remain true")
    if execution.get("paused") is True and next_action.get(
        "requires_user_authorization"
    ) is False:
        failures.append("execution cannot pause while a safe next action exists")

    external = progress.get("external_write_policy") or {}
    for guard in (
        "fail_closed_without_explicit_authorization",
        "stable_idempotency_key_required",
        "ambiguous_outcomes_are_quarantined",
    ):
        if external.get(guard) is not True:
            failures.append(f"external-write guard {guard} must remain true")
    if external.get("automatic_retry_after_ambiguous_charge_or_publication") is not False:
        failures.append("ambiguous paid or publication outcomes must never auto-retry")

    blockers = progress.get("blocking_conditions")
    if not isinstance(blockers, list) or not blockers:
        failures.append("blocking conditions must be a non-empty list")
    else:
        for blocker in blockers:
            if blocker.get("continue_other_work") is not True:
                failures.append("every blocker must explicitly allow other work to continue")
            if not all(SOP_PATTERN.fullmatch(sop) for sop in blocker.get("sops", [])):
                failures.append("every blocker SOP must be between SOP-00 and SOP-13")

    return {
        "schema_version": "nalu.goal-progress-audit/v1",
        "status": "PASS" if not failures else "FAIL",
        "project_complete": sop_result["project_complete"],
        "current_checkpoint": checkpoint.get("sop"),
        "next_action": next_action.get("id"),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit durable Nalu goal progress")
    parser.add_argument("path", nargs="?", default="docs/GOAL_PROGRESS.json")
    parser.add_argument("--sop", default="docs/PRODUCT_SOP.md")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    progress = json.loads(Path(args.path).read_text(encoding="utf-8"))
    result = audit_goal_progress(
        progress, Path(args.sop).read_text(encoding="utf-8"), Path.cwd()
    )
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"Goal progress audit {result['status']}; "
            f"project_complete={result['project_complete']}; "
            f"current={result['current_checkpoint']}; next={result['next_action']}"
        )
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
