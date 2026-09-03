#!/usr/bin/env python3
"""Verify the pinned Qingshan import and optionally discover a newer release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs" / "qingshan-upstream.json"
CANDIDATE_AUDIT_PATH = ROOT / "configs" / "qingshan-candidate-audit.json"
VENDOR_ROOT = ROOT / "vendor" / "qingshan"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vendor_digest() -> str:
    rows = []
    tracked = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "vendor/qingshan"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for relative in sorted(tracked):
        path = ROOT / relative
        rows.append(f"{sha256(path)}  {path.relative_to(VENDOR_ROOT)}\n")
    return hashlib.sha256("".join(rows).encode()).hexdigest()


def verify(manifest: dict) -> list[str]:
    failures = []
    if manifest.get("schema_version") != "nalu.qingshan-upstream/v1":
        failures.append("unsupported upstream manifest schema")
    if vendor_digest() != manifest.get("vendor_content_sha256"):
        failures.append("vendor tree differs from the reviewed upstream snapshot")
    for name, capability in manifest.get("capabilities", {}).items():
        path = VENDOR_ROOT / capability["path"]
        if not path.is_file():
            failures.append(f"missing capability {name}: {capability['path']}")
        elif sha256(path) != capability["sha256"]:
            failures.append(f"capability hash mismatch: {name}")
    if not (VENDOR_ROOT / "LICENSE").is_file():
        failures.append("reviewed upstream license is absent")
    return failures


def verify_candidate_audit(manifest: dict, audit: dict) -> list[str]:
    failures: list[str] = []
    if audit.get("schema_version") != "nalu.qingshan-candidate-audit/v1":
        failures.append("unsupported Qingshan candidate-audit schema")
    if audit.get("repository") != manifest.get("repository"):
        failures.append("candidate audit targets a different repository")
    if audit.get("candidate_release") == manifest.get("release"):
        failures.append("candidate audit must not describe the active pin")
    if not isinstance(audit.get("candidate_commit"), str) or len(
        audit["candidate_commit"]
    ) != 40:
        failures.append("candidate audit has an invalid commit")
    for field in (
        "candidate_tree_sha256",
        "gate_registry_sha256",
        "portable_core_manifest_sha256",
    ):
        value = audit.get(field)
        if not isinstance(value, str) or len(value) != 64:
            failures.append(f"candidate audit has an invalid {field}")
    candidate_failures = audit.get("failures")
    if not isinstance(candidate_failures, list):
        failures.append("candidate registry failures must be a list")
        candidate_failures = []
    elif any(
        not isinstance(item, str)
        or not item.startswith(("missing_path:", "nonportable_absolute_path:"))
        for item in candidate_failures
    ):
        failures.append("candidate audit contains an unsupported failure classification")
    gate_count = audit.get("gate_count")
    coded_count = audit.get("coded_gate_count")
    runtime_count = audit.get("runtime_bound_count")
    if not all(isinstance(value, int) and value > 0 for value in (gate_count, coded_count, runtime_count)):
        failures.append("candidate audit has invalid gate counts")
    elif not runtime_count <= coded_count <= gate_count:
        failures.append("candidate audit gate counts are inconsistent")
    registry_status = audit.get("integrity_status")
    if registry_status not in {"PASS", "FAIL"}:
        failures.append("candidate registry integrity has an invalid status")
    elif (registry_status == "PASS") != (candidate_failures == []):
        failures.append("candidate registry status does not match its exact failures")
    public_interface_failures = audit.get("public_interface_failures")
    if not isinstance(public_interface_failures, list) or any(
        not isinstance(item, str) or not item.startswith("public_interface:")
        for item in (public_interface_failures or [])
    ):
        failures.append("candidate public interface has unsupported failures")
        public_interface_failures = []
    public_status = audit.get("public_interface_status")
    public_record_valid = (
        public_status in {"PASS", "FAIL"}
        and (public_status == "PASS") == (public_interface_failures == [])
        and isinstance(audit.get("public_interface_version"), str)
        and re.fullmatch(r"\d+\.\d+\.\d+", audit.get("public_interface_version", ""))
        is not None
        and audit.get("public_cli_entrypoint") == "qingshan_engine.cli:main"
    )
    expected_commands = [
        "doctor",
        "init",
        "release-preflight",
        "test",
        "video-preflight",
        "writer-doctor",
    ]
    expected_entrypoints = [
        "tools/platform_release_preflight.py",
        "tools/production_video_submission_gate.py",
        "tools/render_portable_timeline.py",
        "tools/submit_giggle_video_manifest_v2.py",
    ]
    if (
        not public_record_valid
        or audit.get("public_cli_commands") != expected_commands
        or audit.get("portable_entrypoints") != expected_entrypoints
    ):
        failures.append("candidate public engine interface record is inconsistent")
    if (
        audit.get("writer_v2_status") != "PASS"
        or audit.get("writer_provenance_schema")
        != "qingshan.canonical_writer_provenance.v1"
        or audit.get("writer_receipt_schema")
        != "qingshan.canonical_writer_run_receipt.v1"
        or not audit.get("writer_authorized_agent_ids")
        or not {"auto", "default"}.issubset(
            set(audit.get("writer_generic_model_aliases") or [])
        )
        or audit.get("writer_v2_failures") != []
    ):
        failures.append("candidate Writer v2 provenance contract is not portable")
    registered_counts = (
        audit.get("registered_test_module_count"),
        audit.get("registered_portable_test_count"),
        audit.get("registered_portable_skipped_count"),
        audit.get("registered_writer_test_count"),
    )
    registered_test_record_valid = (
        audit.get("registered_test_execution_performed") is True
        and audit.get("registered_test_status") == "PASS"
        and all(isinstance(value, int) and value >= 0 for value in registered_counts)
        and audit.get("registered_test_module_count", 0) > 0
        and audit.get("registered_portable_test_count", 0) > 0
        and audit.get("registered_writer_test_count", 0) > 0
        and audit.get("registered_test_failures") == []
    )
    if not registered_test_record_valid:
        failures.append("candidate registered-test evidence is incomplete")
    if (
        audit.get("promotion_status") != "QUARANTINED"
        or audit.get("paid_execution_allowed") is not False
        or audit.get("replaces_active_pin") is not False
    ):
        failures.append("failed candidate audit must remain quarantined and fail closed")
    return failures


def latest_release(repository: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Nalu-Upstream-Audit"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def release_requires_review(
    latest_tag: str, manifest: dict, candidate_audit: dict
) -> bool:
    """Return whether discovery found a release not covered by either trusted record."""
    return latest_tag not in {
        manifest.get("release"),
        candidate_audit.get("candidate_release"),
    }


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-latest", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures = verify(manifest)
    try:
        candidate_audit = json.loads(CANDIDATE_AUDIT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: candidate audit is unreadable: {exc}")
        return 1
    failures.extend(verify_candidate_audit(manifest, candidate_audit))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"Pinned Qingshan snapshot verified: {manifest['release']} @ {manifest['commit']}")
    print(
        "Latest reviewed Qingshan candidate remains quarantined: "
        f"{candidate_audit['candidate_release']} @ {candidate_audit['candidate_commit']} "
        f"(registry={candidate_audit['integrity_status']}, "
        f"public_interface={candidate_audit['public_interface_status']}, "
        f"registered_tests={candidate_audit['registered_test_status']})"
    )

    if args.check_latest:
        latest = latest_release(manifest["repository"])
        tag = latest["tag_name"]
        review_required = release_requires_review(tag, manifest, candidate_audit)
        # Keep the existing output name for workflow compatibility. It means an
        # unaudited release is available, not merely that the stable pin is older.
        write_output("update_available", str(review_required).lower())
        write_output("latest_tag", tag)
        write_output("latest_url", latest["html_url"])
        print(
            f"Latest upstream release: {tag}; "
            f"review_required={review_required}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
