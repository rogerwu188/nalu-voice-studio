#!/usr/bin/env python3
"""Exercise postproduction through the Runtime embedded in a macOS release bundle.

This is a release-candidate QA tool, not a provider simulator. It creates tiny local
media fixtures, sends the execution plan over real loopback HTTP, and verifies that
the bundled Runtime itself normalizes, mixes, assembles, seals, and reopens the result.
No provider, paid model, publication account, or non-loopback network call is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from array import array
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


def create_video(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = height = 64
    fps = 10
    sample_rate = 48000
    with av.open(str(path), mode="w", format="mp4", options={"movflags": "+faststart"}) as output:
        video = output.add_stream("mpeg4", rate=fps)
        video.width = width
        video.height = height
        video.pix_fmt = "yuv420p"
        audio = output.add_stream("aac", rate=sample_rate)
        audio.layout = "stereo"
        for index in range(fps * 2):
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
        write_audio_frames(output, audio, frequency=440)
    return path.read_bytes()


def write_audio_frames(
    output: av.container.OutputContainer, stream: Any, *, frequency: int
) -> None:
    sample_rate = 48000
    cursor = 0
    while cursor < sample_rate * 2:
        samples = min(1024, sample_rate * 2 - cursor)
        frame = av.AudioFrame(format="s16", layout="stereo", samples=samples)
        frame.sample_rate = sample_rate
        frame.pts = cursor
        frame.time_base = Fraction(1, sample_rate)
        pcm = array("h")
        for offset in range(samples):
            sample = int(7000 * math.sin(2 * math.pi * frequency * (cursor + offset) / sample_rate))
            pcm.extend((sample, sample))
        frame.planes[0].update(pcm.tobytes())
        for packet in stream.encode(frame):
            output.mux(packet)
        cursor += samples
    for packet in stream.encode(None):
        output.mux(packet)


def create_audio(path: Path, *, frequency: int) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w", format="wav") as output:
        stream = output.add_stream("pcm_s16le", rate=48000)
        stream.layout = "stereo"
        write_audio_frames(output, stream, frequency=frequency)
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
            "attributes": {"wardrobe": ["蓝色外套"]},
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


def make_plan(exports: Path) -> dict[str, Any]:
    provider = exports / "provider-results"
    video_path = provider / "provider-shot.mp4"
    video = create_video(video_path)
    audio_layers = []
    for index, layer in enumerate(LAYERS):
        audio_path = provider / f"{layer}.wav"
        audio = create_audio(audio_path, frequency=330 + index * 55)
        audio_layers.append(
            {
                "layer": layer,
                "source_relative_path": str(audio_path.relative_to(exports)),
                "source_sha256": hashlib.sha256(audio).hexdigest(),
                "source_cue_sha256s": [hashlib.sha256(f"cue-{layer}".encode()).hexdigest()],
                "gain_db": -3 if layer == "music" else 0,
            }
        )
    captions = provider / "captions.vtt"
    captions.write_text("WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8")
    relative_video = str(video_path.relative_to(exports))
    video_sha = hashlib.sha256(video).hexdigest()
    return {
        "requested_by": "packaged-runtime-qa",
        "shots": [
            {
                "shot_id": "S01",
                "source_relative_path": relative_video,
                "source_sha256": video_sha,
                "source_task_id": "provider-task-1",
                "source_receipt_sha256": hashlib.sha256(b"provider-receipt-1").hexdigest(),
                "source_in_seconds": 0,
                "source_out_seconds": 1,
            },
            {
                "shot_id": "S02",
                "source_relative_path": relative_video,
                "source_sha256": video_sha,
                "source_task_id": "provider-task-2",
                "source_receipt_sha256": hashlib.sha256(b"provider-receipt-2").hexdigest(),
                "source_in_seconds": 1,
                "source_out_seconds": 2,
            },
        ],
        "audio_layers": audio_layers,
        "captions_source_relative_path": str(captions.relative_to(exports)),
        "captions_source_sha256": sha256_file(captions),
        "subtitle_contract_sha256": hashlib.sha256(b"subtitle-contract").hexdigest(),
        "width": 64,
        "height": 64,
        "frame_rate": 10,
    }


def assert_regular_artifact(exports: Path, artifact: dict[str, Any]) -> None:
    path = (exports / artifact["relative_path"]).resolve()
    if not path.is_relative_to(exports.resolve()) or path.is_symlink() or not path.is_file():
        raise RuntimeError(f"unsafe or missing materialized artifact: {artifact['relative_path']}")
    if sha256_file(path) != artifact["sha256"] or path.stat().st_size != artifact["byte_size"]:
        raise RuntimeError(f"materialized artifact digest changed: {artifact['relative_path']}")


def run_positive_case(database: Path) -> dict[str, Any]:
    episode, run = create_approved_episode("发布包后期制作闭环")
    enter_postproduction(database, episode["id"], run["id"])
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    plan = make_plan(exports)
    endpoint = f"/v1/production-runs/{run['id']}/postproduction-materializations"
    result = request(endpoint, plan, expected=201)
    if result["schema_version"] != "nalu.postproduction-materialization/v1":
        raise RuntimeError("unexpected materialization result schema")
    if [item["shot_id"] for item in result["normalized_segments"]] != ["S01", "S02"]:
        raise RuntimeError("bundled Runtime did not preserve the two-shot order")
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
                )
            ],
        },
        expected=201,
    )
    lineage = request(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa", {})
    if lineage["status"] != "PASS" or lineage["shot_selection"]["shot_count"] != 2:
        raise RuntimeError("decoded postproduction lineage QA did not pass")
    if {item["layer"] for item in lineage["audio_mix"]["stems"]} != set(LAYERS):
        raise RuntimeError("lineage QA did not decode all five materialized stems")
    request(endpoint, plan, expected=409)
    return {
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = args.app.resolve()
    work_dir = args.work_dir.resolve()
    evidence = args.evidence.resolve()
    runtime = app / "Contents/Resources/runtime/nalu-runtime"
    runtime_resources = app / "Contents/Resources/runtime-resources"
    executable = app / "Contents/MacOS/NaluVoiceStudio"
    if port_is_open():
        raise RuntimeError(f"loopback port {PORT} is already occupied")
    for required in (runtime, executable, runtime_resources / "configs/qingshan-upstream.json"):
        if not required.exists():
            raise RuntimeError(f"release bundle is missing {required}")
    work_dir.mkdir(parents=True, exist_ok=False)
    database = work_dir / "runtime.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "NALU_DATA_ROOT": str(work_dir / "runtime-data"),
            "NALU_DATABASE_PATH": str(database),
            "NALU_REPOSITORY_ROOT": str(runtime_resources),
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
            positive = run_positive_case(database)
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
    report = {
        "schema_version": "nalu.packaged-postproduction-qa/v1",
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
            "signature_scope": "ad-hoc; Developer ID and notarization are not claimed",
        },
        "positive_case": positive,
        "negative_case": negative,
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
