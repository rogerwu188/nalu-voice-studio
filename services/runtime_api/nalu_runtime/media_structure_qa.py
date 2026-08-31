from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path
from typing import Any


class MediaStructureError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _boxes(data: bytes, start: int = 0, end: int | None = None) -> list[tuple[str, int, int]]:
    end = len(data) if end is None else end
    offset = start
    boxes: list[tuple[str, int, int]] = []
    while offset < end:
        if end - offset < 8:
            raise MediaStructureError("MP4_BOX_HEADER_TRUNCATED")
        size = struct.unpack_from(">I", data, offset)[0]
        box_type = data[offset + 4 : offset + 8].decode("ascii", errors="replace")
        header_size = 8
        if size == 1:
            if end - offset < 16:
                raise MediaStructureError("MP4_EXTENDED_BOX_HEADER_TRUNCATED")
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            raise MediaStructureError(f"MP4_BOX_SIZE_INVALID:{box_type}")
        boxes.append((box_type, offset + header_size, offset + size))
        offset += size
    return boxes


def inspect_mp4(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    failures: list[str] = []
    if len(data) < 24:
        return {
            "status": "FAIL",
            "duration_seconds": None,
            "top_level_boxes": [],
            "failures": ["MP4_FILE_TOO_SMALL"],
        }
    try:
        top = _boxes(data)
    except MediaStructureError as exc:
        return {
            "status": "FAIL",
            "duration_seconds": None,
            "top_level_boxes": [],
            "failures": [str(exc)],
        }
    types = [box_type for box_type, _, _ in top]
    if not types or types[0] != "ftyp":
        failures.append("MP4_FTYP_MISSING_OR_NOT_FIRST")
    if "moov" not in types:
        failures.append("MP4_MOOV_MISSING")
    if "mdat" not in types:
        failures.append("MP4_MDAT_MISSING")
    if "moov" in types and "mdat" in types and types.index("moov") > types.index("mdat"):
        failures.append("MP4_NOT_FAST_START")

    duration_seconds: float | None = None
    moov = next((box for box in top if box[0] == "moov"), None)
    if moov is not None:
        try:
            children = _boxes(data, moov[1], moov[2])
            mvhd = next((box for box in children if box[0] == "mvhd"), None)
            if mvhd is None:
                failures.append("MP4_MVHD_MISSING")
            else:
                payload = data[mvhd[1] : mvhd[2]]
                version = payload[0] if payload else -1
                if version == 0 and len(payload) >= 20:
                    timescale = struct.unpack_from(">I", payload, 12)[0]
                    duration = struct.unpack_from(">I", payload, 16)[0]
                elif version == 1 and len(payload) >= 32:
                    timescale = struct.unpack_from(">I", payload, 20)[0]
                    duration = struct.unpack_from(">Q", payload, 24)[0]
                else:
                    timescale, duration = 0, 0
                    failures.append("MP4_MVHD_INVALID")
                if timescale <= 0 or duration <= 0:
                    failures.append("MP4_DURATION_INVALID")
                else:
                    duration_seconds = duration / timescale
        except MediaStructureError as exc:
            failures.append(str(exc))
    return {
        "status": "PASS" if not failures else "FAIL",
        "duration_seconds": duration_seconds,
        "top_level_boxes": types,
        "failures": failures,
    }


_TIMESTAMP = re.compile(r"^(?:(\d{2,}):)?(\d{2}):(\d{2})\.(\d{3})$")


def _seconds(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise MediaStructureError("WEBVTT_TIMESTAMP_INVALID:" + value.strip())
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int(match.group(4))
    if minutes >= 60 or seconds >= 60:
        raise MediaStructureError("WEBVTT_TIMESTAMP_RANGE_INVALID:" + value.strip())
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def inspect_webvtt(path: Path, *, media_duration_seconds: float | None) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        return {"status": "FAIL", "cue_count": 0, "failures": ["WEBVTT_NOT_UTF8"]}
    failures: list[str] = []
    lines = text.splitlines()
    if not lines or lines[0].strip() != "WEBVTT":
        failures.append("WEBVTT_HEADER_MISSING")
    cues: list[tuple[float, float]] = []
    for line in lines[1:]:
        if "-->" not in line:
            continue
        left, right_with_settings = line.split("-->", 1)
        right = right_with_settings.strip().split()[0] if right_with_settings.strip() else ""
        try:
            start, end = _seconds(left), _seconds(right)
        except MediaStructureError as exc:
            failures.append(str(exc))
            continue
        if end <= start:
            failures.append("WEBVTT_CUE_DURATION_INVALID")
        if cues and start < cues[-1][1] - 0.001:
            failures.append("WEBVTT_CUES_OVERLAP_OR_OUT_OF_ORDER")
        if media_duration_seconds is not None and end > media_duration_seconds + 0.25:
            failures.append("WEBVTT_CUE_EXCEEDS_MASTER_DURATION")
        cues.append((start, end))
    if not cues:
        failures.append("WEBVTT_HAS_NO_CUES")
    return {
        "status": "PASS" if not failures else "FAIL",
        "cue_count": len(cues),
        "first_cue_seconds": cues[0][0] if cues else None,
        "last_cue_seconds": cues[-1][1] if cues else None,
        "failures": sorted(set(failures)),
    }


def webvtt_cues(path: Path) -> list[tuple[float, float]]:
    """Return valid cue intervals for decoded-media alignment checks."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return []
    cues: list[tuple[float, float]] = []
    for line in lines[1:]:
        if "-->" not in line:
            continue
        left, right_with_settings = line.split("-->", 1)
        right = right_with_settings.strip().split()[0] if right_with_settings.strip() else ""
        try:
            start, end = _seconds(left), _seconds(right)
        except MediaStructureError:
            continue
        if end > start:
            cues.append((start, end))
    return cues


def webvtt_transcript(path: Path) -> str:
    """Return visible cue text without identifiers, timing rows or WebVTT metadata."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError):
        return ""
    result: list[str] = []
    in_note = False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("NOTE"):
            in_note = True
            continue
        if in_note:
            if not stripped:
                in_note = False
            continue
        if not stripped or "-->" in stripped or stripped.isdigit():
            continue
        result.append(re.sub(r"<[^>]+>", "", stripped))
    return "".join(result)
