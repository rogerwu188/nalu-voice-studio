"""Shared fail-closed evidence validation for downloaded macOS QA harnesses."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
PUBLICATION_REPORT_FIELDS = {
    "schema_version",
    "status",
    "runtime_mode",
    "project_id",
    "metrics_id",
    "strategy_id",
    "checks",
    "network_scope",
    "production_data_modified",
    "report_sha256",
}
PUBLICATION_REPORT_CHECKS = {
    "isolated_temporary_sqlite",
    "project_visible",
    "digest_link_valid",
    "script_reapproval_required",
    "read_only_flags_valid",
}
PUBLICATION_NETWORK_SCOPE = (
    "loopback only; no provider, paid model, production or publication"
)
STAGED_UPDATE_FIELDS = {
    "schema_version",
    "status",
    "runtime_mode",
    "old_version",
    "old_build",
    "new_version",
    "new_build",
    "manifest_sha256",
    "tampered_manifest_rejected",
    "downgrade_or_replay_rejected",
    "unconfirmed_update_rolled_back",
    "confirmed_update_committed",
    "protected_project_data_sha256",
    "protected_project_data_preserved",
    "network_scope",
    "report_sha256",
}
ROLLBACK_FIELDS = {
    "schema_version",
    "status",
    "runtime_mode",
    "scope",
    "project",
    "schema_version_before",
    "schema_version_after_restart",
    "backup_sha256",
    "restart_state_preserved",
    "clean_backup_rollback_preserved",
    "network_scope",
    "report_sha256",
}


def validate_evidence_identifiers(
    *, artifact_digest: str, source_commit: str
) -> None:
    if not artifact_digest.startswith("sha256:") or not SHA256_PATTERN.fullmatch(
        artifact_digest.removeprefix("sha256:")
    ):
        raise RuntimeError("CI artifact digest must be a complete sha256 digest")
    if not COMMIT_PATTERN.fullmatch(source_commit):
        raise RuntimeError("source commit must be a complete lowercase Git commit")


def validate_source_commit(source_commit: str) -> None:
    if not COMMIT_PATTERN.fullmatch(source_commit):
        raise RuntimeError("source commit must be a complete lowercase Git commit")


def verify_release_zip(path: Path, expected_sha256: str) -> str:
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise RuntimeError("release ZIP SHA-256 must contain exactly 64 lowercase hex digits")
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("release ZIP must be a regular, non-symbolic-link file")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if not hmac.compare_digest(actual, expected_sha256):
        raise RuntimeError("release ZIP SHA-256 does not match the downloaded file")
    return actual


def _stream_sha256(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def regular_file_sha256(path: Path, *, label: str) -> str:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"{label} must be a regular, non-symbolic-link file")
    with path.open("rb") as handle:
        return _stream_sha256(handle)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError(f"publication report contains duplicate JSON key: {key}")
        result[key] = value
    return result


def verify_publication_learning_report(path: Path) -> dict[str, Any]:
    """Validate the packaged local-only publication-learning report fail closed."""
    raw = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    if raw is None:
        raise RuntimeError("publication report must be a regular, non-symbolic-link file")
    try:
        report = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("publication report must be valid UTF-8 JSON") from error
    if not isinstance(report, dict) or set(report) != PUBLICATION_REPORT_FIELDS:
        raise RuntimeError("publication report has missing or unexpected top-level fields")
    if report["schema_version"] != "nalu.packaged-publication-learning-qa/v1":
        raise RuntimeError("publication report schema is not supported")
    if report["status"] != "PASS" or report["runtime_mode"] != "packaged":
        raise RuntimeError("publication report does not describe a passing packaged run")
    checks = report["checks"]
    if not isinstance(checks, dict) or set(checks) != PUBLICATION_REPORT_CHECKS:
        raise RuntimeError("publication report check set is incomplete or unexpected")
    if any(value is not True for value in checks.values()):
        raise RuntimeError("publication report contains a failed safety check")
    if report["network_scope"] != PUBLICATION_NETWORK_SCOPE:
        raise RuntimeError("publication report network scope is not local-only")
    if report["production_data_modified"] is not False:
        raise RuntimeError("publication report claims production data was modified")
    for field, prefix in (
        ("project_id", "prj_"),
        ("metrics_id", "metrics_"),
        ("strategy_id", "strategy_"),
    ):
        value = report[field]
        if not isinstance(value, str) or not value.startswith(prefix) or len(value) <= len(prefix):
            raise RuntimeError(f"publication report {field} is not a stable Nalu identifier")
    claimed = report["report_sha256"]
    if not isinstance(claimed, str) or not SHA256_PATTERN.fullmatch(claimed):
        raise RuntimeError("publication report canonical digest is malformed")
    canonical_body = {key: value for key, value in report.items() if key != "report_sha256"}
    canonical = json.dumps(canonical_body, ensure_ascii=False, sort_keys=True).encode()
    actual = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(actual, claimed):
        raise RuntimeError("publication report canonical digest does not match its content")
    return report


def _load_strict_json_object(path: Path, *, label: str) -> dict[str, Any]:
    raw = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    if raw is None:
        raise RuntimeError(f"{label} must be a regular, non-symbolic-link file")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(f"{label} must be valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    return value


def _verify_compact_report_digest(report: dict[str, Any], *, label: str) -> None:
    claimed = report.get("report_sha256")
    if not isinstance(claimed, str) or not SHA256_PATTERN.fullmatch(claimed):
        raise RuntimeError(f"{label} canonical digest is malformed")
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    encoded = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    actual = hashlib.sha256(encoded).hexdigest()
    if not hmac.compare_digest(actual, claimed):
        raise RuntimeError(f"{label} canonical digest does not match its content")


def verify_staged_update_report(path: Path) -> dict[str, Any]:
    report = _load_strict_json_object(path, label="staged-update report")
    if set(report) != STAGED_UPDATE_FIELDS:
        raise RuntimeError("staged-update report has missing or unexpected fields")
    if report["schema_version"] != "nalu.macos-staged-update-qa/v1":
        raise RuntimeError("staged-update report schema is not supported")
    if report["status"] != "PASS" or report["runtime_mode"] != "packaged_update_helper":
        raise RuntimeError("staged-update report does not describe a passing packaged run")
    if (
        not isinstance(report["old_build"], int)
        or isinstance(report["old_build"], bool)
        or not isinstance(report["new_build"], int)
        or isinstance(report["new_build"], bool)
        or report["new_build"] != report["old_build"] + 1
    ):
        raise RuntimeError("staged-update report build transition is not monotonic")
    if (
        not isinstance(report["old_version"], str)
        or not report["old_version"]
        or not isinstance(report["new_version"], str)
        or not report["new_version"]
        or report["old_version"] == report["new_version"]
    ):
        raise RuntimeError("staged-update report version transition is invalid")
    for field in ("manifest_sha256", "protected_project_data_sha256"):
        if not isinstance(report[field], str) or not SHA256_PATTERN.fullmatch(report[field]):
            raise RuntimeError(f"staged-update report {field} is malformed")
    for field in (
        "tampered_manifest_rejected",
        "downgrade_or_replay_rejected",
        "unconfirmed_update_rolled_back",
        "confirmed_update_committed",
        "protected_project_data_preserved",
    ):
        if report[field] is not True:
            raise RuntimeError(f"staged-update report safety claim failed: {field}")
    if report["network_scope"] != (
        "offline only; no download, paid model, publication or release"
    ):
        raise RuntimeError("staged-update report network scope is not offline-only")
    _verify_compact_report_digest(report, label="staged-update report")
    return report


def verify_upgrade_rollback_report(path: Path) -> dict[str, Any]:
    report = _load_strict_json_object(path, label="upgrade-rollback report")
    if set(report) != ROLLBACK_FIELDS:
        raise RuntimeError("upgrade-rollback report has missing or unexpected fields")
    if report["schema_version"] != "nalu.macos-upgrade-rollback-qa/v1":
        raise RuntimeError("upgrade-rollback report schema is not supported")
    if report["status"] != "PASS" or report["runtime_mode"] != "packaged":
        raise RuntimeError("upgrade-rollback report does not describe a passing packaged run")
    if report["scope"] != (
        "Runtime restart and clean backup rollback only; not a signed/notarized app update"
    ):
        raise RuntimeError("upgrade-rollback report overclaims its test scope")
    if report["network_scope"] != (
        "loopback only; no update download, provider, paid model or publication"
    ):
        raise RuntimeError("upgrade-rollback report network scope is not loopback-only")
    if report["schema_version_before"] != report["schema_version_after_restart"]:
        raise RuntimeError("upgrade-rollback report schema changed across restart")
    if not isinstance(report["schema_version_before"], str) or not report[
        "schema_version_before"
    ].isdigit():
        raise RuntimeError("upgrade-rollback report schema version is malformed")
    project = report["project"]
    if not isinstance(project, dict) or set(project) != {
        "project_id",
        "episode_numbers",
        "statuses",
    }:
        raise RuntimeError("upgrade-rollback report project snapshot is malformed")
    if not isinstance(project["project_id"], str) or not project["project_id"].startswith(
        "prj_"
    ):
        raise RuntimeError("upgrade-rollback report project ID is malformed")
    if project["episode_numbers"] != list(range(1, 11)) or project["statuses"] != [
        "script_approved"
    ] * 10:
        raise RuntimeError("upgrade-rollback report does not preserve ten approved episodes")
    if not isinstance(report["backup_sha256"], str) or not SHA256_PATTERN.fullmatch(
        report["backup_sha256"]
    ):
        raise RuntimeError("upgrade-rollback report backup digest is malformed")
    for field in ("restart_state_preserved", "clean_backup_rollback_preserved"):
        if report[field] is not True:
            raise RuntimeError(f"upgrade-rollback report safety claim failed: {field}")
    _verify_compact_report_digest(report, label="upgrade-rollback report")
    return report


def verify_update_artifact_archive(
    *,
    archive_path: Path,
    expected_artifact_digest: str,
    staged_report_path: Path,
    rollback_report_path: Path,
    release_zip_path: Path,
    staged_member: str = "nalu-staged-update-universal.json",
    rollback_member: str = "nalu-upgrade-rollback-universal.json",
    release_member: str = "Nalu-Voice-Studio-macOS.zip",
    checksum_member: str = "Nalu-Voice-Studio-macOS.zip.sha256",
) -> dict[str, str]:
    if not expected_artifact_digest.startswith("sha256:"):
        raise RuntimeError("CI artifact digest must use the sha256: prefix")
    expected_archive_sha = expected_artifact_digest.removeprefix("sha256:")
    if not SHA256_PATTERN.fullmatch(expected_archive_sha):
        raise RuntimeError("CI artifact digest must contain exactly 64 lowercase hex digits")
    actual_archive_sha = regular_file_sha256(archive_path, label="artifact archive")
    if not hmac.compare_digest(actual_archive_sha, expected_archive_sha):
        raise RuntimeError("artifact archive SHA-256 does not match GitHub artifact digest")
    staged_sha = regular_file_sha256(staged_report_path, label="staged-update report")
    rollback_sha = regular_file_sha256(rollback_report_path, label="upgrade-rollback report")
    release_sha = regular_file_sha256(release_zip_path, label="release ZIP")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = [info.filename for info in archive.infolist()]
            if len(names) != len(set(names)):
                raise RuntimeError("artifact archive contains duplicate member names")
            required = {staged_member, rollback_member, release_member, checksum_member}
            if not required.issubset(names):
                raise RuntimeError("artifact archive is missing update evidence members")
            if archive.read(staged_member) != staged_report_path.read_bytes():
                raise RuntimeError("staged-update report is not the report embedded in artifact")
            if archive.read(rollback_member) != rollback_report_path.read_bytes():
                raise RuntimeError("upgrade-rollback report is not the report embedded in artifact")
            with archive.open(release_member) as handle:
                embedded_release_sha = _stream_sha256(handle)
            if not hmac.compare_digest(embedded_release_sha, release_sha):
                raise RuntimeError("release ZIP is not the release embedded in artifact")
            checksum_text = archive.read(checksum_member).decode("utf-8").strip()
    except (zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise RuntimeError("artifact archive is not a valid update evidence ZIP") from error
    checksum_parts = checksum_text.split()
    checksum_path = PurePosixPath(checksum_parts[1]) if len(checksum_parts) == 2 else None
    if (
        checksum_path is None
        or checksum_path.is_absolute()
        or ".." in checksum_path.parts
        or checksum_path.name != release_member
    ):
        raise RuntimeError("artifact release checksum manifest is malformed")
    if not hmac.compare_digest(checksum_parts[0], release_sha):
        raise RuntimeError("artifact release checksum does not match embedded release ZIP")
    return {
        "artifact_archive_sha256": actual_archive_sha,
        "staged_update_report_sha256": staged_sha,
        "upgrade_rollback_report_sha256": rollback_sha,
        "release_zip_sha256": release_sha,
    }


def verify_publication_artifact_archive(
    *,
    archive_path: Path,
    expected_artifact_digest: str,
    report_path: Path,
    release_zip_path: Path,
    report_member: str = "nalu-publication-fixture-universal.json",
    release_member: str = "Nalu-Voice-Studio-macOS.zip",
    checksum_member: str = "Nalu-Voice-Studio-macOS.zip.sha256",
) -> dict[str, str]:
    """Bind local report and release ZIP bytes to a downloaded GitHub artifact ZIP."""
    if not expected_artifact_digest.startswith("sha256:"):
        raise RuntimeError("CI artifact digest must use the sha256: prefix")
    expected_archive_sha = expected_artifact_digest.removeprefix("sha256:")
    if not SHA256_PATTERN.fullmatch(expected_archive_sha):
        raise RuntimeError("CI artifact digest must contain exactly 64 lowercase hex digits")
    actual_archive_sha = regular_file_sha256(archive_path, label="artifact archive")
    if not hmac.compare_digest(actual_archive_sha, expected_archive_sha):
        raise RuntimeError("artifact archive SHA-256 does not match GitHub artifact digest")

    report_sha = regular_file_sha256(report_path, label="publication report")
    release_sha = regular_file_sha256(release_zip_path, label="release ZIP")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = [info.filename for info in archive.infolist()]
            if len(names) != len(set(names)):
                raise RuntimeError("artifact archive contains duplicate member names")
            required = {report_member, release_member, checksum_member}
            if not required.issubset(names):
                raise RuntimeError("artifact archive is missing publication evidence members")
            if archive.read(report_member) != report_path.read_bytes():
                raise RuntimeError("publication report is not the report embedded in artifact")
            with archive.open(release_member) as handle:
                embedded_release_sha = _stream_sha256(handle)
            if not hmac.compare_digest(embedded_release_sha, release_sha):
                raise RuntimeError("release ZIP is not the release embedded in artifact")
            checksum_text = archive.read(checksum_member).decode("utf-8").strip()
    except (zipfile.BadZipFile, UnicodeDecodeError) as error:
        raise RuntimeError("artifact archive is not a valid publication evidence ZIP") from error
    checksum_parts = checksum_text.split()
    checksum_path = PurePosixPath(checksum_parts[1]) if len(checksum_parts) == 2 else None
    if (
        checksum_path is None
        or checksum_path.is_absolute()
        or ".." in checksum_path.parts
        or checksum_path.name != release_member
    ):
        raise RuntimeError("artifact release checksum manifest is malformed")
    if not hmac.compare_digest(checksum_parts[0], release_sha):
        raise RuntimeError("artifact release checksum does not match embedded release ZIP")
    return {
        "artifact_archive_sha256": actual_archive_sha,
        "publication_report_sha256": report_sha,
        "release_zip_sha256": release_sha,
    }


def editorial_fixture_layout(
    duration_seconds: int,
) -> tuple[bool, int, list[tuple[float, float]]]:
    """Return bounded source media and explicit non-passthrough editorial windows."""
    if duration_seconds < 2:
        raise RuntimeError("fixture duration must be at least two seconds")
    long_soak = duration_seconds >= 60
    if duration_seconds == 2:
        source_video_seconds = 2
        source_ranges: list[tuple[float, float]] = [(0, 1), (1, 2)]
    elif long_soak:
        source_video_seconds = min(301, duration_seconds + 1)
        source_ranges = [
            (0, min(300, duration_seconds - offset))
            for offset in range(0, duration_seconds, 300)
        ]
    else:
        source_video_seconds = duration_seconds + 1
        midpoint = duration_seconds / 2
        source_ranges = [(0, midpoint), (midpoint, duration_seconds)]
    if any(
        source_in <= 0.05 and source_out >= source_video_seconds - 0.05
        for source_in, source_out in source_ranges
    ):
        raise RuntimeError("packaged QA positive fixture cannot use whole-media passthrough")
    if abs(sum(end - start for start, end in source_ranges) - duration_seconds) > 0.001:
        raise RuntimeError("packaged QA editorial windows do not cover the target timeline")
    return long_soak, source_video_seconds, source_ranges
