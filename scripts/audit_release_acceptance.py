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

audit_sop = run_path("scripts/audit_product_sop.py")["audit_sop"]


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
