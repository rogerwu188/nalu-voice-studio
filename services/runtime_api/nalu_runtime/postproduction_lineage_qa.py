from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from pathlib import Path
from typing import Any

import av

REQUIRED_AUDIO_LAYERS = {"dialogue", "ambience", "foley", "music", "sfx"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(exports_root: Path, relative_path: str) -> Path | None:
    relative = Path(relative_path.replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    unresolved = exports_root / relative
    try:
        resolved = unresolved.resolve(strict=True)
    except OSError:
        return None
    if (
        unresolved.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(exports_root.resolve())
    ):
        return None
    return resolved


def _media_stream_facts(path: Path) -> dict[str, Any]:
    failures: list[str] = []
    dimensions: set[tuple[int, int]] = set()
    pixel_formats: set[str] = set()
    video_times: list[float] = []
    fps: float | None = None
    audio_rate: int | None = None
    audio_channels: int | None = None
    audio_times: list[float] = []
    audio_samples = 0
    try:
        with av.open(str(path), mode="r") as container:
            if not container.streams.video:
                failures.append("VIDEO_STREAM_MISSING")
            else:
                stream = container.streams.video[0]
                fps = float(stream.average_rate) if stream.average_rate else None
                for frame in container.decode(stream):
                    dimensions.add((frame.width, frame.height))
                    pixel_formats.add(frame.format.name)
                    if frame.time is not None:
                        video_times.append(float(frame.time))
        with av.open(str(path), mode="r") as container:
            if not container.streams.audio:
                failures.append("AUDIO_STREAM_MISSING")
            else:
                stream = container.streams.audio[0]
                for frame in container.decode(stream):
                    audio_rate = int(frame.sample_rate)
                    audio_channels = len(frame.layout.channels)
                    audio_samples += int(frame.samples)
                    if frame.time is not None:
                        audio_times.append(float(frame.time))
    except (av.FFmpegError, OSError, ValueError) as exc:
        failures.append(f"DECODE_ERROR:{type(exc).__name__}")

    if not video_times:
        failures.append("VIDEO_FRAMES_MISSING")
    if not audio_samples or not audio_rate:
        failures.append("AUDIO_SAMPLES_MISSING")
    duration = max(
        (video_times[-1] + (1 / fps if fps else 0.0)) if video_times else 0.0,
        audio_samples / audio_rate if audio_rate else 0.0,
    )
    return {
        "status": "PASS" if not failures else "FAIL",
        "dimensions": [list(value) for value in sorted(dimensions)],
        "pixel_formats": sorted(pixel_formats),
        "fps": round(fps, 6) if fps else None,
        "video_start_seconds": round(video_times[0], 6) if video_times else None,
        "audio_start_seconds": round(audio_times[0], 6) if audio_times else None,
        "audio_sample_rate_hz": audio_rate,
        "audio_channels": audio_channels,
        "duration_seconds": round(duration, 6),
        "failures": failures,
    }


def _audio_signature(path: Path) -> dict[str, Any]:
    target_rate = 16000
    window_samples = target_rate // 50
    energy_windows: list[float] = []
    sample_count = 0
    peak = 0
    clipped_sample_count = 0
    window_energy = 0
    window_position = 0
    source_rates: set[int] = set()
    source_channels: set[int] = set()
    failures: list[str] = []
    try:
        with av.open(str(path), mode="r") as container:
            if not container.streams.audio:
                failures.append("AUDIO_STREAM_MISSING")
            else:
                stream = container.streams.audio[0]
                resampler = av.AudioResampler(format="s16", layout="mono", rate=target_rate)
                for source_frame in container.decode(stream):
                    source_rates.add(int(source_frame.sample_rate))
                    source_channels.add(len(source_frame.layout.channels))
                    for frame in resampler.resample(source_frame):
                        raw = bytes(frame.planes[0])[: frame.samples * 2]
                        for (sample,) in struct.iter_unpack("=h", raw):
                            sample_count += 1
                            peak = max(peak, abs(sample))
                            if abs(sample) >= 32760:
                                clipped_sample_count += 1
                            window_energy += sample * sample
                            window_position += 1
                            if window_position == window_samples:
                                energy_windows.append(math.sqrt(window_energy / window_position))
                                window_energy = 0
                                window_position = 0
                for frame in resampler.resample(None):
                    raw = bytes(frame.planes[0])[: frame.samples * 2]
                    for (sample,) in struct.iter_unpack("=h", raw):
                        sample_count += 1
                        peak = max(peak, abs(sample))
                        if abs(sample) >= 32760:
                            clipped_sample_count += 1
                        window_energy += sample * sample
                        window_position += 1
                        if window_position == window_samples:
                            energy_windows.append(math.sqrt(window_energy / window_position))
                            window_energy = 0
                            window_position = 0
    except (av.FFmpegError, OSError, ValueError) as exc:
        failures.append(f"AUDIO_DECODE_ERROR:{type(exc).__name__}")
    if window_position:
        energy_windows.append(math.sqrt(window_energy / window_position))
    if not sample_count:
        failures.append("AUDIO_SAMPLES_MISSING")
    quantized_db = [
        round(20 * math.log10(max(value, 1.0) / 32768.0) * 2) / 2 for value in energy_windows
    ]
    encoded = json.dumps(quantized_db, separators=(",", ":")).encode("utf-8")
    mean_rms = (
        math.sqrt(sum(value * value for value in energy_windows) / len(energy_windows))
        if energy_windows
        else 0.0
    )
    return {
        "status": "PASS" if not failures else "FAIL",
        "source_sample_rates_hz": sorted(source_rates),
        "source_channel_counts": sorted(source_channels),
        "decoded_sample_rate_hz": target_rate,
        "decoded_sample_count": sample_count,
        "duration_seconds": round(sample_count / target_rate, 6),
        "mean_rms": round(mean_rms, 3),
        "peak": peak,
        "clipped_sample_count": clipped_sample_count,
        "energy_fingerprint": hashlib.sha256(encoded).hexdigest(),
        "energy_windows": energy_windows,
        "failures": failures,
    }


def audio_energy_fingerprint(path: Path) -> str:
    """Return the deterministic decoded-audio fingerprint used by lineage manifests."""
    signature = _audio_signature(path)
    if signature["status"] != "PASS":
        raise ValueError(f"audio cannot be fingerprinted: {signature['failures']}")
    return str(signature["energy_fingerprint"])


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    left = left[:size]
    right = right[:size]
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator


def inspect_postproduction_lineage(
    manifest_path: Path,
    *,
    exports_root: Path,
    production_package_sha256: str,
    master_path: Path,
    master_sha256: str,
    captions_path: Path,
    captions_sha256: str,
) -> dict[str, Any]:
    failures: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        manifest = {}
        failures.append("MANIFEST_UNREADABLE")
    if manifest.get("schema_version") != "nalu.postproduction-lineage-manifest/v1":
        failures.append("MANIFEST_SCHEMA_INVALID")
    manifest_digest = str(manifest.get("manifest_sha256") or "")
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if not manifest_digest or canonical_sha256(manifest_body) != manifest_digest:
        failures.append("MANIFEST_DIGEST_MISMATCH")
    if manifest.get("production_package_sha256") != production_package_sha256:
        failures.append("MANIFEST_PACKAGE_BINDING_MISMATCH")
    if manifest.get("final_master_sha256") != master_sha256:
        failures.append("MANIFEST_MASTER_BINDING_MISMATCH")
    if manifest.get("captions_sha256") != captions_sha256:
        failures.append("MANIFEST_CAPTIONS_BINDING_MISMATCH")

    master_facts = _media_stream_facts(master_path)
    master_duration = float(master_facts.get("duration_seconds") or 0)
    timeline = manifest.get("timeline") if isinstance(manifest.get("timeline"), dict) else {}
    target_width = timeline.get("width")
    target_height = timeline.get("height")
    target_fps = timeline.get("frame_rate")
    target_pixel_format = timeline.get("pixel_format")
    shots = timeline.get("selected_shots") or []
    shot_results: list[dict[str, Any]] = []
    if not isinstance(shots, list) or not shots:
        shots = []
        failures.append("SHOT_SELECTION_MISSING")
    seen_shots: set[str] = set()
    previous_end = 0.0
    for index, shot in enumerate(shots, start=1):
        shot_failures: list[str] = []
        shot_id = str(shot.get("shot_id") or "")
        label = shot_id or f"ROW-{index}"
        if not shot_id:
            shot_failures.append("SHOT_ID_MISSING")
        elif shot_id in seen_shots:
            shot_failures.append("SHOT_ID_DUPLICATE")
        seen_shots.add(shot_id)
        if shot.get("admission_status") != "ADMITTED_FOR_ASSEMBLY":
            shot_failures.append("SHOT_NOT_ADMITTED_FOR_ASSEMBLY")
        if not str(shot.get("source_task_id") or "").strip():
            shot_failures.append("SHOT_SOURCE_TASK_ID_MISSING")
        receipt_sha = str(shot.get("source_receipt_sha256") or "")
        if not SHA256_PATTERN.fullmatch(receipt_sha):
            shot_failures.append("SHOT_SOURCE_RECEIPT_SHA_INVALID")
        source_path = _safe_file(exports_root, str(shot.get("source_relative_path") or ""))
        if source_path is None:
            shot_failures.append("SHOT_SOURCE_FILE_MISSING_OR_UNSAFE")
        elif file_sha256(source_path) != shot.get("source_sha256"):
            shot_failures.append("SHOT_SOURCE_SHA_MISMATCH")
        normalized_path = _safe_file(exports_root, str(shot.get("normalized_relative_path") or ""))
        normalized_facts: dict[str, Any] = {}
        if normalized_path is None:
            shot_failures.append("NORMALIZED_SEGMENT_MISSING_OR_UNSAFE")
        elif file_sha256(normalized_path) != shot.get("normalized_sha256"):
            shot_failures.append("NORMALIZED_SEGMENT_SHA_MISMATCH")
        else:
            normalized_facts = _media_stream_facts(normalized_path)
            if normalized_facts["status"] != "PASS":
                shot_failures.append("NORMALIZED_SEGMENT_DECODE_FAILED")
            if normalized_facts.get("dimensions") != [[target_width, target_height]]:
                shot_failures.append("NORMALIZED_DIMENSIONS_MISMATCH")
            if normalized_facts.get("pixel_formats") != [target_pixel_format]:
                shot_failures.append("NORMALIZED_PIXEL_FORMAT_MISMATCH")
            actual_fps = normalized_facts.get("fps")
            if (
                not isinstance(target_fps, (int, float))
                or not actual_fps
                or abs(actual_fps - target_fps) > 0.01
            ):
                shot_failures.append("NORMALIZED_FRAME_RATE_MISMATCH")
            if normalized_facts.get("audio_sample_rate_hz") != 48000:
                shot_failures.append("NORMALIZED_AUDIO_RATE_MISMATCH")
            if normalized_facts.get("audio_channels") != 2:
                shot_failures.append("NORMALIZED_AUDIO_CHANNELS_MISMATCH")
            for start_field in ("video_start_seconds", "audio_start_seconds"):
                start_value = normalized_facts.get(start_field)
                if start_value is None or abs(float(start_value)) > 0.05:
                    shot_failures.append("NORMALIZED_TIMESTAMPS_NOT_ZERO_BASED")
        start = shot.get("timeline_start_seconds")
        duration = shot.get("duration_seconds")
        source_in = shot.get("source_in_seconds")
        source_out = shot.get("source_out_seconds")
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (start, duration, source_in, source_out)
        ):
            shot_failures.append("SHOT_TIMELINE_VALUES_INVALID")
        else:
            start = float(start)
            duration = float(duration)
            if duration <= 0 or float(source_out) <= float(source_in):
                shot_failures.append("SHOT_DURATION_INVALID")
            if abs(start - previous_end) > 0.05:
                shot_failures.append("SHOT_TIMELINE_NOT_CONTIGUOUS")
            previous_end = max(previous_end, start + max(duration, 0))
            normalized_duration = float(normalized_facts.get("duration_seconds") or 0)
            if normalized_duration and abs(normalized_duration - duration) > 0.15:
                shot_failures.append("NORMALIZED_DURATION_MISMATCH")
        failures.extend(shot_failures)
        shot_results.append(
            {
                "shot_id": label,
                "normalized_media": normalized_facts,
                "status": "FAIL" if shot_failures else "PASS",
                "failures": sorted(set(shot_failures)),
            }
        )
    if master_duration and abs(previous_end - master_duration) > 0.25:
        failures.append("SHOT_TIMELINE_MASTER_DURATION_MISMATCH")

    audio = manifest.get("audio") if isinstance(manifest.get("audio"), dict) else {}
    if audio.get("sample_rate_hz") != 48000:
        failures.append("AUDIO_CONTRACT_SAMPLE_RATE_INVALID")
    if audio.get("channels") != 2:
        failures.append("AUDIO_CONTRACT_CHANNELS_INVALID")
    stems = audio.get("stems") or []
    stem_results: list[dict[str, Any]] = []
    seen_layers: set[str] = set()
    if not isinstance(stems, list):
        stems = []
    for stem in stems:
        layer = str(stem.get("layer") or "").casefold()
        stem_failures: list[str] = []
        if layer not in REQUIRED_AUDIO_LAYERS:
            stem_failures.append("STEM_LAYER_INVALID")
        elif layer in seen_layers:
            stem_failures.append("STEM_LAYER_DUPLICATE")
        seen_layers.add(layer)
        state = stem.get("state")
        facts: dict[str, Any] = {}
        if state == "omitted":
            if layer == "dialogue":
                stem_failures.append("DIALOGUE_STEM_CANNOT_BE_OMITTED")
            if len(str(stem.get("creative_omission_reason") or "").strip()) < 12:
                stem_failures.append("STEM_OMISSION_REASON_REQUIRED")
        elif state == "included":
            stem_path = _safe_file(exports_root, str(stem.get("relative_path") or ""))
            if stem_path is None:
                stem_failures.append("STEM_FILE_MISSING_OR_UNSAFE")
            elif file_sha256(stem_path) != stem.get("sha256"):
                stem_failures.append("STEM_SHA_MISMATCH")
            else:
                facts = _audio_signature(stem_path)
                if facts["status"] != "PASS":
                    stem_failures.append("STEM_DECODE_FAILED")
                if facts.get("source_sample_rates_hz") != [48000]:
                    stem_failures.append("STEM_SAMPLE_RATE_MISMATCH")
                if facts.get("source_channel_counts") != [2]:
                    stem_failures.append("STEM_CHANNELS_MISMATCH")
                if (
                    master_duration
                    and abs(float(facts["duration_seconds"]) - master_duration) > 0.2
                ):
                    stem_failures.append("STEM_DURATION_MISMATCH")
                if float(facts.get("mean_rms") or 0) < 1:
                    stem_failures.append("STEM_INCLUDED_BUT_SILENT")
            source_cue_sha256s = stem.get("source_cue_sha256s")
            if not isinstance(source_cue_sha256s, list) or not source_cue_sha256s:
                stem_failures.append("STEM_SOURCE_CUE_BINDING_MISSING")
            elif not all(
                isinstance(value, str) and SHA256_PATTERN.fullmatch(value)
                for value in source_cue_sha256s
            ):
                stem_failures.append("STEM_SOURCE_CUE_SHA_INVALID")
        else:
            stem_failures.append("STEM_STATE_INVALID")
        failures.extend(stem_failures)
        stem_results.append(
            {
                "layer": layer,
                "state": state,
                "audio": {key: value for key, value in facts.items() if key != "energy_windows"},
                "status": "FAIL" if stem_failures else "PASS",
                "failures": sorted(set(stem_failures)),
            }
        )
    missing_layers = sorted(REQUIRED_AUDIO_LAYERS - seen_layers)
    failures.extend(f"STEM_LAYER_MISSING:{layer}" for layer in missing_layers)

    published = audio.get("published_mix") if isinstance(audio.get("published_mix"), dict) else {}
    published_path = _safe_file(exports_root, str(published.get("relative_path") or ""))
    published_facts: dict[str, Any] = {}
    master_audio = _audio_signature(master_path)
    mix_similarity = 0.0
    if published_path is None:
        failures.append("PUBLISHED_MIX_MISSING_OR_UNSAFE")
    elif file_sha256(published_path) != published.get("sha256"):
        failures.append("PUBLISHED_MIX_SHA_MISMATCH")
    else:
        published_facts = _audio_signature(published_path)
        if published_facts["status"] != "PASS":
            failures.append("PUBLISHED_MIX_DECODE_FAILED")
        if published_facts.get("source_sample_rates_hz") != [48000]:
            failures.append("PUBLISHED_MIX_SAMPLE_RATE_MISMATCH")
        if published_facts.get("source_channel_counts") != [2]:
            failures.append("PUBLISHED_MIX_CHANNELS_MISMATCH")
        if int(published_facts.get("clipped_sample_count") or 0) > 0:
            failures.append("PUBLISHED_MIX_CLIPPING_DETECTED")
        if published.get("audio_fingerprint") != published_facts.get("energy_fingerprint"):
            failures.append("PUBLISHED_MIX_FINGERPRINT_MISMATCH")
        if (
            master_duration
            and abs(float(published_facts["duration_seconds"]) - master_duration) > 0.2
        ):
            failures.append("PUBLISHED_MIX_DURATION_MISMATCH")
        mix_similarity = _cosine_similarity(
            published_facts.get("energy_windows") or [],
            master_audio.get("energy_windows") or [],
        )
        if mix_similarity < 0.98:
            failures.append("FINAL_MASTER_AUDIO_NOT_BOUND_TO_PUBLISHED_MIX")

    subtitles = manifest.get("subtitles") if isinstance(manifest.get("subtitles"), dict) else {}
    subtitle_path = _safe_file(exports_root, str(subtitles.get("relative_path") or ""))
    if subtitle_path is None:
        failures.append("SUBTITLE_LINEAGE_FILE_MISSING_OR_UNSAFE")
    elif subtitle_path != captions_path.resolve():
        failures.append("SUBTITLE_LINEAGE_PATH_MISMATCH")
    elif file_sha256(subtitle_path) != subtitles.get("sha256"):
        failures.append("SUBTITLE_LINEAGE_SHA_MISMATCH")
    if not SHA256_PATTERN.fullmatch(str(subtitles.get("source_contract_sha256") or "")):
        failures.append("SUBTITLE_SOURCE_CONTRACT_BINDING_MISSING")

    unique_failures = sorted(set(failures))
    return {
        "status": "PASS" if not unique_failures else "FAIL",
        "manifest_sha256": manifest_digest or None,
        "master_media": master_facts,
        "shot_selection": {
            "shot_count": len(shot_results),
            "timeline_duration_seconds": round(previous_end, 6),
            "shots": shot_results,
        },
        "audio_mix": {
            "required_layers": sorted(REQUIRED_AUDIO_LAYERS),
            "stems": stem_results,
            "published_mix": {
                **{key: value for key, value in published_facts.items() if key != "energy_windows"},
                "master_energy_similarity": round(mix_similarity, 6),
                "minimum_master_energy_similarity": 0.98,
            },
        },
        "subtitles": {
            "captions_sha256": captions_sha256,
            "source_contract_sha256": subtitles.get("source_contract_sha256"),
        },
        "failures": unique_failures,
    }
