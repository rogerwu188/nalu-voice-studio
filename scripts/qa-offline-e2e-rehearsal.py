#!/usr/bin/env python3
"""Rehearse SOP-12 structures without claiming a real release acceptance run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = [
    {
        "id": "SOP-12-01-older-adult-autobiography",
        "tests": [
            "tests/test_runtime_api.py::test_atomic_multi_episode_project_plan",
            "tests/test_runtime_api.py::test_draft_project_is_finalized_in_place_with_existing_assets",
            "tests/test_runtime_api.py::test_biometric_asset_requires_consent",
        ],
        "remaining_real_evidence": [
            "clean signed-install voice-only interview",
            "real consented personal photos",
            "human older-adult accessibility review",
        ],
    },
    {
        "id": "SOP-12-02-guardian-child-fiction",
        "tests": [
            "tests/test_continuity_extraction.py::test_user_edits_require_explanation_and_child_confirmation_requires_guardian",
            "tests/test_runtime_api.py::test_feedback_is_local_redacted_and_child_sharing_fails_closed",
        ],
        "remaining_real_evidence": [
            "guardian-supervised clean-install voice session",
            "age-appropriate prompt human review",
        ],
    },
    {
        "id": "SOP-12-03-ten-episode-continuity",
        "tests": [
            "tests/test_runtime_api.py::test_atomic_multi_episode_project_plan",
            "tests/test_project_library.py::test_production_packages_freeze_confirmed_library_revision",
            "tests/test_continuity.py::test_matching_opening_state_passes_and_is_snapshotted",
            "tests/test_runtime_api.py::test_project_rename_archive_export_and_restore",
        ],
        "remaining_real_evidence": [
            "ten produced episodes from one signed installation",
            "human identity, voice and narrative continuity review",
        ],
    },
    {
        "id": "SOP-12-04-failure-restart-resume-qa",
        "tests": [
            "tests/test_runtime_api.py::test_episode_lifecycle_and_restart_recovery",
            "tests/test_runtime_api.py::test_run_events_cancel_and_resume",
            "tests/test_rendered_output_immutability.py::test_runtime_materializes_postproduction_and_recovers_after_state_commit_crash",
        ],
        "remaining_real_evidence": [
            "authorized provider failure and receipt reconciliation",
            "real final-master QA after restart",
        ],
    },
    {
        "id": "SOP-12-05-offline-release-package",
        "tests": [
            "tests/test_rendered_output_immutability.py::test_completed_media_qa_creates_offline_release_package_without_publishing",
            "tests/test_paid_submitter_boundary.py::test_ambiguous_response_is_quarantined_and_never_auto_reposted",
        ],
        "remaining_real_evidence": [
            "platform-specific publication authorization",
            "real publication ID and post-publication reconciliation",
        ],
    },
    {
        "id": "SOP-12-06-capability-routing",
        "tests": [
            "tests/test_runtime_api.py::test_creative_format_routes_projects_without_faking_an_adapter",
            "tests/test_project_library.py::test_documentary_projects_cannot_silently_use_short_drama_adapter",
            "tests/test_runtime_api.py::test_prohibited_model_is_rejected",
        ],
        "remaining_real_evidence": [
            "authorized animation provider result",
            "human confirmation that unsupported commercial intent remains useful but blocked",
        ],
    },
    {
        "id": "SOP-12-07-governed-usability-feedback",
        "tests": [
            "tests/test_runtime_api.py::test_feedback_review_bundle_is_local_redacted_immutable_and_exported",
            "tests/test_feedback_export.py::test_packaged_feedback_export_policy_is_disabled",
            "tests/test_development_handoff.py::test_packaged_development_handoff_is_disabled_and_target_free",
        ],
        "remaining_real_evidence": [
            "administrator-authorized issue export and reviewed change",
            "signed/notarized installed improvement and deliberate rollback",
        ],
    },
]


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    nodeids = list(dict.fromkeys(test for scenario in SCENARIOS for test in scenario["tests"]))
    environment = dict(os.environ)
    removed_names: list[str] = []
    for name in sorted(environment):
        upper = name.upper()
        if any(marker in upper for marker in ("API_KEY", "TOKEN", "SECRET", "CREDENTIAL")):
            removed_names.append(name)
            environment.pop(name, None)
    environment.update(
        {
            "NALU_OFFLINE_E2E_REHEARSAL": "1",
            "NALU_ALLOW_PAID_SUBMISSION": "false",
            "NALU_ALLOW_PUBLICATION": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *nodeids],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return completed.returncode
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    source_paths = sorted(
        {ROOT / test.split("::", 1)[0] for test in nodeids}
        | {Path(__file__).resolve(), ROOT / "tests/conftest.py"}
    )
    body = {
        "schema_version": "nalu.offline-e2e-rehearsal/v1",
        "source_commit": head,
        "mode": "offline_structure_rehearsal_only",
        "scenarios": [
            {
                **scenario,
                "status": "STRUCTURE_REHEARSED",
                "release_acceptance": False,
            }
            for scenario in SCENARIOS
        ],
        "selected_test_count": len(nodeids),
        "pytest_stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "source_sha256": {
            str(path.relative_to(ROOT)): file_sha256(path) for path in source_paths
        },
        "sanitized_environment_names": removed_names,
        "paid_call_performed": False,
        "publication_performed": False,
        "external_write_performed": False,
        "non_loopback_network_blocked": True,
        "signed_install_used": False,
        "notarized_install_used": False,
        "real_provider_receipts_reconciled": False,
        "real_publication_ids_reconciled": False,
        "human_acceptance_performed": False,
        "project_complete": False,
    }
    report = {**body, "evidence_sha256": canonical_sha256(body)}
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
