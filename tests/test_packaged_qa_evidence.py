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


def test_release_zip_digest_is_recomputed_and_mismatch_fails_closed(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    release_zip = tmp_path / "release.zip"
    release_zip.write_bytes(b"downloaded-release")
    expected = hashlib.sha256(release_zip.read_bytes()).hexdigest()

    assert evidence.verify_release_zip(release_zip, expected) == expected
    with pytest.raises(RuntimeError, match="does not match"):
        evidence.verify_release_zip(release_zip, "0" * 64)
    with pytest.raises(RuntimeError, match="exactly 64"):
        evidence.verify_release_zip(release_zip, "not-a-digest")


def test_evidence_identifiers_require_complete_digests() -> None:
    evidence = load_evidence_module()
    evidence.validate_evidence_identifiers(
        artifact_digest=f"sha256:{'a' * 64}", source_commit="b" * 40
    )

    with pytest.raises(RuntimeError, match="artifact digest"):
        evidence.validate_evidence_identifiers(
            artifact_digest="trusted", source_commit="b" * 40
        )
    with pytest.raises(RuntimeError, match="source commit"):
        evidence.validate_evidence_identifiers(
            artifact_digest=f"sha256:{'a' * 64}", source_commit="main"
        )


@pytest.mark.parametrize("duration_seconds", [2, 3, 59, 60, 301, 1800])
def test_editorial_fixture_never_uses_whole_source_passthrough(
    duration_seconds: int,
) -> None:
    evidence = load_evidence_module()
    _long_soak, source_duration, ranges = evidence.editorial_fixture_layout(
        duration_seconds
    )

    assert sum(end - start for start, end in ranges) == duration_seconds
    assert all(not (start <= 0.05 and end >= source_duration - 0.05) for start, end in ranges)
    assert all(0 <= start < end <= source_duration for start, end in ranges)


def publication_report() -> dict[str, object]:
    report: dict[str, object] = {
        "schema_version": "nalu.packaged-publication-learning-qa/v1",
        "status": "PASS",
        "runtime_mode": "packaged",
        "project_id": "prj_fixture",
        "metrics_id": "metrics_fixture",
        "strategy_id": "strategy_fixture",
        "checks": {
            "isolated_temporary_sqlite": True,
            "project_visible": True,
            "digest_link_valid": True,
            "script_reapproval_required": True,
            "read_only_flags_valid": True,
        },
        "network_scope": "loopback only; no provider, paid model, production or publication",
        "production_data_modified": False,
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def write_report(path: Path, report: dict[str, object]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def test_publication_report_verifies_canonical_local_only_contract(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    report_path = tmp_path / "report.json"
    report = publication_report()
    write_report(report_path, report)

    assert evidence.verify_publication_learning_report(report_path) == report


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda report: report.update(status="FAIL"), "passing packaged"),
        (lambda report: report["checks"].update(read_only_flags_valid=False), "failed safety"),
        (lambda report: report.update(production_data_modified=True), "production data"),
        (lambda report: report.update(report_sha256="0" * 64), "canonical digest"),
    ],
)
def test_publication_report_tampering_fails_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    evidence = load_evidence_module()
    report_path = tmp_path / "report.json"
    report = publication_report()
    mutation(report)
    write_report(report_path, report)

    with pytest.raises(RuntimeError, match=message):
        evidence.verify_publication_learning_report(report_path)


def test_publication_artifact_archive_binds_report_release_and_checksum(
    tmp_path: Path,
) -> None:
    evidence = load_evidence_module()
    report_path = tmp_path / "nalu-publication-fixture-universal.json"
    write_report(report_path, publication_report())
    release_path = tmp_path / "Nalu-Voice-Studio-macOS.zip"
    release_path.write_bytes(b"exact release")
    release_sha = hashlib.sha256(release_path.read_bytes()).hexdigest()
    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(report_path, report_path.name)
        archive.write(release_path, release_path.name)
        archive.writestr(
            f"{release_path.name}.sha256", f"{release_sha}  dist/{release_path.name}\n"
        )
    artifact_digest = f"sha256:{hashlib.sha256(archive_path.read_bytes()).hexdigest()}"

    result = evidence.verify_publication_artifact_archive(
        archive_path=archive_path,
        expected_artifact_digest=artifact_digest,
        report_path=report_path,
        release_zip_path=release_path,
    )
    assert result["release_zip_sha256"] == release_sha

    with pytest.raises(RuntimeError, match="GitHub artifact digest"):
        evidence.verify_publication_artifact_archive(
            archive_path=archive_path,
            expected_artifact_digest=f"sha256:{'0' * 64}",
            report_path=report_path,
            release_zip_path=release_path,
        )

    release_path.write_bytes(b"substituted release")
    with pytest.raises(RuntimeError, match="not the release embedded"):
        evidence.verify_publication_artifact_archive(
            archive_path=archive_path,
            expected_artifact_digest=artifact_digest,
            report_path=report_path,
            release_zip_path=release_path,
        )
    release_path.write_bytes(b"exact release")
    report_path.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not the report embedded"):
        evidence.verify_publication_artifact_archive(
            archive_path=archive_path,
            expected_artifact_digest=artifact_digest,
            report_path=report_path,
            release_zip_path=release_path,
        )
