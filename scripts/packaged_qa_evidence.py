"""Shared fail-closed evidence validation for downloaded macOS QA harnesses."""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


def validate_evidence_identifiers(
    *, artifact_digest: str, source_commit: str
) -> None:
    if not artifact_digest.startswith("sha256:") or not SHA256_PATTERN.fullmatch(
        artifact_digest.removeprefix("sha256:")
    ):
        raise RuntimeError("CI artifact digest must be a complete sha256 digest")
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
