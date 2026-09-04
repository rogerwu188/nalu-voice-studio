#!/usr/bin/env python3
"""Verify seven-scenario offline rehearsal evidence without claiming release acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from packaged_qa_evidence import (
    verify_offline_e2e_artifact_archive,
    verify_offline_e2e_report,
)


def git_blob_sha256(repository: Path, commit: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repository,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cannot read {relative_path} from declared source commit")
    return hashlib.sha256(result.stdout).hexdigest()


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--ci-artifact-digest")
    parser.add_argument("--artifact-archive", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if bool(args.artifact_archive) != bool(args.ci_artifact_digest):
        parser.error("--artifact-archive and --ci-artifact-digest must be supplied together")

    report = verify_offline_e2e_report(
        args.report, expected_source_commit=args.source_commit
    )
    for relative_path, expected_sha in report["source_sha256"].items():
        actual_sha = git_blob_sha256(args.repository, args.source_commit, relative_path)
        if actual_sha != expected_sha:
            raise RuntimeError(f"declared source digest does not match {relative_path}")
    archive_binding: dict[str, str] | None = None
    if args.artifact_archive:
        archive_binding = verify_offline_e2e_artifact_archive(
            archive_path=args.artifact_archive,
            expected_artifact_digest=args.ci_artifact_digest,
            report_path=args.report,
        )
    receipt: dict[str, Any] = {
        "schema_version": "nalu.offline-e2e-evidence-verification/v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "ci_artifact_digest": args.ci_artifact_digest,
        "artifact_archive_verified": archive_binding is not None,
        "artifact_archive_sha256": (
            archive_binding["artifact_archive_sha256"] if archive_binding else None
        ),
        "offline_e2e_report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "offline_e2e_report_canonical_sha256": report["evidence_sha256"],
        "scenario_count": len(report["scenarios"]),
        "selected_test_count": report["selected_test_count"],
        "source_file_count": len(report["source_sha256"]),
        "mode": report["mode"],
        "non_loopback_network_blocked": True,
        "signed_install_used": False,
        "notarized_install_used": False,
        "paid_call_performed": False,
        "publication_performed": False,
        "external_write_performed": False,
        "human_acceptance_performed": False,
        "project_complete": False,
    }
    receipt["receipt_sha256"] = canonical_digest(receipt)
    encoded = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        args.evidence.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
