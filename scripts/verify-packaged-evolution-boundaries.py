#!/usr/bin/env python3
"""Verify packaged feedback and development boundaries remain disabled by default."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from packaged_qa_evidence import (
    validate_source_commit,
    verify_controlled_evolution_policies,
    verify_release_artifact_archive,
    verify_release_zip,
)

POLICY_PATHS = {
    "feedback_export_policy_sha256": "configs/feedback-export.json",
    "development_handoff_policy_sha256": "configs/development-handoff.json",
}


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
    parser.add_argument("--release-zip", type=Path, required=True)
    parser.add_argument("--release-zip-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--ci-artifact-digest")
    parser.add_argument("--artifact-archive", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if bool(args.artifact_archive) != bool(args.ci_artifact_digest):
        parser.error("--artifact-archive and --ci-artifact-digest must be supplied together")

    validate_source_commit(args.source_commit)
    release_sha = verify_release_zip(args.release_zip, args.release_zip_sha256)
    policy_hashes = verify_controlled_evolution_policies(args.release_zip)
    for receipt_field, relative_path in POLICY_PATHS.items():
        if git_blob_sha256(args.repository, args.source_commit, relative_path) != policy_hashes[
            receipt_field
        ]:
            raise RuntimeError(f"packaged policy does not match {relative_path} at source commit")
    archive_binding: dict[str, str] | None = None
    if args.artifact_archive:
        archive_binding = verify_release_artifact_archive(
            archive_path=args.artifact_archive,
            expected_artifact_digest=args.ci_artifact_digest,
            release_zip_path=args.release_zip,
        )
    receipt: dict[str, Any] = {
        "schema_version": "nalu.packaged-evolution-boundaries-verification/v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "ci_artifact_digest": args.ci_artifact_digest,
        "artifact_archive_verified": archive_binding is not None,
        "artifact_archive_sha256": (
            archive_binding["artifact_archive_sha256"] if archive_binding else None
        ),
        "release_zip_sha256": release_sha,
        **policy_hashes,
        "feedback_export_enabled": False,
        "feedback_export_authorized": False,
        "feedback_export_target_present": False,
        "development_handoff_enabled": False,
        "development_handoff_authorized": False,
        "development_handoff_target_present": False,
        "automatic_code_change_enabled": False,
        "automatic_merge_enabled": False,
        "automatic_release_enabled": False,
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
