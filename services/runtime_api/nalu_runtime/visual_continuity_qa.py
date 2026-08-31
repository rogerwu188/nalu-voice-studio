from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import av

REQUIRED_DOMAINS = ("identity", "wardrobe", "space_axis", "pose", "props")
MINIMUM_CONFIDENCE = {
    "identity": 0.85,
    "wardrobe": 0.80,
    "space_axis": 0.75,
    "pose": 0.75,
    "props": 0.80,
}
APPROVED_ANALYZERS = {"qingshan-visual-continuity-local"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decoded_frames(master_path: Path) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    with av.open(str(master_path), mode="r") as container:
        if not container.streams.video:
            return frames
        for frame in container.decode(container.streams.video[0]):
            if frame.time is None:
                continue
            gray = frame.reformat(format="gray8")
            plane = gray.planes[0]
            raw = bytes(plane)
            pixels = b"".join(
                raw[row * plane.line_size : row * plane.line_size + gray.width]
                for row in range(gray.height)
            )
            frames.append(
                {
                    "time_seconds": round(float(frame.time), 6),
                    "frame_sha256": hashlib.sha256(pixels).hexdigest(),
                    "width": gray.width,
                    "height": gray.height,
                }
            )
    return frames


def _domain_failure(domain: str, suffix: str) -> str:
    prefix = "PROP" if domain == "props" else domain.upper()
    return f"{prefix}_{suffix}"


def inspect_visual_continuity(
    manifest_path: Path,
    *,
    production_package_sha256: str,
    master_path: Path,
    master_sha256: str,
    resolved_library: list[dict[str, Any]],
    resolved_library_sha256: str,
) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        manifest = {}
        failures.append("MANIFEST_UNREADABLE")

    if manifest.get("schema_version") != "nalu.visual-continuity-manifest/v1":
        failures.append("MANIFEST_SCHEMA_INVALID")
    recorded_digest = str(manifest.get("manifest_sha256") or "")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if not recorded_digest or canonical_sha256(body) != recorded_digest:
        failures.append("MANIFEST_DIGEST_MISMATCH")
    if manifest.get("production_package_sha256") != production_package_sha256:
        failures.append("MANIFEST_PACKAGE_BINDING_MISMATCH")
    if manifest.get("final_master_sha256") != master_sha256:
        failures.append("MANIFEST_MASTER_BINDING_MISMATCH")
    if manifest.get("resolved_library_sha256") != resolved_library_sha256:
        failures.append("MANIFEST_LIBRARY_BINDING_MISMATCH")
    if canonical_sha256(resolved_library) != resolved_library_sha256:
        failures.append("PACKAGE_LIBRARY_DIGEST_MISMATCH")

    analyzer = manifest.get("analyzer") if isinstance(manifest.get("analyzer"), dict) else {}
    if analyzer.get("analyzer_id") not in APPROVED_ANALYZERS:
        failures.append("ANALYZER_NOT_APPROVED")
    if analyzer.get("local_analysis") is not True:
        failures.append("ANALYZER_LOCAL_EXECUTION_NOT_PROVEN")
    if not str(analyzer.get("version") or "").strip():
        failures.append("ANALYZER_VERSION_MISSING")
    if not SHA256_PATTERN.fullmatch(str(analyzer.get("model_sha256") or "")):
        failures.append("ANALYZER_MODEL_SHA_INVALID")
    if not str(analyzer.get("generated_at") or "").strip():
        failures.append("ANALYZER_GENERATED_AT_MISSING")

    declared_domains = manifest.get("required_domains")
    if not isinstance(declared_domains, list) or set(declared_domains) != set(REQUIRED_DOMAINS):
        failures.append("MANIFEST_REQUIRED_DOMAINS_INVALID")

    authorities = {
        str(entity.get("entity_id")): entity
        for entity in resolved_library
        if isinstance(entity, dict) and entity.get("entity_id")
    }
    try:
        frames = _decoded_frames(master_path)
    except (av.FFmpegError, OSError, ValueError):
        frames = []
        failures.append("FRAME_MASTER_DECODE_ERROR")
    if not frames:
        failures.append("FRAME_MASTER_DECODE_EMPTY")
    master_duration = frames[-1]["time_seconds"] if frames else 0.0

    shots = manifest.get("shots")
    if not isinstance(shots, list) or not shots:
        shots = []
        failures.append("SHOT_EVIDENCE_MISSING")
    shot_results: list[dict[str, Any]] = []
    previous_end = 0.0
    for index, shot in enumerate(shots, start=1):
        shot_failures: list[str] = []
        shot_id = str(shot.get("shot_id") or f"ROW-{index}")
        start = shot.get("start_seconds")
        end = shot.get("end_seconds")
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (start, end)
        ):
            shot_failures.append("SHOT_TIMELINE_INVALID")
            start_value = end_value = 0.0
        else:
            start_value = float(start)
            end_value = float(end)
            if start_value < previous_end - 0.05 or end_value <= start_value:
                shot_failures.append("SHOT_TIMELINE_INVALID")
            if end_value > master_duration + 0.25:
                shot_failures.append("SHOT_EXCEEDS_MASTER_DURATION")
            previous_end = max(previous_end, end_value)

        evidence_rows = shot.get("evidence_frames")
        if not isinstance(evidence_rows, list) or not evidence_rows:
            evidence_rows = []
            shot_failures.append("FRAME_EVIDENCE_MISSING")
        evidence_results: list[dict[str, Any]] = []
        verified_frame_hashes: set[str] = set()
        for evidence in evidence_rows:
            time_value = evidence.get("time_seconds")
            declared_sha = str(evidence.get("frame_sha256") or "")
            if not isinstance(time_value, (int, float)) or isinstance(time_value, bool):
                shot_failures.append("FRAME_TIME_INVALID")
                continue
            time_value = float(time_value)
            if time_value < start_value - 0.05 or time_value > end_value + 0.05:
                shot_failures.append("FRAME_TIME_OUTSIDE_SHOT")
            nearest = min(
                frames,
                key=lambda frame: abs(frame["time_seconds"] - time_value),
                default=None,
            )
            if nearest is None or abs(nearest["time_seconds"] - time_value) > 0.15:
                shot_failures.append("FRAME_DECODED_SAMPLE_MISSING")
                actual_sha = None
                actual_time = None
            else:
                actual_sha = nearest["frame_sha256"]
                actual_time = nearest["time_seconds"]
                if declared_sha != actual_sha:
                    shot_failures.append("FRAME_SHA_MISMATCH")
                else:
                    verified_frame_hashes.add(declared_sha)
            evidence_results.append(
                {
                    "requested_time_seconds": time_value,
                    "decoded_time_seconds": actual_time,
                    "declared_frame_sha256": declared_sha,
                    "decoded_frame_sha256": actual_sha,
                    "status": "PASS" if declared_sha == actual_sha else "FAIL",
                }
            )

        checks = shot.get("checks")
        if not isinstance(checks, list):
            checks = []
            shot_failures.append("SHOT_CHECKS_MISSING")
        check_results: list[dict[str, Any]] = []
        observed_domains: set[str] = set()
        for check in checks:
            domain = str(check.get("domain") or "")
            check_failures: list[str] = []
            if domain not in REQUIRED_DOMAINS:
                check_failures.append("CHECK_DOMAIN_INVALID")
                domain = "unknown"
            else:
                observed_domains.add(domain)
            frame_sha = str(check.get("source_frame_sha256") or "")
            if frame_sha not in verified_frame_hashes:
                check_failures.append(_domain_failure(domain, "FRAME_NOT_VERIFIED"))
            expected = str(check.get("expected") or "").strip()
            observed = str(check.get("observed") or "").strip()
            if not expected or not observed:
                check_failures.append(_domain_failure(domain, "VALUE_MISSING"))
            elif expected != observed:
                check_failures.append(_domain_failure(domain, "VALUE_MISMATCH"))
            confidence = check.get("confidence")
            threshold = MINIMUM_CONFIDENCE.get(domain, 1.0)
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not 0 <= float(confidence) <= 1
            ):
                check_failures.append(_domain_failure(domain, "CONFIDENCE_INVALID"))
                confidence_value = 0.0
            else:
                confidence_value = float(confidence)
                if confidence_value < threshold:
                    check_failures.append(_domain_failure(domain, "CONFIDENCE_BELOW_THRESHOLD"))

            subject_id = str(check.get("subject_id") or "")
            confirmed_revision = check.get("confirmed_revision")
            authority = authorities.get(subject_id)
            if domain in {"identity", "wardrobe"}:
                if authority is None or authority.get("kind") != "character":
                    check_failures.append(_domain_failure(domain, "AUTHORITY_MISSING"))
                elif confirmed_revision != authority.get("confirmed_revision"):
                    check_failures.append(_domain_failure(domain, "AUTHORITY_REVISION_MISMATCH"))
                elif domain == "identity" and expected != authority.get("stable_name"):
                    check_failures.append("IDENTITY_EXPECTED_AUTHORITY_MISMATCH")
                elif domain == "wardrobe":
                    revision = authority.get("revision") or {}
                    attributes = revision.get("attributes") or {}
                    wardrobe = attributes.get("wardrobe") or []
                    if expected not in wardrobe:
                        check_failures.append("WARDROBE_EXPECTED_AUTHORITY_MISMATCH")
            if domain == "props" and subject_id:
                if authority is None or authority.get("kind") != "prop":
                    check_failures.append("PROP_AUTHORITY_MISSING")
                elif confirmed_revision != authority.get("confirmed_revision"):
                    check_failures.append("PROP_AUTHORITY_REVISION_MISMATCH")
                elif expected != authority.get("stable_name"):
                    check_failures.append("PROP_EXPECTED_AUTHORITY_MISMATCH")

            computed_status = "FAIL" if check_failures else "PASS"
            if check.get("status") != computed_status:
                check_failures.append(_domain_failure(domain, "DECLARED_STATUS_MISMATCH"))
                computed_status = "FAIL"
            shot_failures.extend(check_failures)
            check_results.append(
                {
                    "domain": domain,
                    "subject_id": subject_id or None,
                    "confirmed_revision": confirmed_revision,
                    "expected": expected,
                    "observed": observed,
                    "confidence": confidence_value,
                    "minimum_confidence": threshold,
                    "source_frame_sha256": frame_sha,
                    "status": computed_status,
                    "failures": sorted(set(check_failures)),
                }
            )
        for domain in REQUIRED_DOMAINS:
            if domain not in observed_domains:
                shot_failures.append(_domain_failure(domain, "EVIDENCE_MISSING"))
        failures.extend(shot_failures)
        shot_results.append(
            {
                "shot_id": shot_id,
                "start_seconds": start_value,
                "end_seconds": end_value,
                "evidence_frames": evidence_results,
                "checks": check_results,
                "status": "FAIL" if shot_failures else "PASS",
                "failures": sorted(set(shot_failures)),
            }
        )

    domain_results = {
        domain: {
            "status": (
                "FAIL"
                if any(
                    failure.startswith("PROP_" if domain == "props" else domain.upper() + "_")
                    for failure in failures
                )
                else "PASS"
            ),
            "minimum_confidence": MINIMUM_CONFIDENCE[domain],
            "check_count": sum(
                check["domain"] == domain
                for shot in shot_results
                for check in shot["checks"]
            ),
        }
        for domain in REQUIRED_DOMAINS
    }
    return {
        "status": "FAIL" if failures else "PASS",
        "manifest_sha256": recorded_digest or None,
        "analyzer": analyzer,
        "decoded_frame_count": len(frames),
        "shot_count": len(shot_results),
        "passed_shot_count": sum(shot["status"] == "PASS" for shot in shot_results),
        "domain_results": domain_results,
        "shots": shot_results,
        "failures": sorted(set(failures)),
    }
