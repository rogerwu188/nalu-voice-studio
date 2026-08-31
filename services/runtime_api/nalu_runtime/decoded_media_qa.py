from __future__ import annotations

import hashlib
import math
import struct
from itertools import pairwise
from pathlib import Path
from typing import Any

import av

from .media_structure_qa import webvtt_cues


def _plane_rows(frame: av.VideoFrame) -> tuple[bytes, int, int]:
    gray = frame.reformat(format="gray8")
    plane = gray.planes[0]
    raw = bytes(plane)
    pixels = b"".join(
        raw[row * plane.line_size : row * plane.line_size + gray.width]
        for row in range(gray.height)
    )
    return pixels, gray.width, gray.height


def inspect_decoded_video(path: Path) -> dict[str, Any]:
    failures: list[str] = []
    frame_count = 0
    unique_signatures: set[str] = set()
    prior_signature: str | None = None
    identical_run = max_identical_run = 0
    black_run = max_black_run = 0
    timestamps: list[float] = []
    dimensions: set[tuple[int, int]] = set()
    average_rate: float | None = None
    try:
        with av.open(str(path), mode="r") as container:
            if not container.streams.video:
                failures.append("VIDEO_STREAM_MISSING")
            else:
                stream = container.streams.video[0]
                average_rate = float(stream.average_rate) if stream.average_rate else None
                for frame in container.decode(stream):
                    pixels, width, height = _plane_rows(frame)
                    dimensions.add((width, height))
                    signature = hashlib.sha256(pixels).hexdigest()
                    unique_signatures.add(signature)
                    frame_count += 1
                    if signature == prior_signature:
                        identical_run += 1
                    else:
                        identical_run = 1
                    prior_signature = signature
                    max_identical_run = max(max_identical_run, identical_run)
                    mean_luma = sum(pixels) / len(pixels) if pixels else 0.0
                    black_run = black_run + 1 if mean_luma < 8.0 else 0
                    max_black_run = max(max_black_run, black_run)
                    if frame.time is not None:
                        timestamps.append(float(frame.time))
    except (av.FFmpegError, OSError, ValueError) as exc:
        failures.append(f"VIDEO_DECODE_ERROR:{type(exc).__name__}")

    if frame_count < 2:
        failures.append("VIDEO_INSUFFICIENT_FRAMES")
    if len(dimensions) > 1:
        failures.append("VIDEO_DIMENSIONS_CHANGE")
    if dimensions and any(width % 2 or height % 2 for width, height in dimensions):
        failures.append("VIDEO_DIMENSIONS_NOT_EVEN")
    unique_ratio = len(unique_signatures) / frame_count if frame_count else 0.0
    if frame_count >= 2 and unique_ratio < 0.15:
        failures.append("VIDEO_FRAME_REPEAT_EXCESSIVE")
    fps = average_rate or (
        (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        if len(timestamps) > 1 and timestamps[-1] > timestamps[0]
        else None
    )
    repeat_limit = max(5, math.ceil((fps or 10.0) * 1.5))
    black_limit = max(5, math.ceil((fps or 10.0) * 2.0))
    if max_identical_run > repeat_limit:
        failures.append("VIDEO_IDENTICAL_RUN_TOO_LONG")
    if max_black_run > black_limit:
        failures.append("VIDEO_BLACK_RUN_TOO_LONG")
    timestamp_gaps = [right - left for left, right in pairwise(timestamps)]
    if any(gap <= 0 for gap in timestamp_gaps):
        failures.append("VIDEO_TIMESTAMPS_NOT_MONOTONIC")
    max_timestamp_gap = max(timestamp_gaps, default=0.0)
    expected_gap = 1 / fps if fps and fps > 0 else 0.1
    if max_timestamp_gap > max(0.5, expected_gap * 3.0):
        failures.append("VIDEO_TIMELINE_GAP")
    return {
        "status": "PASS" if not failures else "FAIL",
        "codec": None,
        "frame_count": frame_count,
        "unique_frame_ratio": round(unique_ratio, 6),
        "max_identical_run_frames": max_identical_run,
        "max_black_run_frames": max_black_run,
        "average_fps": round(fps, 6) if fps else None,
        "max_timestamp_gap_seconds": round(max_timestamp_gap, 6),
        "dimensions": [list(value) for value in sorted(dimensions)],
        "failures": sorted(set(failures)),
    }


def inspect_decoded_audio(path: Path) -> dict[str, Any]:
    failures: list[str] = []
    sample_rate = 16000
    window_samples = sample_rate // 50
    sample_count = clipped_count = 0
    window_count = window_position = 0
    window_energy = 0
    voiced_windows: list[tuple[float, float]] = []
    silence_run = max_silence_run = 0
    try:
        with av.open(str(path), mode="r") as container:
            if not container.streams.audio:
                failures.append("AUDIO_STREAM_MISSING")
            else:
                stream = container.streams.audio[0]
                resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
                decoded = container.decode(stream)
                for source_frame in decoded:
                    for frame in resampler.resample(source_frame):
                        raw = bytes(frame.planes[0])[: frame.samples * 2]
                        for (sample,) in struct.iter_unpack("=h", raw):
                            sample_count += 1
                            clipped_count += int(abs(sample) >= 32760)
                            window_energy += sample * sample
                            window_position += 1
                            if window_position < window_samples:
                                continue
                            rms = math.sqrt(window_energy / window_position)
                            start = window_count * window_samples / sample_rate
                            end = start + window_position / sample_rate
                            if rms >= 300.0:
                                voiced_windows.append((start, end))
                                silence_run = 0
                            else:
                                silence_run += 1
                                max_silence_run = max(max_silence_run, silence_run)
                            window_count += 1
                            window_position = 0
                            window_energy = 0
                for frame in resampler.resample(None):
                    raw = bytes(frame.planes[0])[: frame.samples * 2]
                    for (sample,) in struct.iter_unpack("=h", raw):
                        sample_count += 1
                        clipped_count += int(abs(sample) >= 32760)
    except (av.FFmpegError, OSError, ValueError) as exc:
        failures.append(f"AUDIO_DECODE_ERROR:{type(exc).__name__}")

    duration = sample_count / sample_rate
    voiced_duration = sum(end - start for start, end in voiced_windows)
    voiced_ratio = voiced_duration / duration if duration else 0.0
    clipping_ratio = clipped_count / sample_count if sample_count else 0.0
    if sample_count == 0:
        failures.append("AUDIO_HAS_NO_DECODED_SAMPLES")
    elif voiced_ratio < 0.05:
        failures.append("AUDIO_VOICE_ACTIVITY_TOO_LOW")
    if clipping_ratio > 0.01:
        failures.append("AUDIO_CLIPPING_EXCESSIVE")
    max_silence_seconds = max_silence_run * window_samples / sample_rate
    if duration > 3.0 and max_silence_seconds > 3.0:
        failures.append("AUDIO_SILENCE_RUN_TOO_LONG")
    return {
        "status": "PASS" if not failures else "FAIL",
        "sample_rate": sample_rate,
        "decoded_sample_count": sample_count,
        "duration_seconds": round(duration, 6),
        "voiced_ratio": round(voiced_ratio, 6),
        "clipping_ratio": round(clipping_ratio, 8),
        "max_silence_seconds": round(max_silence_seconds, 6),
        "voiced_intervals": [[round(start, 3), round(end, 3)] for start, end in voiced_windows],
        "failures": sorted(set(failures)),
    }


def inspect_caption_speech_alignment(
    captions_path: Path, voiced_intervals: list[list[float]]
) -> dict[str, Any]:
    cues = webvtt_cues(captions_path)
    aligned = 0
    for cue_start, cue_end in cues:
        if any(max(cue_start, start) < min(cue_end, end) for start, end in voiced_intervals):
            aligned += 1
    ratio = aligned / len(cues) if cues else 0.0
    failures: list[str] = []
    if not cues:
        failures.append("CAPTION_ALIGNMENT_HAS_NO_VALID_CUES")
    elif ratio < 0.8:
        failures.append("CAPTION_SPEECH_ALIGNMENT_TOO_LOW")
    return {
        "status": "PASS" if not failures else "FAIL",
        "cue_count": len(cues),
        "aligned_cue_count": aligned,
        "aligned_ratio": round(ratio, 6),
        "semantic_asr_verified": False,
        "failures": failures,
    }


def inspect_decoded_media(master_path: Path, captions_path: Path) -> dict[str, Any]:
    video = inspect_decoded_video(master_path)
    audio = inspect_decoded_audio(master_path)
    alignment = inspect_caption_speech_alignment(captions_path, audio.get("voiced_intervals") or [])
    failures = [
        *("video:" + value for value in video["failures"]),
        *("audio:" + value for value in audio["failures"]),
        *("alignment:" + value for value in alignment["failures"]),
    ]
    return {
        "video": video,
        "audio": audio,
        "caption_speech_alignment": alignment,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
