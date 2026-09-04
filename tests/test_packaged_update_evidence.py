import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


def load_evidence_module():
    path = Path(__file__).resolve().parents[1] / "scripts/packaged_qa_evidence.py"
    spec = importlib.util.spec_from_file_location("packaged_qa_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def with_digest(report: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    report["report_sha256"] = hashlib.sha256(encoded).hexdigest()
    return report


def staged_report() -> dict[str, object]:
    return with_digest(
        {
            "schema_version": "nalu.macos-staged-update-qa/v1",
            "status": "PASS",
            "runtime_mode": "packaged_update_helper",
            "old_version": "0.1.0",
            "old_build": 1,
            "new_version": "0.1.1",
            "new_build": 2,
            "manifest_sha256": "1" * 64,
            "tampered_manifest_rejected": True,
            "downgrade_or_replay_rejected": True,
            "unconfirmed_update_rolled_back": True,
            "confirmed_update_committed": True,
            "protected_project_data_sha256": "2" * 64,
            "protected_project_data_preserved": True,
            "network_scope": "offline only; no download, paid model, publication or release",
        }
    )


def rollback_report() -> dict[str, object]:
    return with_digest(
        {
            "schema_version": "nalu.macos-upgrade-rollback-qa/v1",
            "status": "PASS",
            "runtime_mode": "packaged",
            "scope": "Runtime restart and clean backup rollback only; not a signed/notarized app update",
            "project": {
                "project_id": "prj_fixture",
                "episode_numbers": list(range(1, 11)),
                "statuses": ["script_approved"] * 10,
            },
            "schema_version_before": "26",
            "schema_version_after_restart": "26",
            "backup_sha256": "3" * 64,
            "restart_state_preserved": True,
            "clean_backup_rollback_preserved": True,
            "network_scope": "loopback only; no update download, provider, paid model or publication",
        }
    )


def write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def test_update_reports_verify_complete_offline_contract(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    staged_path = tmp_path / "staged.json"
    rollback_path = tmp_path / "rollback.json"
    staged = staged_report()
    rollback = rollback_report()
    write_json(staged_path, staged)
    write_json(rollback_path, rollback)

    assert evidence.verify_staged_update_report(staged_path) == staged
    assert evidence.verify_upgrade_rollback_report(rollback_path) == rollback


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report.update(new_build=3), "monotonic"),
        (
            lambda report: report.update(protected_project_data_preserved=False),
            "safety claim failed",
        ),
        (lambda report: report.update(report_sha256="0" * 64), "canonical digest"),
    ],
)
def test_staged_update_tampering_fails_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    evidence = load_evidence_module()
    path = tmp_path / "staged.json"
    report = staged_report()
    mutation(report)
    write_json(path, report)
    with pytest.raises(RuntimeError, match=message):
        evidence.verify_staged_update_report(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda report: report["project"].update(episode_numbers=list(range(1, 10))),
            "ten approved episodes",
        ),
        (lambda report: report.update(scope="signed update passed"), "overclaims"),
        (lambda report: report.update(report_sha256="0" * 64), "canonical digest"),
    ],
)
def test_upgrade_rollback_tampering_fails_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    evidence = load_evidence_module()
    path = tmp_path / "rollback.json"
    report = rollback_report()
    mutation(report)
    write_json(path, report)
    with pytest.raises(RuntimeError, match=message):
        evidence.verify_upgrade_rollback_report(path)


def test_update_artifact_binds_both_reports_release_and_checksum(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    staged_path = tmp_path / "nalu-staged-update-universal.json"
    rollback_path = tmp_path / "nalu-upgrade-rollback-universal.json"
    release_path = tmp_path / "Nalu-Voice-Studio-macOS.zip"
    write_json(staged_path, staged_report())
    write_json(rollback_path, rollback_report())
    release_path.write_bytes(b"exact release")
    release_sha = hashlib.sha256(release_path.read_bytes()).hexdigest()
    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(staged_path, staged_path.name)
        archive.write(rollback_path, rollback_path.name)
        archive.write(release_path, release_path.name)
        archive.writestr(
            f"{release_path.name}.sha256", f"{release_sha}  dist/{release_path.name}\n"
        )
    artifact_digest = f"sha256:{hashlib.sha256(archive_path.read_bytes()).hexdigest()}"

    result = evidence.verify_update_artifact_archive(
        archive_path=archive_path,
        expected_artifact_digest=artifact_digest,
        staged_report_path=staged_path,
        rollback_report_path=rollback_path,
        release_zip_path=release_path,
    )
    assert result["release_zip_sha256"] == release_sha

    rollback_path.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="rollback report is not"):
        evidence.verify_update_artifact_archive(
            archive_path=archive_path,
            expected_artifact_digest=artifact_digest,
            staged_report_path=staged_path,
            rollback_report_path=rollback_path,
            release_zip_path=release_path,
        )
