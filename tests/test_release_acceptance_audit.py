import copy
import json
from pathlib import Path
from runpy import run_path

audit_release_acceptance = run_path("scripts/audit_release_acceptance.py")[
    "audit_release_acceptance"
]


def repository_inputs() -> tuple[dict, str]:
    manifest = json.loads(Path("docs/RELEASE_ACCEPTANCE.json").read_text(encoding="utf-8"))
    sop_text = Path("docs/PRODUCT_SOP.md").read_text(encoding="utf-8")
    return manifest, sop_text


def complete_sop() -> str:
    return "".join(
        f"## SOP-{number:02d} · Test — PASS\n\n"
        "Acceptance:\n\n- criterion\n\n"
        "Evidence:\n\n- Commit `abc`; GitHub CI passed.\n\n"
        for number in range(14)
    )


def complete_manifest() -> dict:
    commit = "a" * 40
    artifact = "b" * 64
    receipt = "c" * 64
    manifest = {
        "schema_version": "nalu.release-acceptance/v1",
        "status": "PASS",
        "completion_eligible": True,
        "candidate": {
            "commit": commit,
            "artifact_sha256": artifact,
            "signed": True,
            "notarized": True,
        },
        "required_gates": {},
    }
    common = {
        "candidate_commit": commit,
        "artifact_sha256": artifact,
        "evidence_url": "https://example.invalid/evidence",
    }
    details = {
        "signed_notarized_installation": {
            "developer_team_id": "ABCDE12345",
            "notarization_submission_id": "notary-1",
            "hardened_runtime_verified": True,
            "staple_verified": True,
            "gatekeeper_accepted": True,
        },
        "real_provider_reconciliation": {
            "provider_task_ids": ["task-1"],
            "provider_receipt_sha256": [receipt],
            "reconciled": True,
            "ambiguous_transactions": 0,
            "total_cost_minor_units": 100,
            "currency": "USD",
        },
        "real_publication_reconciliation": {
            "publication_ids": ["publication-1"],
            "publication_receipt_sha256": [receipt],
            "reconciled": True,
            "ambiguous_publications": 0,
        },
        "human_accessibility_acceptance": {
            "review_record_ids": ["review-1"],
            "voiceover_passed": True,
            "accessibility_inspector_passed": True,
            "older_adult_session_passed": True,
            "guardian_child_session_passed": True,
        },
        "seven_scenario_e2e": {
            "scenarios": [
                {"id": f"SOP-12-{number:02d}", "status": "PASS"}
                for number in range(1, 8)
            ]
        },
        "clean_install_upgrade_rollback": {
            "clean_account_install_passed": True,
            "ten_episode_data_preserved": True,
            "upgrade_passed": True,
            "rollback_passed": True,
            "older_build": "1",
            "candidate_build": "2",
        },
        "no_open_p0_p1": {"open_p0": 0, "open_p1": 0, "defect_query_id": "query-1"},
        "all_sops_same_candidate": {
            "sop_states": {f"SOP-{number:02d}": "PASS" for number in range(14)}
        },
    }
    for gate_name, detail in details.items():
        manifest["required_gates"][gate_name] = {
            "status": "PASS",
            "evidence": common | detail,
        }
    return manifest


def test_repository_manifest_is_honestly_not_ready() -> None:
    manifest, sop_text = repository_inputs()
    result = audit_release_acceptance(manifest, sop_text)
    assert result["status"] == "PASS", result["failures"]
    assert result["completion_eligible"] is False
    assert result["sop_project_complete"] is False


def test_incomplete_manifest_cannot_smuggle_pass_evidence() -> None:
    manifest, sop_text = repository_inputs()
    unsafe = copy.deepcopy(manifest)
    unsafe["required_gates"]["signed_notarized_installation"] = {
        "status": "PASS",
        "evidence": {"claim": "not checked"},
    }
    result = audit_release_acceptance(unsafe, sop_text)
    assert result["status"] == "FAIL"
    assert any("must not claim PASS" in failure for failure in result["failures"])
    assert any("must not attach PASS evidence" in failure for failure in result["failures"])


def test_false_completion_is_rejected_before_all_sops_pass() -> None:
    manifest, sop_text = repository_inputs()
    unsafe = copy.deepcopy(manifest)
    unsafe["status"] = "PASS"
    unsafe["completion_eligible"] = True
    unsafe["candidate"] = {
        "commit": "a" * 40,
        "artifact_sha256": "b" * 64,
        "signed": True,
        "notarized": True,
    }
    for gate in unsafe["required_gates"].values():
        gate["status"] = "PASS"
        gate["evidence"] = {
            "candidate_commit": "a" * 40,
            "artifact_sha256": "b" * 64,
            "evidence_url": "https://example.invalid/evidence",
        }
    result = audit_release_acceptance(unsafe, sop_text)
    assert result["status"] == "FAIL"
    assert "release acceptance cannot pass before SOP-00 through SOP-13 pass" in result[
        "failures"
    ]


def test_cross_candidate_evidence_is_rejected() -> None:
    manifest, sop_text = repository_inputs()
    unsafe = copy.deepcopy(manifest)
    unsafe["status"] = "PASS"
    unsafe["completion_eligible"] = True
    unsafe["candidate"] = {
        "commit": "a" * 40,
        "artifact_sha256": "b" * 64,
        "signed": True,
        "notarized": True,
    }
    for gate in unsafe["required_gates"].values():
        gate["status"] = "PASS"
        gate["evidence"] = {
            "candidate_commit": "c" * 40,
            "artifact_sha256": "d" * 64,
            "evidence_url": "https://example.invalid/evidence",
        }
    result = audit_release_acceptance(unsafe, sop_text)
    assert any("bound to another commit" in failure for failure in result["failures"])
    assert any("bound to another artifact" in failure for failure in result["failures"])


def test_complete_manifest_requires_gate_specific_evidence() -> None:
    manifest = complete_manifest()
    result = audit_release_acceptance(manifest, complete_sop())
    assert result["status"] == "PASS", result["failures"]
    assert result["completion_eligible"] is True

    missing_real_receipts = copy.deepcopy(manifest)
    missing_real_receipts["required_gates"]["real_provider_reconciliation"]["evidence"][
        "provider_receipt_sha256"
    ] = []
    result = audit_release_acceptance(missing_real_receipts, complete_sop())
    assert result["status"] == "FAIL"
    assert any("requires receipt digests" in failure for failure in result["failures"])


def test_seven_scenarios_cannot_be_replaced_by_a_dry_run() -> None:
    manifest = complete_manifest()
    manifest["required_gates"]["seven_scenario_e2e"]["evidence"]["scenarios"][0][
        "status"
    ] = "STRUCTURE_REHEARSED"
    result = audit_release_acceptance(manifest, complete_sop())
    assert result["status"] == "FAIL"
    assert any("every SOP-12 scenario must PASS" in failure for failure in result["failures"])
