from __future__ import annotations

import hashlib
import json
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import av

from .media_structure_qa import webvtt_transcript


def canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalized_speech_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def inspect_semantic_asr(
    captions_path: Path,
    *,
    transcript: str,
    segments: list[dict[str, Any]],
    recognizer_id: str,
    locale: str,
    local_recognition: bool,
    media_duration_seconds: float,
) -> dict[str, Any]:
    expected = webvtt_transcript(captions_path)
    expected_normalized = normalized_speech_text(expected)
    actual_normalized = normalized_speech_text(transcript)
    failures: list[str] = []
    if not expected_normalized:
        failures.append("ASR_EXPECTED_CAPTION_TEXT_MISSING")
    if not actual_normalized:
        failures.append("ASR_TRANSCRIPT_EMPTY")
    if not local_recognition:
        failures.append("ASR_LOCAL_RECOGNITION_NOT_PROVEN")
    if locale.casefold().replace("_", "-") not in {"zh-cn", "zh-hans-cn"}:
        failures.append("ASR_LOCALE_NOT_SIMPLIFIED_MANDARIN")
    if recognizer_id not in {
        "apple-speech-on-device",
        "qingshan-faster-whisper-local",
    }:
        failures.append("ASR_RECOGNIZER_NOT_APPROVED")
    previous_end = 0.0
    for segment in segments:
        start = float(segment.get("start_seconds") or 0)
        end = float(segment.get("end_seconds") or 0)
        text = normalized_speech_text(str(segment.get("text") or ""))
        if start < previous_end - 0.001 or end <= start:
            failures.append("ASR_SEGMENTS_OVERLAP_OR_INVALID")
        if end > media_duration_seconds + 0.25:
            failures.append("ASR_SEGMENT_EXCEEDS_MASTER_DURATION")
        if not text:
            failures.append("ASR_SEGMENT_TEXT_EMPTY")
        previous_end = max(previous_end, end)
    if not segments:
        failures.append("ASR_SEGMENTS_MISSING")
    matcher = SequenceMatcher(None, expected_normalized, actual_normalized)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    recall = matched / len(expected_normalized) if expected_normalized else 0.0
    similarity = matcher.ratio() if expected_normalized or actual_normalized else 0.0
    if expected_normalized and recall < 0.8:
        failures.append("ASR_TRANSCRIPT_RECALL_BELOW_THRESHOLD")
    return {
        "status": "PASS" if not failures else "FAIL",
        "expected_caption_text": expected,
        "transcript": transcript,
        "expected_normalized_sha256": hashlib.sha256(
            expected_normalized.encode("utf-8")
        ).hexdigest(),
        "transcript_normalized_sha256": hashlib.sha256(
            actual_normalized.encode("utf-8")
        ).hexdigest(),
        "recall": round(recall, 6),
        "similarity": round(similarity, 6),
        "minimum_recall": 0.8,
        "segment_count": len(segments),
        "recognizer_id": recognizer_id,
        "locale": locale,
        "local_recognition": local_recognition,
        "failures": sorted(set(failures)),
    }


