from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from runpy import run_path
from typing import Any

COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_GATES = {
    "signed_notarized_installation",
    "real_provider_reconciliation",
    "real_publication_reconciliation",
    "human_accessibility_acceptance",
    "seven_scenario_e2e",
    "clean_install_upgrade_rollback",
    "no_open_p0_p1",
    "all_sops_same_candidate",
}
SCENARIO_IDS = {f"SOP-12-{number:02d}" for number in range(1, 8)}

audit_sop = run_path("scripts/audit_product_sop.py")["audit_sop"]


def _digest_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and SHA256_PATTERN.fullmatch(item) for item in value
    )


def _nonempty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _audit_gate_details(gate_name: str, evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if gate_name == "signed_notarized_installation":
        if not re.fullmatch(r"[A-Z0-9]{10}", str(evidence.get("developer_team_id", ""))):
            failures.append("signed installation requires a Developer ID team identifier")
        if not evidence.get("notarization_submission_id"):
            failures.append("signed installation requires a notarization submission identifier")
        for field in ("hardened_runtime_verified", "staple_verified", "gatekeeper_accepted"):
            if evidence.get(field) is not True:
                failures.append(f"signed installation requires {field}=true")
    elif gate_name == "real_provider_reconciliation":
        if not _nonempty_string_list(evidence.get("provider_task_ids")):
            failures.append("provider reconciliation requires real task identifiers")
        if not _digest_list(evidence.get("provider_receipt_sha256")):
            failures.append("provider reconciliation requires receipt digests")
        if evidence.get("reconciled") is not True or evidence.get("ambiguous_transactions") != 0:
            failures.append("provider transactions must reconcile with zero ambiguity")
        if not isinstance(evidence.get("total_cost_minor_units"), int) or evidence.get(
            "total_cost_minor_units", -1
        ) < 0:
            failures.append("provider reconciliation requires a non-negative exact cost")
        if not re.fullmatch(r"[A-Z]{3}", str(evidence.get("currency", ""))):
            failures.append("provider reconciliation requires an ISO currency")
    elif gate_name == "real_publication_reconciliation":
        if not _nonempty_string_list(evidence.get("publication_ids")):
            failures.append("publication reconciliation requires real publication identifiers")
        if not _digest_list(evidence.get("publication_receipt_sha256")):
            failures.append("publication reconciliation requires receipt digests")
        if evidence.get("reconciled") is not True or evidence.get("ambiguous_publications") != 0:
            failures.append("publications must reconcile with zero ambiguity")
    elif gate_name == "human_accessibility_acceptance":
        if not _nonempty_string_list(evidence.get("review_record_ids")):
            failures.append("human accessibility acceptance requires review records")
        for field in (
            "voiceover_passed",
            "accessibility_inspector_passed",
            "older_adult_session_passed",
            "guardian_child_session_passed",
        ):
            if evidence.get(field) is not True:
                failures.append(f"human accessibility acceptance requires {field}=true")
    elif gate_name == "seven_scenario_e2e":
        scenarios = evidence.get("scenarios")
        if not isinstance(scenarios, list) or {
            item.get("id") for item in scenarios if isinstance(item, dict)
        } != SCENARIO_IDS:
            failures.append("end-to-end acceptance requires all seven exact SOP-12 scenarios")
        elif any(item.get("status") != "PASS" for item in scenarios):
            failures.append("every SOP-12 scenario must PASS")
    elif gate_name == "clean_install_upgrade_rollback":
        for field in (
            "clean_account_install_passed",
            "ten_episode_data_preserved",
            "upgrade_passed",
            "rollback_passed",
        ):
            if evidence.get(field) is not True:
                failures.append(f"upgrade and rollback acceptance requires {field}=true")
        if not evidence.get("older_build") or not evidence.get("candidate_build"):
            failures.append("upgrade and rollback acceptance requires both build identities")
    elif gate_name == "no_open_p0_p1":
        if evidence.get("open_p0") != 0 or evidence.get("open_p1") != 0:
            failures.append("release acceptance requires zero open P0 and P1 defects")
        if not evidence.get("defect_query_id"):
            failures.append("defect counts require a preserved query identifier")
    elif gate_name == "all_sops_same_candidate":
        states = evidence.get("sop_states")
        expected = {f"SOP-{number:02d}": "PASS" for number in range(14)}
        if states != expected:
            failures.append("same-candidate evidence requires SOP-00 through SOP-13 PASS")
    return failures


def audit_release_acceptance(manifest: dict[str, Any], sop_text: str) -> dict[str, Any]:
    failures: list[str] = []
    sop = audit_sop(sop_text)
    if sop["status"] != "PASS":
        failures.append("PRODUCT_SOP audit must pass before release acceptance can be trusted")

    if manifest.get("schema_version") != "nalu.release-acceptance/v1":
        failures.append("unsupported release acceptance schema")

    gates = manifest.get("required_gates")
    if not isinstance(gates, dict) or set(gates) != REQUIRED_GATES:
        failures.append("release acceptance must contain every required gate exactly once")
        gates = {}

    candidate = manifest.get("candidate")
    completion_claimed = manifest.get("completion_eligible") is True
    status = manifest.get("status")

    if not completion_claimed:
        if status != "NOT_READY":
            failures.append("incomplete release acceptance must use NOT_READY status")
        if sop["project_complete"]:
            failures.append("all SOPs are PASS but release acceptance is not complete")
        for gate_name, gate in gates.items():
            if gate.get("status") not in {"BLOCKED", "IN_PROGRESS"}:
                failures.append(f"incomplete gate {gate_name} must not claim PASS")
            if gate.get("evidence") is not None:
                failures.append(f"incomplete gate {gate_name} must not attach PASS evidence")
    else:
        if status != "PASS":
            failures.append("completion-eligible release acceptance must use PASS status")
        if not sop["project_complete"]:
            failures.append("release acceptance cannot pass before SOP-00 through SOP-13 pass")
        if not isinstance(candidate, dict):
            failures.append("completion-eligible release must identify one candidate")
        else:
            commit = candidate.get("commit", "")
            artifact_sha256 = candidate.get("artifact_sha256", "")
            if not COMMIT_PATTERN.fullmatch(commit):
                failures.append("release candidate commit must be a full Git commit")
            if not SHA256_PATTERN.fullmatch(artifact_sha256):
                failures.append("release candidate artifact_sha256 must be a SHA-256 digest")
            if candidate.get("signed") is not True or candidate.get("notarized") is not True:
                failures.append("release candidate must be signed and notarized")

            for gate_name, gate in gates.items():
                if gate.get("status") != "PASS":
                    failures.append(f"release gate {gate_name} must PASS")
                    continue
                evidence = gate.get("evidence")
                if not isinstance(evidence, dict):
                    failures.append(f"release gate {gate_name} must attach structured evidence")
                    continue
                if evidence.get("candidate_commit") != commit:
                    failures.append(f"release gate {gate_name} is bound to another commit")
                if evidence.get("artifact_sha256") != artifact_sha256:
                    failures.append(f"release gate {gate_name} is bound to another artifact")
                if not str(evidence.get("evidence_url", "")).startswith("https://"):
                    failures.append(f"release gate {gate_name} must include an HTTPS evidence URL")
                failures.extend(
                    f"release gate {gate_name}: {failure}"
                    for failure in _audit_gate_details(gate_name, evidence)
                )

    return {
        "schema_version": "nalu.release-acceptance-audit/v1",
        "status": "PASS" if not failures else "FAIL",
        "completion_eligible": completion_claimed and not failures,
        "sop_project_complete": sop["project_complete"],
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit one Nalu release acceptance candidate")
    parser.add_argument("path", nargs="?", default="docs/RELEASE_ACCEPTANCE.json")
    parser.add_argument("--sop", default="docs/PRODUCT_SOP.md")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = audit_release_acceptance(
        json.loads(Path(args.path).read_text(encoding="utf-8")),
        Path(args.sop).read_text(encoding="utf-8"),
    )
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"Release acceptance audit {result['status']}; "
            f"completion_eligible={result['completion_eligible']}"
        )
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
