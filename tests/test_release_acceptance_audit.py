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
