from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import shutil
from array import array
from collections.abc import Iterable, Iterator
from fractions import Fraction
from pathlib import Path
from typing import Any

import av

from .models import (
    PostproductionMaterializationCreate,
    PostproductionMaterializationResult,
    PostproductionShotSource,
)
from .postproduction_lineage_qa import (
    audio_energy_fingerprint,
    inspect_postproduction_lineage,
)
from .secure_files import harden_tree, secure_directory


class PostproductionMaterializationError(RuntimeError):
    pass


def canonical_sha256(value: dict[str, Any] | list[Any]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_input(exports_root: Path, relative_path: str, expected_sha256: str) -> Path:
    relative = Path(relative_path)
    unresolved = exports_root / relative
    try:
        resolved = unresolved.resolve(strict=True)
    except OSError as exc:
        raise PostproductionMaterializationError(
            f"postproduction source is missing: {relative_path}"
        ) from exc
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != "provider-results"
        or unresolved.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(exports_root.resolve(strict=True))
    ):
        raise PostproductionMaterializationError(
            f"postproduction source is unsafe: {relative_path}"
        )
    if file_sha256(resolved) != expected_sha256:
        raise PostproductionMaterializationError(
            f"postproduction source digest changed: {relative_path}"
        )
    return resolved


def _timed_video_frames(path: Path) -> Iterator[tuple[float, av.VideoFrame]]:
    with av.open(str(path), mode="r") as container:
        if not container.streams.video:
            raise PostproductionMaterializationError(f"video stream is missing: {path.name}")
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            if frame.time is not None:
                timestamp = float(frame.time)
            elif frame.pts is not None and frame.time_base is not None:
                timestamp = float(frame.pts * frame.time_base)
            else:
                continue
            yield timestamp, frame


def _selected_frames(
    path: Path,
    *,
    start_seconds: float,
    duration_seconds: float,
    frame_rate: int,
    width: int,
    height: int,
    pixel_format: str,
) -> Iterator[av.VideoFrame]:
    frame_count = max(1, round(duration_seconds * frame_rate))
    iterator = iter(_timed_video_frames(path))
    previous: tuple[float, av.VideoFrame] | None = None
    try:
        current: tuple[float, av.VideoFrame] | None = next(iterator)
    except StopIteration as exc:
        raise PostproductionMaterializationError(f"video has no timed frames: {path.name}") from exc

    for index in range(frame_count):
        target = start_seconds + (index + 0.5) / frame_rate
        while current is not None and current[0] < target:
            previous = current
            try:
                current = next(iterator)
            except StopIteration:
                current = None
        candidates = [candidate for candidate in (previous, current) if candidate is not None]
        if not candidates:
            raise PostproductionMaterializationError(
                f"video range cannot be decoded: {path.name} at {target:.3f}s"
            )
        selected = min(candidates, key=lambda candidate: abs(candidate[0] - target))
        tolerance = max(0.1, 1.5 / frame_rate)
        if abs(selected[0] - target) > tolerance:
            raise PostproductionMaterializationError(
                f"video does not cover requested range: {path.name} at {target:.3f}s"
            )
        yield selected[1].reformat(width=width, height=height, format=pixel_format)


def _decode_audio(path: Path, *, sample_rate: int = 48000) -> array:
    decoded = array("h")
    try:
        with av.open(str(path), mode="r") as container:
            if not container.streams.audio:
                return decoded
            stream = container.streams.audio[0]
            resampler = av.AudioResampler(format="s16", layout="stereo", rate=sample_rate)
            for source_frame in container.decode(stream):
                for frame in resampler.resample(source_frame):
                    raw = bytes(frame.planes[0])[: frame.samples * 4]
                    decoded.frombytes(raw)
            for frame in resampler.resample(None):
                raw = bytes(frame.planes[0])[: frame.samples * 4]
                decoded.frombytes(raw)
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise PostproductionMaterializationError(
            f"audio cannot be decoded: {path.name}: {type(exc).__name__}"
        ) from exc
    return decoded


def _audio_segment(
    path: Path,
    *,
    start_seconds: float,
    sample_count: int,
    require_full_duration: bool,
) -> array:
    source = _decode_audio(path)
    start = round(start_seconds * 48000) * 2
    end = start + sample_count * 2
    if require_full_duration and len(source) < end:
        raise PostproductionMaterializationError(
            f"audio source is shorter than the requested timeline: {path.name}"
        )
    selected = array("h", source[start:min(end, len(source))]) if start < len(source) else array("h")
    missing = sample_count * 2 - len(selected)
    if missing > 0:
        selected.extend(array("h", [0]) * missing)
    return selected


