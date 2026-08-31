#!/usr/bin/env python3
"""Exercise postproduction through the Runtime embedded in a macOS release bundle.

This is a release-candidate QA tool, not a provider simulator. It can create either a
tiny contract fixture or a full 30-minute local soak, sends the execution plan over real
loopback HTTP, and verifies that the bundled Runtime itself normalizes, mixes, assembles,
seals, restarts, and reopens the result. No provider, paid model, publication account, or
non-loopback network call is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from array import array
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import av

PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"
LAYERS = ("dialogue", "ambience", "foley", "music", "sfx")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def request(
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    expected: int = 200,
    timeout: float = 120,
) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    http_request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    if status != expected:
        raise RuntimeError(
            f"{path} returned HTTP {status}, expected {expected}: {raw.decode(errors='replace')}"
        )
    if not raw:
        return None
    return json.loads(raw)


def upload(path: str, query: dict[str, Any], content: bytes, *, content_type: str) -> Any:
    http_request = urllib.request.Request(
        BASE_URL + path + "?" + urllib.parse.urlencode(query),
        data=content,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=120) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    if status != 201:
        raise RuntimeError(
            f"{path} returned HTTP {status}, expected 201: {raw.decode(errors='replace')}"
        )
    return json.loads(raw)


def port_is_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def wait_for_health(process: subprocess.Popen[bytes]) -> float:
    started_at = time.monotonic()
    for _ in range(1200):
        if process.poll() is not None:
            raise RuntimeError(f"bundled Runtime exited before health check: {process.returncode}")
        try:
            health = request("/health", timeout=0.5)
            if health.get("status") == "ok":
                return time.monotonic() - started_at
        except (OSError, RuntimeError):
            pass
        time.sleep(0.1)
    raise RuntimeError("bundled Runtime did not become healthy")


def process_tree_rss_bytes(root_pid: int) -> int:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,rss="],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: dict[int, tuple[int, int]] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        pid, parent, rss_kib = (int(field) for field in fields)
        rows[pid] = (parent, rss_kib)
    included = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (parent, _rss_kib) in rows.items():
            if parent in included and pid not in included:
                included.add(pid)
                changed = True
    return sum(rows.get(pid, (0, 0))[1] for pid in included) * 1024


def allocated_tree_bytes(root: Path) -> int:
    total = 0
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories if not (current_path / name).is_symlink()
        ]
        for name in files:
            candidate = current_path / name
            if not candidate.is_symlink():
                total += candidate.stat().st_blocks * 512
    return total


def sample_materialization(
    *,
    endpoint: str,
    plan: dict[str, Any],
    runtime_pid: int,
    work_dir: Path,
    duration_seconds: int,
    sample_interval_seconds: float,
    max_rss_mib: int,
    min_realtime_factor: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_rss = process_tree_rss_bytes(runtime_pid)
    samples: list[dict[str, Any]] = []
    started_at = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            request,
            endpoint,
            plan,
            expected=201,
            timeout=max(1800, duration_seconds * 8),
        )
        while not future.done():
            elapsed = time.monotonic() - started_at
            samples.append(
                {
                    "elapsed_seconds": round(elapsed, 3),
                    "rss_bytes": process_tree_rss_bytes(runtime_pid),
                    "allocated_bytes": allocated_tree_bytes(work_dir),
                    "free_disk_bytes": shutil.disk_usage(work_dir).free,
                    "stage_count": len(list(work_dir.rglob(".nalu-postproduction-*"))),
                }
            )
            time.sleep(sample_interval_seconds)
        result = future.result()
    elapsed = time.monotonic() - started_at
    samples.append(
        {
            "elapsed_seconds": round(elapsed, 3),
            "rss_bytes": process_tree_rss_bytes(runtime_pid),
            "allocated_bytes": allocated_tree_bytes(work_dir),
            "free_disk_bytes": shutil.disk_usage(work_dir).free,
            "stage_count": len(list(work_dir.rglob(".nalu-postproduction-*"))),
        }
    )
    max_rss = max(sample["rss_bytes"] for sample in samples)
    realtime_factor = duration_seconds / elapsed
    if max_rss > max_rss_mib * 1024 * 1024:
        raise RuntimeError(
            f"full-duration Runtime RSS {max_rss / 1024 / 1024:.1f} MiB exceeds "
            f"{max_rss_mib} MiB"
        )
    if realtime_factor < min_realtime_factor:
        raise RuntimeError(
            f"full-duration throughput {realtime_factor:.3f}x is below "
            f"{min_realtime_factor:.3f}x realtime"
        )
    metrics = {
        "timeline_duration_seconds": duration_seconds,
        "elapsed_seconds": round(elapsed, 3),
        "realtime_factor": round(realtime_factor, 4),
        "sample_interval_seconds": sample_interval_seconds,
        "sample_count": len(samples),
        "baseline_rss_bytes": baseline_rss,
        "maximum_process_tree_rss_bytes": max_rss,
        "maximum_rss_growth_bytes": max_rss - baseline_rss,
        "maximum_allocated_bytes": max(sample["allocated_bytes"] for sample in samples),
        "minimum_free_disk_bytes": min(sample["free_disk_bytes"] for sample in samples),
        "working_stage_observed": any(sample["stage_count"] > 0 for sample in samples),
        "samples_sha256": canonical_sha256(samples),
        "rss_limit_mib": max_rss_mib,
        "minimum_realtime_factor": min_realtime_factor,
    }
    return result, metrics


def create_video(
    path: Path,
    *,
    duration_seconds: int = 2,
    width: int = 64,
    height: int = 64,
    fps: int = 10,
    include_audio: bool = True,
) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w", format="mp4", options={"movflags": "+faststart"}) as output:
        video = output.add_stream("mpeg4", rate=fps)
        video.width = width
        video.height = height
        video.pix_fmt = "yuv420p"
        audio = None
        if include_audio:
            audio = output.add_stream("aac", rate=48000)
            audio.layout = "stereo"
        for index in range(fps * duration_seconds):
            frame = av.VideoFrame(width, height, format="rgb24")
            value = 40 + (index * 9) % 180
            row = bytes((value, 255 - value, (value * 3) % 255)) * width
            padded = row + bytes(frame.planes[0].line_size - len(row))
            frame.planes[0].update(padded * height)
            frame.pts = index
            frame.time_base = Fraction(1, fps)
            for packet in video.encode(frame):
                output.mux(packet)
        for packet in video.encode(None):
            output.mux(packet)
        if audio is not None:
            write_audio_frames(
                output,
                audio,
                frequency=440,
                duration_seconds=duration_seconds,
            )
    return path.read_bytes()


def create_reference_png() -> bytes:
    row = bytes((30, 80, 220)) * 64

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    pixels = b"".join(b"\x00" + row for _ in range(64))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels, 9))
        + chunk(b"IEND", b"")
    )


def write_audio_frames(
    output: av.container.OutputContainer,
    stream: Any,
    *,
    frequency: int,
    duration_seconds: int = 2,
) -> None:
    sample_rate = 48000
    cursor = 0
    total_samples = sample_rate * duration_seconds
    template = array("h")
    for offset in range(1024):
        sample = int(7000 * math.sin(2 * math.pi * frequency * offset / sample_rate))
        template.extend((sample, sample))
    while cursor < total_samples:
        samples = min(1024, total_samples - cursor)
        frame = av.AudioFrame(format="s16", layout="stereo", samples=samples)
        frame.sample_rate = sample_rate
        frame.pts = cursor
        frame.time_base = Fraction(1, sample_rate)
        frame.planes[0].update(template[: samples * 2].tobytes())
        for packet in stream.encode(frame):
            output.mux(packet)
        cursor += samples
    for packet in stream.encode(None):
        output.mux(packet)


def create_audio(
    path: Path,
    *,
    frequency: int,
    duration_seconds: int = 2,
    lossless_compressed: bool = False,
) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    container_format = "flac" if lossless_compressed else "wav"
    codec = "flac" if lossless_compressed else "pcm_s16le"
    with av.open(str(path), mode="w", format=container_format) as output:
        stream = output.add_stream(codec, rate=48000)
        stream.layout = "stereo"
        write_audio_frames(
            output,
            stream,
            frequency=frequency,
            duration_seconds=duration_seconds,
        )
    return path.read_bytes()


def create_approved_episode(title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = request(
        "/v1/project-plans",
        {
            "project": {
                "title": title,
                "audience_mode": "older_adult",
                "planned_episode_count": 1,
            },
            "episode_titles": ["回家"],
        },
        expected=201,
    )
    project = plan["project"]
    episode = plan["episodes"][0]
    entity = request(
        f"/v1/projects/{project['id']}/library-entities",
        {
            "kind": "character",
            "name": "林叔",
            "description": "穿蓝色外套",
            "attributes": {
                "wardrobe": ["蓝色外套"],
                "space_axis": "screen-left",
                "pose": "standing",
                "held_props": [],
            },
            "source_channel": "voice",
            "change_summary": "发布包验收人物",
        },
        expected=201,
    )
    request(
        f"/v1/library-entities/{entity['id']}/confirmations",
        {
            "confirmed_by": "本机 QA",
            "reviewed_revision": 1,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这份人物设定",
        },
        expected=201,
    )
    reference = create_reference_png()
    upload(
        f"/v1/projects/{project['id']}/asset-imports",
        {
            "filename": "lin-shu.png",
            "kind": "character_image",
            "name": "林叔本机视觉参考",
            "subject_name": "林叔",
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本机 QA",
            "consent_statement": "只允许这个隔离项目在本机进行视觉分析",
        },
        reference,
        content_type="image/png",
    )
    script = request(
        f"/v1/episodes/{episode['id']}/scripts",
        {
            "content": "林叔穿着蓝色外套回到家。",
            "summary_for_voice_review": "林叔回到家。",
        },
        expected=201,
    )
    request(
        f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
        {"approved_by": "本机 QA", "spoken_confirmation": "我确认这个剧本"},
    )
    run = request(
        f"/v1/episodes/{episode['id']}/production-runs",
        {"dry_run": True},
        expected=201,
    )
    return episode, run


def enter_postproduction(database: Path, episode_id: str, run_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database, timeout=10) as connection:
        cursor = connection.execute(
            "UPDATE production_runs SET status = 'running', updated_at = ? WHERE id = ?",
            (now, run_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("could not place the isolated QA run into running state")
    for target in ("generating", "postproduction"):
        request(
            f"/v1/episodes/{episode_id}/transition",
            {
                "target_status": target,
                "requested_by": "packaged-runtime-qa",
                "reason": f"isolated fixture entered {target}",
            },
        )


def webvtt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def make_plan(exports: Path, *, duration_seconds: int = 2) -> dict[str, Any]:
    provider = exports / "provider-results"
    video_path = provider / "provider-shot.mp4"
    long_soak = duration_seconds > 2
    source_video_seconds = min(300, duration_seconds)
    video = create_video(
        video_path,
        duration_seconds=source_video_seconds,
        width=64,
        height=64,
        fps=1 if long_soak else 10,
        include_audio=not long_soak,
    )
    audio_layers = []
    shared_audio_path = provider / "shared-lossless-audio.flac"
    if long_soak:
        create_audio(
            shared_audio_path,
            frequency=330,
            duration_seconds=duration_seconds,
            lossless_compressed=True,
        )
        shared_audio_sha = sha256_file(shared_audio_path)
    for index, layer in enumerate(LAYERS):
        audio_path = shared_audio_path if long_soak else provider / f"{layer}.wav"
        if long_soak:
            audio_sha = shared_audio_sha
        else:
            create_audio(audio_path, frequency=330 + index * 55)
            audio_sha = sha256_file(audio_path)
        audio_layers.append(
            {
                "layer": layer,
                "source_relative_path": str(audio_path.relative_to(exports)),
                "source_sha256": audio_sha,
                "source_cue_sha256s": [hashlib.sha256(f"cue-{layer}".encode()).hexdigest()],
                "gain_db": -3 if layer == "music" else 0,
            }
        )
    captions = provider / "captions.vtt"
    captions.write_text(
        "WEBVTT\n\n"
        f"00:00:00.100 --> {webvtt_timestamp(duration_seconds - 0.1)}\n"
        "回家\n",
        encoding="utf-8",
    )
    relative_video = str(video_path.relative_to(exports))
    video_sha = hashlib.sha256(video).hexdigest()
    shots = []
    source_ranges = (
        [(0, 1), (1, 2)]
        if not long_soak
        else [
            (0, min(300, duration_seconds - offset))
            for offset in range(0, duration_seconds, 300)
        ]
    )
    for shot_number, (source_in, source_out) in enumerate(source_ranges, start=1):
        shots.append(
            {
                "shot_id": f"S{shot_number:02d}",
                "source_relative_path": relative_video,
                "source_sha256": video_sha,
                "source_task_id": f"provider-task-{shot_number}",
                "source_receipt_sha256": hashlib.sha256(
                    f"provider-receipt-{shot_number}".encode()
                ).hexdigest(),
                "source_in_seconds": source_in,
                "source_out_seconds": source_out,
            }
        )
    return {
        "requested_by": "packaged-runtime-qa",
        "shots": shots,
        "audio_layers": audio_layers,
        "captions_source_relative_path": str(captions.relative_to(exports)),
        "captions_source_sha256": sha256_file(captions),
        "subtitle_contract_sha256": hashlib.sha256(b"subtitle-contract").hexdigest(),
        "width": 64,
        "height": 64,
        "frame_rate": 1 if long_soak else 10,
    }


def assert_regular_artifact(exports: Path, artifact: dict[str, Any]) -> None:
    path = (exports / artifact["relative_path"]).resolve()
    if not path.is_relative_to(exports.resolve()) or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"unsafe or missing materialized artifact: {artifact['relative_path']}")
    if sha256_file(path) != artifact["sha256"] or path.stat().st_size != artifact["byte_size"]:
        raise RuntimeError(f"materialized artifact digest changed: {artifact['relative_path']}")


def run_positive_case(
    database: Path,
    analyzer: Path,
    *,
    duration_seconds: int,
    runtime_pid: int,
    work_dir: Path,
    sample_interval_seconds: float,
    max_rss_mib: int,
    min_realtime_factor: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    episode, run = create_approved_episode("发布包后期制作闭环")
    enter_postproduction(database, episode["id"], run["id"])
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    plan = make_plan(exports, duration_seconds=duration_seconds)
    endpoint = f"/v1/production-runs/{run['id']}/postproduction-materializations"
    soak_metrics = None
    if duration_seconds > 2:
        result, soak_metrics = sample_materialization(
            endpoint=endpoint,
            plan=plan,
            runtime_pid=runtime_pid,
            work_dir=work_dir,
            duration_seconds=duration_seconds,
            sample_interval_seconds=sample_interval_seconds,
            max_rss_mib=max_rss_mib,
            min_realtime_factor=min_realtime_factor,
        )
    else:
        result = request(endpoint, plan, expected=201)
    if result["schema_version"] != "nalu.postproduction-materialization/v1":
        raise RuntimeError("unexpected materialization result schema")
    expected_shot_ids = [shot["shot_id"] for shot in plan["shots"]]
    if [item["shot_id"] for item in result["normalized_segments"]] != expected_shot_ids:
        raise RuntimeError("bundled Runtime did not preserve the authored shot order")
    if {item["layer"] for item in result["audio_stems"]} != set(LAYERS):
        raise RuntimeError("bundled Runtime did not materialize all five audio layers")
    for artifact in (
        result["master"],
        result["captions"],
        result["postproduction_manifest"],
        result["published_mix"],
        *result["normalized_segments"],
        *result["audio_stems"],
    ):
        assert_regular_artifact(exports, artifact)
    if not result["output_root_relative_path"].startswith("materialized/"):
        raise RuntimeError("materialized output is not rooted under the hash-addressed directory")
    if request(endpoint, plan, expected=201) != result:
        raise RuntimeError("identical materialization replay was not deterministic")
    run_state = request(f"/v1/production-runs/{run['id']}")
    episode_state = request(f"/v1/episodes/{episode['id']}")
    if run_state["status"] != "qa_review" or episode_state["status"] != "qa_review":
        raise RuntimeError("materialization did not atomically enter QA review")
    events = request(f"/v1/production-runs/{run['id']}/events")
    event_count = sum(item["event_type"] == "postproduction_materialized" for item in events)
    if event_count != 1:
        raise RuntimeError(f"materialization replay recorded {event_count} transition events")
    request(endpoint, {**plan, "requested_by": "different-worker"}, expected=409)

    workspace = Path(run["package_path"]).parent / "qingshan-workspace"
    task = json.loads(
        (workspace / "workflow/tasks/E01_PRODUCTION_TASK.json").read_text(encoding="utf-8")
    )
    analyzer_inputs = json.loads(
        (workspace / task["local_visual_analysis"]["inputs_path"]).read_text(encoding="utf-8")
    )
    reference_uri = analyzer_inputs["subjects"][0]["references"][0]["local_file_uri"]
    reference_path = Path(urllib.parse.unquote(urllib.parse.urlparse(reference_uri).path))
    reference_bytes = reference_path.read_bytes()
    reference_path.write_bytes(reference_bytes + b"digest-drift")
    visual_endpoint = f"/v1/production-runs/{run['id']}/local-visual-analysis"
    request(visual_endpoint, {}, expected=409)
    reference_path.write_bytes(reference_bytes)
    visual = request(visual_endpoint, {}, expected=201)
    if (
        visual["provider_upload_performed"]
        or visual["analyzed_shot_count"] != len(expected_shot_ids)
    ):
        raise RuntimeError("local visual execution privacy or shot-count evidence is invalid")
    if visual["analyzer_model_sha256"] != sha256_file(analyzer):
        raise RuntimeError("visual result is not bound to the packaged analyzer binary")
    assert_regular_artifact(exports, visual["manifest"])
    visual_manifest = json.loads(
        (exports / visual["manifest"]["relative_path"]).read_text(encoding="utf-8")
    )
    analyzer_record = visual_manifest["analyzer"]
    if (
        analyzer_record["analyzer_id"] != "nalu-apple-vision-local"
        or not analyzer_record["local_analysis"]
        or analyzer_record["provider_upload_performed"]
    ):
        raise RuntimeError("visual manifest did not prove local-only Apple Vision execution")
    checks = [
        check
        for shot in visual_manifest["shots"]
        for check in shot["checks"]
    ]
    if not checks or any("machine_measurement" not in check for check in checks):
        raise RuntimeError("visual manifest omitted machine-derived measurements")
    visual_events = request(f"/v1/production-runs/{run['id']}/events")
    visual_event_count = sum(
        item["event_type"] == "local_visual_analysis_completed" for item in visual_events
    )
    if visual_event_count != 1 or request(visual_endpoint, {}, expected=201) != visual:
        raise RuntimeError("local visual execution did not replay exactly once")
    seal = request(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        {
            "sealed_by": "packaged-runtime-qa",
            "artifacts": [
                {
                    "kind": item["kind"],
                    "relative_path": item["relative_path"],
                    "media_type": item["media_type"],
                }
                for item in (
                    result["master"],
                    result["captions"],
                    result["postproduction_manifest"],
                    visual["manifest"],
                )
            ],
        },
        expected=201,
    )
    lineage = request(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa", {})
    if (
        lineage["status"] != "PASS"
        or lineage["shot_selection"]["shot_count"] != len(expected_shot_ids)
    ):
        raise RuntimeError("decoded postproduction lineage QA did not pass")
    if {item["layer"] for item in lineage["audio_mix"]["stems"]} != set(LAYERS):
        raise RuntimeError("lineage QA did not decode all five materialized stems")
    visual_qa = request(f"/v1/production-runs/{run['id']}/visual-continuity-qa", {})
    if (
        visual_qa["status"] != visual["status"]
        or visual_qa["shot_count"] != len(expected_shot_ids)
    ):
        raise RuntimeError("same-seal visual QA disagrees with machine observations")
    request(endpoint, plan, expected=409)
    summary = {
        "run_id": run["id"],
        "episode_id": episode["id"],
        "plan_sha256": result["plan_sha256"],
        "result_sha256": result["result_sha256"],
        "master_sha256": result["master"]["sha256"],
        "captions_sha256": result["captions"]["sha256"],
        "manifest_sha256": result["postproduction_manifest"]["sha256"],
        "output_root_relative_path": result["output_root_relative_path"],
        "normalized_shot_count": len(result["normalized_segments"]),
        "audio_layers": sorted(item["layer"] for item in result["audio_stems"]),
        "run_status": run_state["status"],
        "episode_status": episode_state["status"],
        "materialization_event_count": event_count,
        "seal_sha256": seal["manifest_sha256"],
        "lineage_status": lineage["status"],
        "visual_analysis_status": visual["status"],
        "visual_analysis_result_sha256": visual["result_sha256"],
        "visual_manifest_sha256": visual["manifest"]["sha256"],
        "visual_check_count": len(checks),
        "visual_event_count": visual_event_count,
        "visual_qa_status": visual_qa["status"],
        "reference_digest_drift_rejected": True,
        "provider_upload_performed": False,
    }
    if soak_metrics is not None:
        summary["full_duration_soak"] = soak_metrics
    return summary, {
        "result_sha256": result["result_sha256"],
        "event_count": event_count,
        "artifacts": [
            {
                "relative_path": artifact["relative_path"],
                "sha256": artifact["sha256"],
                "byte_size": artifact["byte_size"],
            }
            for artifact in (
                result["master"],
                result["captions"],
                result["postproduction_manifest"],
                result["published_mix"],
                *result["normalized_segments"],
                *result["audio_stems"],
            )
        ],
    }


def run_negative_case(database: Path) -> dict[str, Any]:
    episode, run = create_approved_episode("发布包摘要漂移拒绝")
    enter_postproduction(database, episode["id"], run["id"])
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    plan = make_plan(exports)
    plan["shots"][0]["source_sha256"] = "0" * 64
    request(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        plan,
        expected=409,
    )
    run_state = request(f"/v1/production-runs/{run['id']}")
    episode_state = request(f"/v1/episodes/{episode['id']}")
    finalized = list((exports / "materialized").glob("*/materialization-result.json"))
    if run_state["status"] != "running" or episode_state["status"] != "postproduction":
        raise RuntimeError("rejected materialization advanced production state")
    if finalized:
        raise RuntimeError("rejected materialization left an accepted result")
    return {
        "run_id": run["id"],
        "rejected_http_status": 409,
        "run_status": run_state["status"],
        "episode_status": episode_state["status"],
        "accepted_result_count": len(finalized),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--ci-run", required=True)
    parser.add_argument("--ci-artifact-id", required=True)
    parser.add_argument("--ci-artifact-digest", required=True)
    parser.add_argument("--release-zip-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--duration-seconds", type=int, default=2)
    parser.add_argument("--sample-interval-seconds", type=float, default=1.0)
    parser.add_argument("--max-rss-mib", type=int, default=1024)
    parser.add_argument("--min-realtime-factor", type=float, default=0.25)
    parser.add_argument("--min-free-after-gib", type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = args.app.resolve()
    work_dir = args.work_dir.resolve()
    evidence = args.evidence.resolve()
    if not 2 <= args.duration_seconds <= 1800:
        raise RuntimeError("duration-seconds must be between 2 and 1800")
    if args.sample_interval_seconds <= 0 or args.max_rss_mib <= 0:
        raise RuntimeError("sampling interval and RSS limit must be positive")
    if not 0 < args.min_realtime_factor <= 10:
        raise RuntimeError("minimum realtime factor must be positive and bounded")
    runtime = app / "Contents/Resources/runtime/nalu-runtime"
    runtime_resources = app / "Contents/Resources/runtime-resources"
    executable = app / "Contents/MacOS/NaluVoiceStudio"
    analyzer = app / "Contents/Resources/analyzers/nalu-visual-analyzer"
    if port_is_open():
        raise RuntimeError(f"loopback port {PORT} is already occupied")
    for required in (
        runtime,
        executable,
        analyzer,
        runtime_resources / "configs/qingshan-upstream.json",
    ):
        if not required.exists():
            raise RuntimeError(f"release bundle is missing {required}")
    predicted_pcm_outputs = args.duration_seconds * 48000 * 2 * 2 * 6
    free_before = shutil.disk_usage(work_dir.parent).free
    required_free = predicted_pcm_outputs + round(args.min_free_after_gib * 1024**3)
    if free_before < required_free:
        raise RuntimeError(
            f"full-duration soak requires {required_free / 1024**3:.2f} GiB free but "
            f"only {free_before / 1024**3:.2f} GiB is available"
        )
    work_dir.mkdir(parents=True, exist_ok=False)
    database = work_dir / "runtime.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "NALU_DATA_ROOT": str(work_dir / "runtime-data"),
            "NALU_DATABASE_PATH": str(database),
            "NALU_REPOSITORY_ROOT": str(runtime_resources),
            "NALU_VISUAL_ANALYZER_BINARY": str(analyzer),
        }
    )
    log_path = work_dir / "runtime.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(runtime)], stdout=log, stderr=subprocess.STDOUT, env=environment
        )
        try:
            startup_seconds = wait_for_health(process)
            openapi = request("/openapi.json")
            route = "/v1/production-runs/{run_id}/postproduction-materializations"
            if route not in openapi["paths"]:
                raise RuntimeError("packaged OpenAPI omits the materialization route")
            visual_route = "/v1/production-runs/{run_id}/local-visual-analysis"
            if visual_route not in openapi["paths"]:
                raise RuntimeError("packaged OpenAPI omits the local visual-analysis route")
            positive, replay_context = run_positive_case(
                database,
                analyzer,
                duration_seconds=args.duration_seconds,
                runtime_pid=process.pid,
                work_dir=work_dir,
                sample_interval_seconds=args.sample_interval_seconds,
                max_rss_mib=args.max_rss_mib,
                min_realtime_factor=args.min_realtime_factor,
            )
            negative = run_negative_case(database)
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    for _ in range(50):
        if not port_is_open():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("bundled Runtime left loopback port open after termination")
    restart_replay = {"performed": False}
    if args.duration_seconds > 2:
        with log_path.open("ab") as log:
            restarted = subprocess.Popen(
                [str(runtime)], stdout=log, stderr=subprocess.STDOUT, env=environment
            )
            try:
                restart_startup_seconds = wait_for_health(restarted)
                run_state = request(f"/v1/production-runs/{positive['run_id']}")
                if run_state["status"] != "qa_review":
                    raise RuntimeError("restart did not preserve the sealed QA-review run")
                exports = (
                    Path(run_state["package_path"]).parent / "qingshan-workspace" / "exports"
                )
                for artifact in replay_context["artifacts"]:
                    assert_regular_artifact(exports, artifact)
                events = request(f"/v1/production-runs/{positive['run_id']}/events")
                event_count = sum(
                    item["event_type"] == "postproduction_materialized" for item in events
                )
                if event_count != replay_context["event_count"]:
                    raise RuntimeError("restart replay duplicated the materialization event")
                restart_replay = {
                    "performed": True,
                    "startup_seconds": round(restart_startup_seconds, 3),
                    "sealed_run_state_replayed": True,
                    "all_materialized_artifacts_rehashed": True,
                    "result_sha256": replay_context["result_sha256"],
                    "materialization_event_count": event_count,
                }
            finally:
                restarted.terminate()
                try:
                    restarted.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    restarted.kill()
                    restarted.wait(timeout=10)
        for _ in range(50):
            if not port_is_open():
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("restarted bundled Runtime left loopback port open")
    report = {
        "schema_version": "nalu.packaged-postproduction-qa/v2",
        "status": "PASS",
        "source_commit": args.source_commit,
        "ci_run": args.ci_run,
        "ci_artifact": {
            "id": args.ci_artifact_id,
            "digest": args.ci_artifact_digest,
            "release_zip_sha256": args.release_zip_sha256,
        },
        "bundle": {
            "path": str(app),
            "main_executable_sha256": sha256_file(executable),
            "bundled_runtime_sha256": sha256_file(runtime),
            "bundled_visual_analyzer_sha256": sha256_file(analyzer),
            "signature_scope": "ad-hoc; Developer ID and notarization are not claimed",
        },
        "positive_case": positive,
        "negative_case": negative,
        "restart_replay": restart_replay,
        "device_soak": {
            "requested_duration_seconds": args.duration_seconds,
            "free_disk_before_bytes": free_before,
            "predicted_pcm_output_bytes": predicted_pcm_outputs,
            "minimum_free_after_bytes": round(args.min_free_after_gib * 1024**3),
        },
        "network_scope": "loopback HTTP only; no provider, paid model, or publication call",
        "runtime_stopped_and_port_closed": True,
        "runtime_startup_seconds": round(startup_seconds, 3),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report["report_sha256"] = canonical_sha256(report)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Packaged postproduction QA failed: {error}", file=sys.stderr)
        raise
