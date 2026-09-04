#!/usr/bin/env python3
"""Independently verify packaged publication-learning evidence and provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from packaged_qa_evidence import (
    validate_source_commit,
    verify_publication_artifact_archive,
    verify_publication_learning_report,
    verify_release_zip,
)


def canonical_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
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
    report = verify_publication_learning_report(args.report)
    release_sha = verify_release_zip(args.release_zip, args.release_zip_sha256)
    archive_binding: dict[str, str] | None = None
    if args.artifact_archive:
        archive_binding = verify_publication_artifact_archive(
            archive_path=args.artifact_archive,
            expected_artifact_digest=args.ci_artifact_digest,
            report_path=args.report,
            release_zip_path=args.release_zip,
        )

    receipt: dict[str, Any] = {
        "schema_version": "nalu.packaged-publication-evidence-verification/v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "ci_artifact_digest": args.ci_artifact_digest,
        "artifact_archive_verified": archive_binding is not None,
        "artifact_archive_sha256": (
            archive_binding["artifact_archive_sha256"] if archive_binding else None
        ),
        "release_zip_sha256": release_sha,
        "publication_report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "publication_report_canonical_sha256": report["report_sha256"],
        "project_id": report["project_id"],
        "metrics_id": report["metrics_id"],
        "strategy_id": report["strategy_id"],
        "network_scope": report["network_scope"],
        "production_data_modified": False,
        "publication_performed": False,
        "paid_call_performed": False,
    }
    receipt["receipt_sha256"] = canonical_digest(receipt)
    encoded = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        args.evidence.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