def _decoded_frame_evidence(master_path: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    with av.open(str(master_path), mode="r") as container:
        if not container.streams.video:
            return evidence
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
            evidence.append(
                {
                    "time_seconds": float(frame.time),
                    "frame_sha256": hashlib.sha256(pixels).hexdigest(),
                    "mean_luma": sum(pixels) / len(pixels) if pixels else 0.0,
                }
            )
    return evidence


def inspect_shot_boundaries(
    master_path: Path,
    manifest_path: Path,
    *,
    production_package_sha256: str,
    media_duration_seconds: float,
) -> dict[str, Any]:
    failures: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        manifest = {}
        failures.append("SHOT_MANIFEST_UNREADABLE")
    if manifest.get("schema_version") != "nalu.shot-boundary-manifest/v1":
        failures.append("SHOT_MANIFEST_SCHEMA_INVALID")
    recorded_digest = str(manifest.get("manifest_sha256") or "")
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if not recorded_digest or canonical_sha256(manifest_body) != recorded_digest:
        failures.append("SHOT_MANIFEST_DIGEST_MISMATCH")
    if manifest.get("production_package_sha256") != production_package_sha256:
        failures.append("SHOT_MANIFEST_PACKAGE_BINDING_MISMATCH")
    units = manifest.get("units") or []
    if not isinstance(units, list) or not units:
        units = []
        failures.append("SHOT_MANIFEST_UNITS_MISSING")
    try:
        frames = _decoded_frame_evidence(master_path)
    except (av.FFmpegError, OSError, ValueError):
        frames = []
        failures.append("SHOT_BOUNDARY_VIDEO_DECODE_ERROR")
    if not frames:
        failures.append("SHOT_BOUNDARY_FRAMES_MISSING")
    previous_end = 0.0
    for index, unit in enumerate(units):
        unit_id = str(unit.get("unit_id") or "")
        start = float(unit.get("start_seconds") or 0)
        end = float(unit.get("end_seconds") or 0)
        if not unit_id or end <= start or start < previous_end - 0.05:
            failures.append("SHOT_MANIFEST_UNIT_TIMELINE_INVALID")
        if index and abs(start - previous_end) > 0.25:
            failures.append("SHOT_MANIFEST_UNIT_BOUNDARY_GAP")
        if end > media_duration_seconds + 0.25:
            failures.append("SHOT_MANIFEST_UNIT_EXCEEDS_MASTER")
        previous_end = max(previous_end, end)
        if index == 0:
            continue
        contract = unit.get("incoming_transition_contract")
        contract_digest = str(unit.get("incoming_transition_contract_sha256") or "")
        if not isinstance(contract, dict) or canonical_sha256(contract) != contract_digest:
            failures.append("SHOT_TRANSITION_CONTRACT_DIGEST_MISMATCH")
            contract = {}
        transition_type = contract.get("transition_type")
        visual_change_required = contract.get("visual_change_required")
        audio_bridge = contract.get("audio_bridge")
        if transition_type not in {
            "hard_cut",
            "crossfade",
            "match_cut",
            "dip_to_black",
            "continuous_take",
        }:
            failures.append("SHOT_TRANSITION_TYPE_INVALID")
        if not isinstance(visual_change_required, bool):
            failures.append("SHOT_TRANSITION_VISUAL_CHANGE_CONTRACT_MISSING")
        if not isinstance(audio_bridge, str) or not audio_bridge.strip():
            failures.append("SHOT_TRANSITION_AUDIO_BRIDGE_CONTRACT_MISSING")
        left = max(
            (frame for frame in frames if frame["time_seconds"] < start),
            key=lambda frame: frame["time_seconds"],
            default=None,
        )
        right = min(
            (frame for frame in frames if frame["time_seconds"] >= start),
            key=lambda frame: frame["time_seconds"],
            default=None,
        )
        boundary_failures: list[str] = []
        if left is None or right is None:
            boundary_failures.append("BOUNDARY_SIDE_FRAME_MISSING")
        else:
            gap = right["time_seconds"] - left["time_seconds"]
            if gap > 0.5:
                boundary_failures.append("BOUNDARY_DECODED_FRAME_GAP")
            if left["mean_luma"] < 8 or right["mean_luma"] < 8:
                boundary_failures.append("BOUNDARY_BLACK_FRAME")
            if visual_change_required is True and (
                left["frame_sha256"] == right["frame_sha256"]
            ):
                boundary_failures.append("BOUNDARY_EXPECTED_VISUAL_CHANGE_MISSING")
        if boundary_failures:
            failures.extend(boundary_failures)
        results.append(
            {
                "boundary_id": f"{units[index - 1].get('unit_id')}->{unit_id}",
                "cut_seconds": start,
                "transition_contract_sha256": contract_digest,
                "transition_type": transition_type,
                "visual_change_required": visual_change_required,
                "audio_bridge": audio_bridge,
                "left_frame": left,
                "right_frame": right,
                "status": "FAIL" if boundary_failures else "PASS",
                "failures": boundary_failures,
            }
        )
    return {
        "status": "PASS" if not failures else "FAIL",
        "manifest_sha256": recorded_digest or None,
        "unit_count": len(units),
        "boundary_count": max(0, len(units) - 1),
        "passed_boundary_count": sum(row["status"] == "PASS" for row in results),
        "boundaries": results,
        "failures": sorted(set(failures)),
    }
