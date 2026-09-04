#!/usr/bin/env python3
"""Verify packaged staged-update and populated rollback evidence provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from packaged_qa_evidence import (
    validate_source_commit,
    verify_release_zip,
    verify_staged_update_report,
    verify_update_artifact_archive,
    verify_upgrade_rollback_report,
)


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged-report", type=Path, required=True)
    parser.add_argument("--rollback-report", type=Path, required=True)
    parser.add_argument("--release-zip", type=Path, required=True)
    parser.add_argument("--release-zip-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--ci-artifact-digest")
    parser.add_argument("--artifact-archive", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if bool(args.artifact_archive) != bool(args.ci_artifact_digest):
        parser.error("--artifact-archive and --ci-artifact-digest must be supplied together")

    validate_source_commit(args.source_commit)
    staged = verify_staged_update_report(args.staged_report)
    rollback = verify_upgrade_rollback_report(args.rollback_report)
    release_sha = verify_release_zip(args.release_zip, args.release_zip_sha256)
    archive_binding: dict[str, str] | None = None
    if args.artifact_archive:
        archive_binding = verify_update_artifact_archive(
            archive_path=args.artifact_archive,
            expected_artifact_digest=args.ci_artifact_digest,
            staged_report_path=args.staged_report,
            rollback_report_path=args.rollback_report,
            release_zip_path=args.release_zip,
        )

    receipt: dict[str, Any] = {
        "schema_version": "nalu.packaged-update-evidence-verification/v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "ci_artifact_digest": args.ci_artifact_digest,
        "artifact_archive_verified": archive_binding is not None,
        "artifact_archive_sha256": (
            archive_binding["artifact_archive_sha256"] if archive_binding else None
        ),
        "release_zip_sha256": release_sha,
        "staged_update_report_sha256": hashlib.sha256(
            args.staged_report.read_bytes()
        ).hexdigest(),
        "staged_update_report_canonical_sha256": staged["report_sha256"],
        "upgrade_rollback_report_sha256": hashlib.sha256(
            args.rollback_report.read_bytes()
        ).hexdigest(),
        "upgrade_rollback_report_canonical_sha256": rollback["report_sha256"],
        "old_build": staged["old_build"],
        "new_build": staged["new_build"],
        "schema_version_before": rollback["schema_version_before"],
        "schema_version_after_restart": rollback["schema_version_after_restart"],
        "ten_approved_episodes_preserved": True,
        "protected_project_data_preserved": True,
        "network_scope": "offline/loopback only; no update download, provider, paid model, publication or release",
        "external_write_performed": False,
    }
    receipt["receipt_sha256"] = canonical_digest(receipt)
    encoded = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        args.evidence.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
