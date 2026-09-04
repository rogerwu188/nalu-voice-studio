import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCENARIO_IDS = [
    "SOP-12-01-older-adult-autobiography",
    "SOP-12-02-guardian-child-fiction",
    "SOP-12-03-ten-episode-continuity",
    "SOP-12-04-failure-restart-resume-qa",
    "SOP-12-05-offline-release-package",
    "SOP-12-06-capability-routing",
    "SOP-12-07-governed-usability-feedback",
]


def load_evidence_module():
    path = Path(__file__).resolve().parents[1] / "scripts/packaged_qa_evidence.py"
    spec = importlib.util.spec_from_file_location("packaged_qa_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report_fixture(commit: str = "a" * 40) -> dict[str, object]:
    scenarios = [
        {
            "id": scenario_id,
            "tests": [f"tests/scenario_{index}.py::test_contract"],
            "remaining_real_evidence": ["signed human acceptance remains required"],
            "status": "STRUCTURE_REHEARSED",
            "release_acceptance": False,
        }
        for index, scenario_id in enumerate(SCENARIO_IDS, start=1)
    ]
    paths = {test.split("::", 1)[0] for item in scenarios for test in item["tests"]}
    paths |= {"scripts/qa-offline-e2e-rehearsal.py", "tests/conftest.py"}
    body: dict[str, object] = {
        "schema_version": "nalu.offline-e2e-rehearsal/v1",
        "source_commit": commit,
        "mode": "offline_structure_rehearsal_only",
        "scenarios": scenarios,
        "selected_test_count": 7,
        "pytest_stdout_sha256": "1" * 64,
        "source_sha256": {path: "2" * 64 for path in sorted(paths)},
        "sanitized_environment_names": [],
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
    encoded = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {**body, "evidence_sha256": hashlib.sha256(encoded).hexdigest()}


def write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def test_offline_e2e_report_verifies_truthful_seven_scenario_contract(
    tmp_path: Path,
) -> None:
    evidence = load_evidence_module()
    path = tmp_path / "report.json"
    report = report_fixture()
    write_report(path, report)
    assert evidence.verify_offline_e2e_report(path, expected_source_commit="a" * 40) == report


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report.update(project_complete=True), "false completion"),
        (
            lambda report: report["scenarios"][0].update(release_acceptance=True),
            "falsely claims",
        ),
        (lambda report: report.update(evidence_sha256="0" * 64), "canonical digest"),
    ],
)
def test_offline_e2e_report_tampering_fails_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    evidence = load_evidence_module()
    path = tmp_path / "report.json"
    report = report_fixture()
    mutation(report)
    write_report(path, report)
    with pytest.raises(RuntimeError, match=message):
        evidence.verify_offline_e2e_report(path, expected_source_commit="a" * 40)


def test_offline_e2e_artifact_binds_exact_report(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    report_path = tmp_path / "nalu-offline-e2e-rehearsal.json"
    write_report(report_path, report_fixture())
    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(report_path, report_path.name)
    digest = f"sha256:{hashlib.sha256(archive_path.read_bytes()).hexdigest()}"
    result = evidence.verify_offline_e2e_artifact_archive(
        archive_path=archive_path,
        expected_artifact_digest=digest,
        report_path=report_path,
    )
    assert result["offline_e2e_report_sha256"] == hashlib.sha256(
        report_path.read_bytes()
    ).hexdigest()

    report_path.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not the report embedded"):
        evidence.verify_offline_e2e_artifact_archive(
            archive_path=archive_path,
            expected_artifact_digest=digest,
            report_path=report_path,
        )
