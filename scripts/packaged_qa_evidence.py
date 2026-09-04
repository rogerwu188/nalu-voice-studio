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