def _encode_audio_packets(
    container: av.container.OutputContainer,
    stream: av.AudioStream,
    samples: array,
) -> None:
    sample_cursor = 0
    total_samples = len(samples) // 2
    while sample_cursor < total_samples:
        count = min(1024, total_samples - sample_cursor)
        frame = av.AudioFrame(format="s16", layout="stereo", samples=count)
        frame.sample_rate = 48000
        frame.pts = sample_cursor
        frame.time_base = Fraction(1, 48000)
        offset = sample_cursor * 2
        frame.planes[0].update(samples[offset : offset + count * 2].tobytes())
        for packet in stream.encode(frame):
            container.mux(packet)
        sample_cursor += count
    for packet in stream.encode(None):
        container.mux(packet)


def _encode_mp4(
    path: Path,
    *,
    frames: Iterable[av.VideoFrame],
    audio_samples: array,
    width: int,
    height: int,
    frame_rate: int,
    pixel_format: str,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = 0
    try:
        with av.open(
            str(path), mode="w", format="mp4", options={"movflags": "+faststart"}
        ) as container:
            video = container.add_stream("mpeg4", rate=frame_rate)
            video.width = width
            video.height = height
            video.pix_fmt = pixel_format
            audio = container.add_stream("aac", rate=48000)
            audio.layout = "stereo"
            audio.bit_rate = 192000
            for frame_count, frame in enumerate(frames, start=1):
                frame.pts = frame_count - 1
                frame.time_base = Fraction(1, frame_rate)
                for packet in video.encode(frame):
                    container.mux(packet)
            for packet in video.encode(None):
                container.mux(packet)
            _encode_audio_packets(container, audio, audio_samples)
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise PostproductionMaterializationError(
            f"media encoding failed for {path.name}: {type(exc).__name__}"
        ) from exc
    if frame_count == 0:
        raise PostproductionMaterializationError(f"no video frames were encoded: {path.name}")
    return frame_count


def _write_wav(path: Path, samples: array) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with av.open(str(path), mode="w", format="wav") as container:
            stream = container.add_stream("pcm_s16le", rate=48000)
            stream.layout = "stereo"
            _encode_audio_packets(container, stream, samples)
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise PostproductionMaterializationError(
            f"audio encoding failed for {path.name}: {type(exc).__name__}"
        ) from exc


def _artifact(relative_path: str, path: Path, *, kind: str, media_type: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "relative_path": relative_path,
        "media_type": media_type,
        "sha256": file_sha256(path),
        "byte_size": path.stat().st_size,
    }


def _verify_result(
    result_path: Path,
    *,
    exports_root: Path,
    expected_plan_sha256: str,
) -> PostproductionMaterializationResult:
    if result_path.is_symlink() or not result_path.is_file():
        raise PostproductionMaterializationError("materialization result is missing or unsafe")
    try:
        result = PostproductionMaterializationResult.model_validate_json(
            result_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise PostproductionMaterializationError("materialization result is unreadable") from exc
    body = result.model_dump(mode="json", exclude={"result_sha256"})
    if canonical_sha256(body) != result.result_sha256:
        raise PostproductionMaterializationError("materialization result digest mismatch")
    if result.plan_sha256 != expected_plan_sha256:
        raise PostproductionMaterializationError(
            "postproduction was already materialized from a different plan"
        )
    for artifact in [
        result.master,
        result.captions,
        result.postproduction_manifest,
        result.published_mix,
        *result.normalized_segments,
        *result.audio_stems,
    ]:
        relative = Path(str(artifact.get("relative_path") or ""))
        candidate = exports_root / relative
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise PostproductionMaterializationError(
                f"materialized artifact is missing: {relative}"
            ) from exc
        if (
            relative.is_absolute()
            or candidate.is_symlink()
            or not resolved.is_file()
            or not resolved.is_relative_to(exports_root.resolve(strict=True))
            or file_sha256(resolved) != artifact.get("sha256")
            or resolved.stat().st_size != artifact.get("byte_size")
        ):
            raise PostproductionMaterializationError(
                f"materialized artifact integrity failed: {relative}"
            )
    master_path = exports_root / str(result.master["relative_path"])
    captions_path = exports_root / str(result.captions["relative_path"])
    manifest_path = exports_root / str(result.postproduction_manifest["relative_path"])
    inspected = inspect_postproduction_lineage(
        manifest_path,
        exports_root=exports_root,
        production_package_sha256=result.production_package_sha256,
        master_path=master_path,
        master_sha256=str(result.master["sha256"]),
        captions_path=captions_path,
        captions_sha256=str(result.captions["sha256"]),
    )
    if inspected["status"] != "PASS":
        raise PostproductionMaterializationError(
            "stored materialization failed decoded lineage replay: "
            + "; ".join(inspected["failures"])
        )
    return result


def _existing_result(
    exports_root: Path,
    *,
    plan_sha256: str,
) -> PostproductionMaterializationResult | None:
    materialized_root = exports_root / "materialized"
    if not materialized_root.exists():
        return None
    candidates = sorted(materialized_root.glob("*/materialization-result.json"))
    if len(candidates) > 1:
        raise PostproductionMaterializationError(
            "multiple finalized postproduction materializations exist for one run"
        )
    if not candidates:
        return None
    return _verify_result(
        candidates[0], exports_root=exports_root, expected_plan_sha256=plan_sha256
    )


def materialize_postproduction(
    *,
    run_id: str,
    project_id: str,
    episode_id: str,
    episode_number: int,
    production_package_sha256: str,
    workspace_manifest_sha256: str,
    exports_root: Path,
    request: PostproductionMaterializationCreate,
    created_at: str,
) -> PostproductionMaterializationResult:
    exports_root = exports_root.resolve(strict=True)
    plan_body = {
        "schema_version": "nalu.postproduction-materialization-plan/v1",
        "run_id": run_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "production_package_sha256": production_package_sha256,
        "workspace_manifest_sha256": workspace_manifest_sha256,
        "request": request.model_dump(mode="json"),
    }
    plan_sha256 = canonical_sha256(plan_body)
    existing = _existing_result(exports_root, plan_sha256=plan_sha256)
    if existing is not None:
        return existing

    source_files: dict[str, Path] = {}
    for shot in request.shots:
        source_files[shot.source_relative_path] = _safe_input(
            exports_root, shot.source_relative_path, shot.source_sha256
        )
    for layer in request.audio_layers:
        source_files[layer.source_relative_path] = _safe_input(
            exports_root, layer.source_relative_path, layer.source_sha256
        )
    captions_source = _safe_input(
        exports_root,
        request.captions_source_relative_path,
        request.captions_source_sha256,
    )

    episode_code = f"E{episode_number:02d}"
    output_prefix = Path("materialized") / plan_sha256
    materialized_parent = exports_root / "materialized"
    secure_directory(materialized_parent)
    stage = exports_root / f".nalu-postproduction-{secrets.token_hex(12)}"
    stage.mkdir(mode=0o700)
    total_duration = 0.0
    normalized_entries: list[dict[str, Any]] = []
    stem_entries: list[dict[str, Any]] = []
    output_result: PostproductionMaterializationResult | None = None
    final_root = exports_root / output_prefix
    try:
        (stage / "materialization-plan.json").write_text(
            json.dumps({**plan_body, "plan_sha256": plan_sha256}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

        normalized_specs: list[tuple[PostproductionShotSource, Path, float]] = []
        for shot in request.shots:
            raw_duration = shot.source_out_seconds - shot.source_in_seconds
            frame_count = max(1, round(raw_duration * request.frame_rate))
            duration = frame_count / request.frame_rate
            sample_count = round(duration * 48000)
            source_path = source_files[shot.source_relative_path]
            source_audio = _audio_segment(
                source_path,
                start_seconds=shot.source_in_seconds,
                sample_count=sample_count,
                require_full_duration=False,
            )
            normalized_path = stage / "normalized-segments" / f"{shot.shot_id}.mp4"
            encoded_frames = _encode_mp4(
                normalized_path,
                frames=_selected_frames(
                    source_path,
                    start_seconds=shot.source_in_seconds,
                    duration_seconds=duration,
                    frame_rate=request.frame_rate,
                    width=request.width,
                    height=request.height,
                    pixel_format=request.pixel_format,
                ),
                audio_samples=source_audio,
                width=request.width,
                height=request.height,
                frame_rate=request.frame_rate,
                pixel_format=request.pixel_format,
            )
            if encoded_frames != frame_count:
                raise PostproductionMaterializationError(
                    f"normalized frame count mismatch for {shot.shot_id}"
                )
            relative = output_prefix / "normalized-segments" / f"{shot.shot_id}.mp4"
            normalized_entries.append(
                {
                    "shot_id": shot.shot_id,
                    "relative_path": relative.as_posix(),
                    "sha256": file_sha256(normalized_path),
                    "byte_size": normalized_path.stat().st_size,
                    "duration_seconds": round(duration, 6),
                    "frame_count": frame_count,
                }
            )
            normalized_specs.append((shot, normalized_path, duration))
            total_duration += duration

        total_sample_count = round(total_duration * 48000)
        mix_accumulator = array("f", [0.0]) * (total_sample_count * 2)
        total_gain = 0.0
        for layer in request.audio_layers:
            source_path = source_files[layer.source_relative_path]
            samples = _audio_segment(
                source_path,
                start_seconds=layer.source_in_seconds,
                sample_count=total_sample_count,
                require_full_duration=True,
            )
            stem_path = stage / "audio" / f"{episode_code}_{layer.layer.upper()}.wav"
            _write_wav(stem_path, samples)
            gain = math.pow(10.0, layer.gain_db / 20.0)
            total_gain += gain
            for index, sample in enumerate(samples):
                mix_accumulator[index] += sample * gain
            relative = output_prefix / "audio" / stem_path.name
            stem_entries.append(
                {
                    "layer": layer.layer,
                    "state": "included",
                    "relative_path": relative.as_posix(),
                    "sha256": file_sha256(stem_path),
                    "byte_size": stem_path.stat().st_size,
                    "source_cue_sha256s": layer.source_cue_sha256s,
                    "source_relative_path": layer.source_relative_path,
                    "source_sha256": layer.source_sha256,
                    "gain_db": layer.gain_db,
                }
            )
        if total_gain <= 0:
            raise PostproductionMaterializationError("audio mix has no positive gain")
        published_samples = array(
            "h",
            (
                max(-32768, min(32767, round(value / total_gain * 0.9)))
                for value in mix_accumulator
            ),
        )
        published_mix_path = stage / "audio" / f"{episode_code}_PUBLISHED_MIX.wav"
        _write_wav(published_mix_path, published_samples)

        def master_frames() -> Iterator[av.VideoFrame]:
            for _shot, normalized_path, duration in normalized_specs:
                yield from _selected_frames(
                    normalized_path,
                    start_seconds=0,
                    duration_seconds=duration,
                    frame_rate=request.frame_rate,
                    width=request.width,
                    height=request.height,
                    pixel_format=request.pixel_format,
                )

        master_path = stage / f"{episode_code}_MASTER.mp4"
        _encode_mp4(
            master_path,
            frames=master_frames(),
            audio_samples=published_samples,
            width=request.width,
            height=request.height,
            frame_rate=request.frame_rate,
            pixel_format=request.pixel_format,
        )
        captions_path = stage / f"{episode_code}_zh-CN.vtt"
        shutil.copyfile(captions_source, captions_path)

        master_relative = (output_prefix / master_path.name).as_posix()
        captions_relative = (output_prefix / captions_path.name).as_posix()
        mix_relative = (output_prefix / "audio" / published_mix_path.name).as_posix()
        timeline_start = 0.0
        selected_shots: list[dict[str, Any]] = []
        for (shot, _normalized_path, duration), normalized in zip(
            normalized_specs, normalized_entries, strict=True
        ):
            selected_shots.append(
                {
                    "shot_id": shot.shot_id,
                    "admission_status": "ADMITTED_FOR_ASSEMBLY",
                    "source_task_id": shot.source_task_id,
                    "source_receipt_sha256": shot.source_receipt_sha256,
                    "source_relative_path": shot.source_relative_path,
                    "source_sha256": shot.source_sha256,
                    "normalized_relative_path": normalized["relative_path"],
                    "normalized_sha256": normalized["sha256"],
                    "timeline_start_seconds": round(timeline_start, 6),
                    "duration_seconds": round(duration, 6),
                    "source_in_seconds": shot.source_in_seconds,
                    "source_out_seconds": shot.source_out_seconds,
                }
            )
            timeline_start += duration

        master_sha256 = file_sha256(master_path)
        captions_sha256 = file_sha256(captions_path)
        manifest_body = {
            "schema_version": "nalu.postproduction-lineage-manifest/v1",
            "production_package_sha256": production_package_sha256,
            "final_master_sha256": master_sha256,
            "captions_sha256": captions_sha256,
            "materialization_plan_sha256": plan_sha256,
            "executor": {
                "executor_id": "nalu-local-postproduction",
                "version": "nalu.postproduction-materialization/v1",
                "network_call_performed": False,
            },
            "timeline": {
                "width": request.width,
                "height": request.height,
                "frame_rate": request.frame_rate,
                "pixel_format": request.pixel_format,
                "selected_shots": selected_shots,
            },
            "audio": {
                "sample_rate_hz": 48000,
                "channels": 2,
                "stems": [
                    {key: value for key, value in stem.items() if key != "byte_size"}
                    for stem in stem_entries
                ],
                "published_mix": {
                    "relative_path": mix_relative,
                    "sha256": file_sha256(published_mix_path),
                    "audio_fingerprint": audio_energy_fingerprint(published_mix_path),
                },
            },
            "subtitles": {
                "relative_path": captions_relative,
                "sha256": captions_sha256,
                "source_contract_sha256": request.subtitle_contract_sha256,
                "source_relative_path": request.captions_source_relative_path,
                "source_sha256": request.captions_source_sha256,
            },
        }
        manifest_path = stage / f"{episode_code}_POSTPRODUCTION_LINEAGE.json"
        manifest_path.write_text(
            json.dumps(
                {**manifest_body, "manifest_sha256": canonical_sha256(manifest_body)},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        master_artifact = _artifact(
            master_relative, master_path, kind="master_video", media_type="video/mp4"
        )
        captions_artifact = _artifact(
            captions_relative, captions_path, kind="captions", media_type="text/vtt"
        )
        manifest_artifact = _artifact(
            (output_prefix / manifest_path.name).as_posix(),
            manifest_path,
            kind="postproduction_manifest",
            media_type="application/json",
        )
        published_artifact = _artifact(
            mix_relative,
            published_mix_path,
            kind="audio_master",
            media_type="audio/wav",
        )
        result_body = {
            "schema_version": "nalu.postproduction-materialization/v1",
            "run_id": run_id,
            "project_id": project_id,
            "episode_id": episode_id,
            "production_package_sha256": production_package_sha256,
            "workspace_manifest_sha256": workspace_manifest_sha256,
            "plan_sha256": plan_sha256,
            "output_root_relative_path": output_prefix.as_posix(),
            "master": master_artifact,
            "captions": captions_artifact,
            "postproduction_manifest": manifest_artifact,
            "normalized_segments": normalized_entries,
            "audio_stems": stem_entries,
            "published_mix": published_artifact,
            "requested_by": request.requested_by,
            "created_at": created_at,
        }
        output_result = PostproductionMaterializationResult(
            **result_body, result_sha256=canonical_sha256(result_body)
        )
        (stage / "materialization-result.json").write_text(
            output_result.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

        for relative_path, expected_sha256 in (
            (shot.source_relative_path, shot.source_sha256) for shot in request.shots
        ):
            _safe_input(exports_root, relative_path, expected_sha256)
        for relative_path, expected_sha256 in (
            (layer.source_relative_path, layer.source_sha256)
            for layer in request.audio_layers
        ):
            _safe_input(exports_root, relative_path, expected_sha256)
        _safe_input(
            exports_root,
            request.captions_source_relative_path,
            request.captions_source_sha256,
        )

        harden_tree(stage)
        try:
            os.rename(stage, final_root)
        except OSError:
            existing = _existing_result(exports_root, plan_sha256=plan_sha256)
            if existing is None:
                raise
            return existing
        harden_tree(final_root)
        inspected = inspect_postproduction_lineage(
            final_root / manifest_path.name,
            exports_root=exports_root,
            production_package_sha256=production_package_sha256,
            master_path=final_root / master_path.name,
            master_sha256=master_sha256,
            captions_path=final_root / captions_path.name,
            captions_sha256=captions_sha256,
        )
        if inspected["status"] != "PASS":
            quarantine = exports_root / "quarantine"
            secure_directory(quarantine)
            quarantined = quarantine / f"{plan_sha256}-{secrets.token_hex(8)}"
            os.rename(final_root, quarantined)
            raise PostproductionMaterializationError(
                "materialized outputs failed lineage verification: "
                + "; ".join(inspected["failures"])
            )
        return _verify_result(
            final_root / "materialization-result.json",
            exports_root=exports_root,
            expected_plan_sha256=plan_sha256,
        )
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
