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
    if not isinstance(candidate_failures, list) or not candidate_failures:
        failures.append("quarantined candidate audit must retain exact failures")
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
    if (
        audit.get("public_interface_status") != "PASS"
        or not isinstance(audit.get("public_interface_version"), str)
        or re.fullmatch(r"\d+\.\d+\.\d+", audit.get("public_interface_version", "")) is None
        or audit.get("public_cli_entrypoint") != "qingshan_engine.cli:main"
        or audit.get("public_interface_failures") != []
    ):
        failures.append("candidate public engine interface is not portable")
    if (
        audit.get("integrity_status") != "FAIL"
        or audit.get("promotion_status") != "QUARANTINED"
        or audit.get("paid_execution_allowed") is not False
        or audit.get("replaces_active_pin") is not False
        or audit.get("registered_test_execution_performed") is not False
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
        f"({len(candidate_audit['failures'])} integrity failures)"
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
