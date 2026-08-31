import hashlib
import json
import math
import struct
from array import array
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import av
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import RunStatus
from nalu_runtime.postproduction_lineage_qa import audio_energy_fingerprint


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def approved_episode_with_library(api: TestClient) -> tuple[dict, dict, dict]:
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "成片不可变性", "planned_episode_count": 1}},
    ).json()
    project = plan["project"]
    episode = plan["episodes"][0]
    entity = api.post(
        f"/v1/projects/{project['id']}/library-entities",
        json={
            "kind": "character",
            "name": "林叔",
            "description": "穿蓝色外套",
            "attributes": {"wardrobe": ["蓝色外套"]},
            "source_channel": "voice",
            "change_summary": "第一次确认",
        },
    ).json()
    confirmed = api.post(
        f"/v1/library-entities/{entity['id']}/confirmations",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 1,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这份人物设定",
        },
    )
    assert confirmed.status_code == 201
    script = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={
            "content": "林叔穿着蓝色外套回到家。",
            "summary_for_voice_review": "林叔回到家。",
        },
    ).json()
    approved = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "本人", "spoken_confirmation": "我确认这个剧本"},
    )
    assert approved.status_code == 200
    return project, episode, entity


def seal_payload(
    *,
    include_qa: bool = False,
    include_shot_manifest: bool = False,
    include_postproduction_manifest: bool = False,
    include_visual_continuity_manifest: bool = False,
) -> dict:
    payload = {
        "sealed_by": "local-qa-worker",
        "artifacts": [
            {
                "kind": "master_video",
                "relative_path": "E01_MASTER.mp4",
                "media_type": "video/mp4",
            },
            {
                "kind": "captions",
                "relative_path": "E01_zh-CN.vtt",
                "media_type": "text/vtt",
            },
        ],
    }
    if include_qa:
        payload["artifacts"].append(
            {
                "kind": "qa_report",
                "relative_path": "E01_FINAL_QA.json",
                "media_type": "application/json",
            }
        )
    if include_shot_manifest:
        payload["artifacts"].append(
            {
                "kind": "shot_manifest",
                "relative_path": "E01_SHOT_BOUNDARIES.json",
                "media_type": "application/json",
            }
        )
    if include_postproduction_manifest:
        payload["artifacts"].append(
            {
                "kind": "postproduction_manifest",
                "relative_path": "E01_POSTPRODUCTION_LINEAGE.json",
                "media_type": "application/json",
            }
        )
    if include_visual_continuity_manifest:
        payload["artifacts"].append(
            {
                "kind": "visual_continuity_manifest",
                "relative_path": "E01_VISUAL_CONTINUITY.json",
                "media_type": "application/json",
            }
        )
    return payload


def advance_episode_to_qa(api: TestClient, episode_id: str) -> None:
    for target in ("generating", "postproduction", "qa_review"):
        response = api.post(
            f"/v1/episodes/{episode_id}/transition",
            json={
                "target_status": target,
                "requested_by": "local-production-worker",
                "reason": f"fixture entered {target}",
            },
        )
        assert response.status_code == 200


def mp4_box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def minimal_mp4(*, duration_milliseconds: int = 2000, include_media_data: bool = True) -> bytes:
    ftyp = mp4_box(b"ftyp", b"isom" + struct.pack(">I", 0) + b"isommp42")
    mvhd_payload = (
        b"\x00\x00\x00\x00"
        + struct.pack(">I", 0)
        + struct.pack(">I", 0)
        + struct.pack(">I", 1000)
        + struct.pack(">I", duration_milliseconds)
    )
    moov = mp4_box(b"moov", mp4_box(b"mvhd", mvhd_payload))
    mdat = mp4_box(b"mdat", b"golden-frame-fixture") if include_media_data else b""
    return ftyp + moov + mdat


def create_playable_mp4(
    path: Path,
    *,
    frozen: bool = False,
    silent: bool = False,
    hold_across_boundary: bool = False,
) -> bytes:
    width = height = 64
    fps = 10
    sample_rate = 48000
    duration_seconds = 2
    with av.open(
        str(path),
        mode="w",
        format="mp4",
        options={"movflags": "+faststart"},
    ) as container:
        video = container.add_stream("mpeg4", rate=fps)
        video.width = width
        video.height = height
        video.pix_fmt = "yuv420p"
        audio = container.add_stream("aac", rate=sample_rate)
        audio.layout = "stereo"

        for index in range(fps * duration_seconds):
            frame = av.VideoFrame(width, height, format="rgb24")
            value = 80 if frozen else 40 + (index * 9) % 180
            if hold_across_boundary and index in {9, 10}:
                value = 121
            pixel_row = bytes((value, 255 - value, (value * 3) % 255)) * width
            padded_row = pixel_row + bytes(frame.planes[0].line_size - len(pixel_row))
            frame.planes[0].update(padded_row * height)
            frame.pts = index
            frame.time_base = Fraction(1, fps)
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode(None):
            container.mux(packet)

        sample_cursor = 0
        while sample_cursor < sample_rate * duration_seconds:
            samples = min(1024, sample_rate * duration_seconds - sample_cursor)
            frame = av.AudioFrame(format="s16", layout="stereo", samples=samples)
            frame.sample_rate = sample_rate
            frame.pts = sample_cursor
            frame.time_base = Fraction(1, sample_rate)
            pcm = array("h")
            for offset in range(samples):
                sample = (
                    0
                    if silent
                    else int(
                        7000 * math.sin(2 * math.pi * 440 * (sample_cursor + offset) / sample_rate)
                    )
                )
                pcm.extend((sample, sample))
            frame.planes[0].update(pcm.tobytes())
            for packet in audio.encode(frame):
                container.mux(packet)
            sample_cursor += samples
        for packet in audio.encode(None):
            container.mux(packet)
    return path.read_bytes()


def create_audio_stem(path: Path, *, frequency: int = 440) -> bytes:
    sample_rate = 48000
    duration_seconds = 2
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w", format="wav") as container:
        audio = container.add_stream("pcm_s16le", rate=sample_rate)
        audio.layout = "stereo"
        sample_cursor = 0
        while sample_cursor < sample_rate * duration_seconds:
            samples = min(1024, sample_rate * duration_seconds - sample_cursor)
            frame = av.AudioFrame(format="s16", layout="stereo", samples=samples)
            frame.sample_rate = sample_rate
            frame.pts = sample_cursor
            frame.time_base = Fraction(1, sample_rate)
            pcm = array("h")
            for offset in range(samples):
                sample = int(
                    7000
                    * math.sin(2 * math.pi * frequency * (sample_cursor + offset) / sample_rate)
                )
                pcm.extend((sample, sample))
            frame.planes[0].update(pcm.tobytes())
            for packet in audio.encode(frame):
                container.mux(packet)
            sample_cursor += samples
        for packet in audio.encode(None):
            container.mux(packet)
    return path.read_bytes()


def write_postproduction_lineage_manifest(
    run: dict,
    exports: Path,
    *,
    corrupt_admission: bool = False,
) -> None:
    package = json.loads(Path(run["package_path"]).read_text(encoding="utf-8"))
    master_path = exports / "E01_MASTER.mp4"
    captions_path = exports / "E01_zh-CN.vtt"
    source_path = exports / "source-clips" / "S01.mp4"
    normalized_path = exports / "normalized-segments" / "S01.mp4"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(master_path.read_bytes())
    normalized_path.write_bytes(master_path.read_bytes())

    stem_entries = []
    for index, layer in enumerate(("dialogue", "ambience", "foley", "music", "sfx")):
        stem_path = exports / "audio" / f"E01_{layer.upper()}.wav"
        stem_bytes = create_audio_stem(stem_path)
        stem_entries.append(
            {
                "layer": layer,
                "state": "included",
                "relative_path": str(stem_path.relative_to(exports)),
                "sha256": hashlib.sha256(stem_bytes).hexdigest(),
                "source_cue_sha256s": [hashlib.sha256(f"cue-{index}".encode()).hexdigest()],
            }
        )
    published_mix = exports / "audio" / "E01_PUBLISHED_MIX.wav"
    published_bytes = create_audio_stem(published_mix)
    body = {
        "schema_version": "nalu.postproduction-lineage-manifest/v1",
        "production_package_sha256": package["package_sha256"],
        "final_master_sha256": hashlib.sha256(master_path.read_bytes()).hexdigest(),
        "captions_sha256": hashlib.sha256(captions_path.read_bytes()).hexdigest(),
        "timeline": {
            "width": 64,
            "height": 64,
            "frame_rate": 10,
            "pixel_format": "yuv420p",
            "selected_shots": [
                {
                    "shot_id": "S01",
                    "admission_status": (
                        "REJECTED" if corrupt_admission else "ADMITTED_FOR_ASSEMBLY"
                    ),
                    "source_task_id": "fixture-provider-task-1",
                    "source_receipt_sha256": hashlib.sha256(b"provider-receipt-1").hexdigest(),
                    "source_relative_path": str(source_path.relative_to(exports)),
                    "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                    "normalized_relative_path": str(normalized_path.relative_to(exports)),
                    "normalized_sha256": hashlib.sha256(normalized_path.read_bytes()).hexdigest(),
                    "timeline_start_seconds": 0.0,
                    "duration_seconds": 2.0,
                    "source_in_seconds": 0.0,
                    "source_out_seconds": 2.0,
                }
            ],
        },
        "audio": {
            "sample_rate_hz": 48000,
            "channels": 2,
            "stems": stem_entries,
            "published_mix": {
                "relative_path": str(published_mix.relative_to(exports)),
                "sha256": hashlib.sha256(published_bytes).hexdigest(),
                "audio_fingerprint": audio_energy_fingerprint(published_mix),
            },
        },
        "subtitles": {
            "relative_path": str(captions_path.relative_to(exports)),
            "sha256": hashlib.sha256(captions_path.read_bytes()).hexdigest(),
            "source_contract_sha256": hashlib.sha256(b"subtitle-contract").hexdigest(),
        },
    }
    body["manifest_sha256"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (exports / "E01_POSTPRODUCTION_LINEAGE.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def decoded_gray_frame(path: Path, requested_time: float) -> tuple[float, str]:
    frames: list[tuple[float, str]] = []
    with av.open(str(path), mode="r") as container:
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
            frames.append((float(frame.time), hashlib.sha256(pixels).hexdigest()))
    return min(frames, key=lambda item: abs(item[0] - requested_time))


def write_visual_continuity_manifest(
    run: dict,
    exports: Path,
    *,
    corrupt_domain: str | None = None,
    corrupt_frame: bool = False,
) -> None:
    package = json.loads(Path(run["package_path"]).read_text(encoding="utf-8"))
    master_path = exports / "E01_MASTER.mp4"
    frame_time, frame_sha = decoded_gray_frame(master_path, 0.5)
    character = next(
        entity for entity in package["resolved_library"] if entity["kind"] == "character"
    )
    wardrobe = character["revision"]["attributes"]["wardrobe"][0]
    expected_values = {
        "identity": character["stable_name"],
        "wardrobe": wardrobe,
        "space_axis": "screen-left",
        "pose": "standing",
        "props": "none",
    }
    checks = []
    for domain, expected in expected_values.items():
        observed = "mismatch" if corrupt_domain == domain else expected
        check = {
            "domain": domain,
            "expected": expected,
            "observed": observed,
            "confidence": 0.98,
            "source_frame_sha256": frame_sha,
            "status": "FAIL" if corrupt_domain == domain else "PASS",
        }
        if domain in {"identity", "wardrobe"}:
            check["subject_id"] = character["entity_id"]
            check["confirmed_revision"] = character["confirmed_revision"]
        checks.append(check)
    resolved_library_sha = hashlib.sha256(
        json.dumps(
            package["resolved_library"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    body = {
        "schema_version": "nalu.visual-continuity-manifest/v1",
        "production_package_sha256": package["package_sha256"],
        "final_master_sha256": hashlib.sha256(master_path.read_bytes()).hexdigest(),
        "resolved_library_sha256": resolved_library_sha,
        "analyzer": {
            "analyzer_id": "qingshan-visual-continuity-local",
            "version": "golden-fixture-v1",
            "model_sha256": hashlib.sha256(b"fixture-visual-model").hexdigest(),
            "local_analysis": True,
            "generated_at": "2026-08-31T02:30:00Z",
        },
        "required_domains": [
            "identity",
            "wardrobe",
            "space_axis",
            "pose",
            "props",
        ],
        "shots": [
            {
                "shot_id": "S01",
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "evidence_frames": [
                    {
                        "time_seconds": frame_time,
                        "frame_sha256": "0" * 64 if corrupt_frame else frame_sha,
                    }
                ],
                "checks": checks,
            }
        ],
    }
    body["manifest_sha256"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    (exports / "E01_VISUAL_CONTINUITY.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_shot_manifest(run: dict, exports: Path, *, corrupt_contract: bool = False) -> None:
    package = json.loads(Path(run["package_path"]).read_text(encoding="utf-8"))
    contract = {
        "transition_type": "hard_cut",
        "visual_change_required": True,
        "audio_bridge": "continuous-voice",
    }
    contract_sha = hashlib.sha256(
        json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    body = {
        "schema_version": "nalu.shot-boundary-manifest/v1",
        "production_package_sha256": package["package_sha256"],
        "units": [
            {"unit_id": "U01", "start_seconds": 0.0, "end_seconds": 1.0},
            {
                "unit_id": "U02",
                "start_seconds": 1.0,
                "end_seconds": 2.0,
                "incoming_transition_contract": contract,
                "incoming_transition_contract_sha256": (
                    "0" * 64 if corrupt_contract else contract_sha
                ),
            },
        ],
    }
    body["manifest_sha256"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (exports / "E01_SHOT_BOUNDARIES.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def semantic_qa_payload(master_sha: str, *, transcript: str = "回家") -> dict:
    return {
        "source_master_sha256": master_sha,
        "transcript": transcript,
        "segments": [
            {
                "start_seconds": 0.1,
                "end_seconds": 1.8,
                "text": transcript,
                "confidence": 0.95,
            }
        ],
        "recognizer_id": "apple-speech-on-device",
        "recognizer_version": "macOS-test-double",
        "locale": "zh-CN",
        "local_recognition": True,
        "generated_at": "2026-08-31T00:20:00Z",
    }


def test_sealed_outputs_survive_library_edits_and_detect_file_tampering(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _project, episode, entity = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    run_directory = Path(run["package_path"]).parent
    exports = run_directory / "qingshan-workspace" / "exports"
    master_bytes = b"immutable-master-video-fixture"
    (exports / "E01_MASTER.mp4").write_bytes(master_bytes)
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.000\n回家\n", encoding="utf-8"
    )

    sealed = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    assert sealed.status_code == 201
    seal = sealed.json()
    master = next(item for item in seal["artifacts"] if item["kind"] == "master_video")
    assert master["sha256"] == hashlib.sha256(master_bytes).hexdigest()
    assert len(seal["production_package_sha256"]) == 64
    assert len(seal["resolved_library_sha256"]) == 64

    revision = api.post(
        f"/v1/library-entities/{entity['id']}/revisions",
        json={
            "name": "林叔",
            "description": "改穿棕色外套",
            "attributes": {"wardrobe": ["棕色外套"]},
            "source_channel": "voice",
            "change_summary": "为下一集换装",
        },
    ).json()
    assert revision["current_revision"] == 2
    confirmed = api.post(
        f"/v1/library-entities/{entity['id']}/confirmations",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 2,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认下一集改穿棕色外套",
        },
    )
    assert confirmed.status_code == 201

    intact = api.get(f"/v1/production-runs/{run['id']}/rendered-output-integrity").json()
    assert intact["integrity_ok"] is True
    assert intact["seal"] == seal
    assert (exports / "E01_MASTER.mp4").read_bytes() == master_bytes
    package = Path(run["package_path"]).read_text(encoding="utf-8")
    assert "蓝色外套" in package
    assert "棕色外套" not in package

    duplicate = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    assert duplicate.status_code == 409
    assert "already sealed" in duplicate.text

    (exports / "E01_MASTER.mp4").write_bytes(b"tampered")
    damaged = api.get(f"/v1/production-runs/{run['id']}/rendered-output-integrity").json()
    assert damaged["integrity_ok"] is False
    assert damaged["failures"] == ["rendered output digest mismatch: E01_MASTER.mp4"]


def test_verified_seal_and_human_qa_complete_atomically_and_retry_safely(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _project, episode, entity = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    advance_episode_to_qa(api, episode["id"])
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    master_path = exports / "E01_MASTER.mp4"
    master_bytes = create_playable_mp4(master_path)
    master_sha = hashlib.sha256(master_bytes).hexdigest()
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_shot_manifest(run, exports)
    write_postproduction_lineage_manifest(run, exports)
    write_visual_continuity_manifest(run, exports)
    (exports / "E01_FINAL_QA.json").write_text(
        json.dumps(
            {
                "schema_version": "nalu.final-qa-evidence/v1",
                "run_id": run["id"],
                "master_sha256": master_sha,
                "original_resolution_reviewed": True,
                "picture_passed": True,
                "audio_sync_passed": True,
                "captions_passed": True,
                "continuity_passed": True,
                "safety_passed": True,
                "reviewed_by": "human-reviewer",
                "review_channel": "human_original_resolution",
                "reviewed_at": "2026-08-30T06:00:00Z",
                "notes": "自动化测试中的人工证据格式夹具，不作为真实人工 QA 声明。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    seal = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(
            include_qa=True,
            include_shot_manifest=True,
            include_postproduction_manifest=True,
            include_visual_continuity_manifest=True,
        ),
    ).json()
    assert (
        api.post(f"/v1/production-runs/{run['id']}/media-structure-qa").json()["status"] == "PASS"
    )
    assert api.post(f"/v1/production-runs/{run['id']}/decoded-media-qa").json()["status"] == "PASS"
    master_download = api.get(f"/v1/production-runs/{run['id']}/sealed-master")
    assert master_download.status_code == 200
    assert master_download.content == master_bytes
    assert master_download.headers["x-nalu-master-sha256"] == master_sha
    semantic_qa = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    ).json()
    assert semantic_qa["status"] == "PASS"
    assert semantic_qa["semantic_asr"]["recall"] == 1.0
    assert semantic_qa["shot_boundaries"]["passed_boundary_count"] == 1
    lineage_qa = api.post(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa").json()
    assert lineage_qa["status"] == "PASS"
    assert lineage_qa["shot_selection"]["shot_count"] == 1
    assert {stem["layer"] for stem in lineage_qa["audio_mix"]["stems"]} == {
        "dialogue",
        "ambience",
        "foley",
        "music",
        "sfx",
    }
    assert lineage_qa["audio_mix"]["published_mix"]["master_energy_similarity"] >= 0.98
    completion_payload = {
        "output_seal_sha256": seal["manifest_sha256"],
        "completed_by": "local-user",
        "spoken_confirmation": "我确认这份成片和人工质量检查记录",
    }
    missing_visual = api.post(
        f"/v1/production-runs/{run['id']}/complete",
        json=completion_payload,
    )
    assert missing_visual.status_code == 409
    repair = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in repair["repair_tasks"]] == [
        "visual_continuity_qa_presence"
    ]
    visual_qa = api.post(f"/v1/production-runs/{run['id']}/visual-continuity-qa").json()
    assert visual_qa["status"] == "PASS"
    assert visual_qa["passed_shot_count"] == 1
    assert set(visual_qa["domain_results"]) == {
        "identity",
        "wardrobe",
        "space_axis",
        "pose",
        "props",
    }
    repository = api.app.state.repository
    with (
        patch.object(
            repository,
            "_record_episode_transition",
            side_effect=RuntimeError("simulated crash before SQLite commit"),
        ),
        pytest.raises(RuntimeError, match="simulated crash"),
    ):
        api.post(
            f"/v1/production-runs/{run['id']}/complete",
            json=completion_payload,
        )
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "qa_review"
    assert api.get(f"/v1/episodes/{episode['id']}").json()["status"] == "qa_review"
    rolled_back_events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert not any(event["event_type"] == "production_completed" for event in rolled_back_events)

    completed = api.post(
        f"/v1/production-runs/{run['id']}/complete",
        json=completion_payload,
    )
    assert completed.status_code == 200
    result = completed.json()
    assert result["run"]["status"] == "completed"
    assert result["episode"]["status"] == "ready_to_publish"
    assert result["output_seal_sha256"] == seal["manifest_sha256"]

    replay = api.post(
        f"/v1/production-runs/{run['id']}/complete",
        json=completion_payload,
    )
    assert replay.status_code == 200
    assert replay.json() == result
    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    completion_events = [event for event in events if event["event_type"] == "production_completed"]
    assert len(completion_events) == 1

    revision = api.post(
        f"/v1/library-entities/{entity['id']}/revisions",
        json={
            "name": "林叔",
            "description": "完成后供下一集使用的新设定",
            "attributes": {"wardrobe": ["棕色外套"]},
            "source_channel": "voice",
            "change_summary": "成片完成后更新下一集设定",
        },
    ).json()
    assert revision["current_revision"] == 2
    integrity = api.get(f"/v1/production-runs/{run['id']}/rendered-output-integrity").json()
    assert integrity["integrity_ok"] is True
    assert (exports / "E01_MASTER.mp4").read_bytes() == master_bytes


def test_completion_rejects_missing_or_mismatched_final_qa(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    advance_episode_to_qa(api, episode["id"])
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    (exports / "E01_MASTER.mp4").write_bytes(b"master")
    (exports / "E01_zh-CN.vtt").write_text("WEBVTT\n", encoding="utf-8")
    seal = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    ).json()
    missing = api.post(
        f"/v1/production-runs/{run['id']}/complete",
        json={
            "output_seal_sha256": seal["manifest_sha256"],
            "completed_by": "local-user",
            "spoken_confirmation": "我确认完成",
        },
    )
    assert missing.status_code == 409
    assert "exactly one sealed QA report" in missing.text
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "qa_review"
    plan = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in plan["repair_tasks"]] == ["qa_report_presence"]
    assert plan["repair_tasks"][0]["release_blocking"] is True


def test_failed_final_qa_creates_specific_idempotent_repair_tasks(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    advance_episode_to_qa(api, episode["id"])
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    master = b"master-needing-audio-caption-and-continuity-repair"
    master_sha = hashlib.sha256(master).hexdigest()
    (exports / "E01_MASTER.mp4").write_bytes(master)
    (exports / "E01_zh-CN.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (exports / "E01_FINAL_QA.json").write_text(
        json.dumps(
            {
                "schema_version": "nalu.final-qa-evidence/v1",
                "run_id": run["id"],
                "master_sha256": master_sha,
                "original_resolution_reviewed": True,
                "picture_passed": True,
                "audio_sync_passed": False,
                "captions_passed": False,
                "continuity_passed": False,
                "safety_passed": True,
                "reviewed_by": "human-reviewer",
                "review_channel": "human_original_resolution",
                "reviewed_at": "2026-08-30T07:30:00Z",
                "notes": "三个发布门禁失败。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    seal = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_qa=True),
    ).json()
    completion = {
        "output_seal_sha256": seal["manifest_sha256"],
        "completed_by": "local-user",
        "spoken_confirmation": "我确认检查结果",
    }
    first = api.post(f"/v1/production-runs/{run['id']}/complete", json=completion)
    second = api.post(f"/v1/production-runs/{run['id']}/complete", json=completion)
    assert first.status_code == second.status_code == 409
    plan = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan").json()
    assert plan["output_seal_sha256"] == seal["manifest_sha256"]
    assert plan["master_sha256"] == master_sha
    assert len(plan["plan_sha256"]) == 64
    assert [task["code"] for task in plan["repair_tasks"]] == [
        "audio_sync_passed",
        "captions_passed",
        "continuity_passed",
    ]
    assert all(task["required_action"] for task in plan["repair_tasks"])
    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    repair_events = [
        event for event in events if event["event_type"] == "postproduction_repair_required"
    ]
    assert len(repair_events) == 1
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "qa_review"

    plan_path = Path(run["package_path"]).parent / "postproduction-repair-plan.json"
    tampered = json.loads(plan_path.read_text(encoding="utf-8"))
    tampered["repair_tasks"][0]["required_action"] = "跳过返修"
    plan_path.write_text(
        json.dumps(tampered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rejected_plan = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan")
    assert rejected_plan.status_code == 409
    assert "digest mismatch" in rejected_plan.text


def test_media_structure_and_caption_timeline_golden_fixtures(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    (exports / "E01_MASTER.mp4").write_bytes(minimal_mp4())
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.800\n回家\n",
        encoding="utf-8",
    )
    write_shot_manifest(run, exports)
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    passed = api.post(f"/v1/production-runs/{run['id']}/media-structure-qa").json()
    assert passed["status"] == "PASS"
    assert passed["mp4"]["duration_seconds"] == 2.0
    assert passed["mp4"]["top_level_boxes"] == ["ftyp", "moov", "mdat"]
    assert passed["captions"]["cue_count"] == 1
    assert passed["failures"] == []

    _, failed_episode, _ = approved_episode_with_library(api)
    failed_run = api.post(
        f"/v1/episodes/{failed_episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    api.app.state.repository.update_run_status(failed_run["id"], RunStatus.QA_REVIEW)
    failed_exports = Path(failed_run["package_path"]).parent / "qingshan-workspace" / "exports"
    (failed_exports / "E01_MASTER.mp4").write_bytes(minimal_mp4(include_media_data=False))
    (failed_exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:03.000\n超出成片\n",
        encoding="utf-8",
    )
    api.post(
        f"/v1/production-runs/{failed_run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    failed = api.post(f"/v1/production-runs/{failed_run['id']}/media-structure-qa").json()
    assert failed["status"] == "FAIL"
    assert "mp4:MP4_MDAT_MISSING" in failed["failures"]
    assert "captions:WEBVTT_CUE_EXCEEDS_MASTER_DURATION" in failed["failures"]
    repair = api.get(f"/v1/production-runs/{failed_run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in repair["repair_tasks"]] == [
        "caption_timeline",
        "mp4_structure",
    ]


def test_decoded_media_gates_playable_and_frozen_silent_golden_fixtures(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    create_playable_mp4(exports / "E01_MASTER.mp4")
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    passed = api.post(f"/v1/production-runs/{run['id']}/decoded-media-qa")
    assert passed.status_code == 200
    report = passed.json()
    assert report["status"] == "PASS"
    assert report["video"]["frame_count"] == 20
    assert report["audio"]["voiced_ratio"] > 0.9
    assert report["caption_speech_alignment"]["aligned_ratio"] == 1.0
    assert report["caption_speech_alignment"]["semantic_asr_verified"] is False
    assert api.get(f"/v1/production-runs/{run['id']}/decoded-media-qa").json() == report

    _, failed_episode, _ = approved_episode_with_library(api)
    failed_run = api.post(
        f"/v1/episodes/{failed_episode['id']}/production-runs", json={"dry_run": True}
    ).json()
    api.app.state.repository.update_run_status(failed_run["id"], RunStatus.QA_REVIEW)
    failed_exports = Path(failed_run["package_path"]).parent / "qingshan-workspace" / "exports"
    create_playable_mp4(failed_exports / "E01_MASTER.mp4", frozen=True, silent=True)
    (failed_exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n无人声字幕\n", encoding="utf-8"
    )
    api.post(
        f"/v1/production-runs/{failed_run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    failed = api.post(f"/v1/production-runs/{failed_run['id']}/decoded-media-qa").json()
    assert failed["status"] == "FAIL"
    assert "video:VIDEO_FRAME_REPEAT_EXCESSIVE" in failed["failures"]
    assert "audio:AUDIO_VOICE_ACTIVITY_TOO_LOW" in failed["failures"]
    assert "alignment:CAPTION_SPEECH_ALIGNMENT_TOO_LOW" in failed["failures"]
    repair = api.get(f"/v1/production-runs/{failed_run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in repair["repair_tasks"]] == [
        "audio_vad",
        "caption_speech_alignment",
        "decoded_video",
        "frame_repeat",
    ]


def test_semantic_asr_and_authored_boundary_failures_are_release_blocking(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    master = create_playable_mp4(exports / "E01_MASTER.mp4")
    master_sha = hashlib.sha256(master).hexdigest()
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_shot_manifest(run, exports, corrupt_contract=True)
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_shot_manifest=True),
    )
    assert (
        api.post(f"/v1/production-runs/{run['id']}/media-structure-qa").json()["status"] == "PASS"
    )
    assert api.post(f"/v1/production-runs/{run['id']}/decoded-media-qa").json()["status"] == "PASS"
    failed = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha, transcript="天气不错"),
    )
    assert failed.status_code == 200
    report = failed.json()
    assert report["status"] == "FAIL"
    assert "asr:ASR_TRANSCRIPT_RECALL_BELOW_THRESHOLD" in report["failures"]
    assert "boundary:SHOT_TRANSITION_CONTRACT_DIGEST_MISMATCH" in report["failures"]
    assert api.get(f"/v1/production-runs/{run['id']}/semantic-media-qa").json() == report
    repair = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in repair["repair_tasks"]] == [
        "semantic_asr",
        "shot_boundary",
    ]
    changed = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha, transcript="回家"),
    )
    assert changed.status_code == 409
    assert "different evidence" in changed.text


def test_postproduction_lineage_rejects_unadmitted_shot_and_blocks_release(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    create_playable_mp4(exports / "E01_MASTER.mp4")
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_postproduction_lineage_manifest(run, exports, corrupt_admission=True)
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_postproduction_manifest=True),
    )
    report = api.post(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa").json()
    assert report["status"] == "FAIL"
    assert "SHOT_NOT_ADMITTED_FOR_ASSEMBLY" in report["failures"]
    assert report["shot_selection"]["shots"][0]["status"] == "FAIL"
    assert api.get(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa").json() == report
    repair = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in repair["repair_tasks"]] == ["shot_selection"]
    assert repair["repair_tasks"][0]["release_blocking"] is True


def test_visual_continuity_redecodes_frames_and_creates_domain_repair(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    create_playable_mp4(exports / "E01_MASTER.mp4")
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_visual_continuity_manifest(run, exports, corrupt_domain="wardrobe")
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_visual_continuity_manifest=True),
    )

    response = api.post(f"/v1/production-runs/{run['id']}/visual-continuity-qa")
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "FAIL"
    assert report["decoded_frame_count"] == 20
    assert "WARDROBE_VALUE_MISMATCH" in report["failures"]
    assert report["domain_results"]["wardrobe"]["status"] == "FAIL"
    assert report["domain_results"]["identity"]["status"] == "PASS"
    assert api.get(f"/v1/production-runs/{run['id']}/visual-continuity-qa").json() == report
    repair = api.get(f"/v1/production-runs/{run['id']}/postproduction-repair-plan").json()
    assert [task["code"] for task in repair["repair_tasks"]] == ["visual_wardrobe"]
    assert repair["repair_tasks"][0]["release_blocking"] is True

    _, frame_episode, _ = approved_episode_with_library(api)
    frame_run = api.post(
        f"/v1/episodes/{frame_episode['id']}/production-runs", json={"dry_run": True}
    ).json()
    api.app.state.repository.update_run_status(frame_run["id"], RunStatus.QA_REVIEW)
    frame_exports = (
        Path(frame_run["package_path"]).parent / "qingshan-workspace" / "exports"
    )
    create_playable_mp4(frame_exports / "E01_MASTER.mp4")
    (frame_exports / "E01_zh-CN.vtt").write_text("WEBVTT\n", encoding="utf-8")
    write_visual_continuity_manifest(frame_run, frame_exports, corrupt_frame=True)
    api.post(
        f"/v1/production-runs/{frame_run['id']}/rendered-output-seal",
        json=seal_payload(include_visual_continuity_manifest=True),
    )
    frame_report = api.post(
        f"/v1/production-runs/{frame_run['id']}/visual-continuity-qa"
    ).json()
    assert frame_report["status"] == "FAIL"
    assert "FRAME_SHA_MISMATCH" in frame_report["failures"]
    assert "IDENTITY_FRAME_NOT_VERIFIED" in frame_report["failures"]
    frame_repair = api.get(
        f"/v1/production-runs/{frame_run['id']}/postproduction-repair-plan"
    ).json()
    assert {task["code"] for task in frame_repair["repair_tasks"]} == {
        "visual_continuity_manifest",
        "visual_identity",
        "visual_wardrobe",
        "visual_space_axis",
        "visual_pose",
        "visual_prop",
    }


def test_authored_boundary_requires_visual_change_when_contract_says_so(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    master = create_playable_mp4(exports / "E01_MASTER.mp4", hold_across_boundary=True)
    master_sha = hashlib.sha256(master).hexdigest()
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_shot_manifest(run, exports)
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_shot_manifest=True),
    )
    assert (
        api.post(f"/v1/production-runs/{run['id']}/media-structure-qa").json()["status"] == "PASS"
    )
    assert api.post(f"/v1/production-runs/{run['id']}/decoded-media-qa").json()["status"] == "PASS"
    report = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    ).json()
    assert report["status"] == "FAIL"
    assert "boundary:BOUNDARY_EXPECTED_VISUAL_CHANGE_MISSING" in report["failures"]


def test_completed_media_qa_creates_offline_release_package_without_publishing(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    advance_episode_to_qa(api, episode["id"])
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    master_path = exports / "E01_MASTER.mp4"
    master = create_playable_mp4(master_path)
    master_sha = hashlib.sha256(master).hexdigest()
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.900\n回家\n",
        encoding="utf-8",
    )
    write_shot_manifest(run, exports)
    write_postproduction_lineage_manifest(run, exports)
    write_visual_continuity_manifest(run, exports)
    (exports / "E01_COVER.jpg").write_bytes(b"sealed-cover-fixture")
    (exports / "E01_FINAL_QA.json").write_text(
        json.dumps(
            {
                "schema_version": "nalu.final-qa-evidence/v1",
                "run_id": run["id"],
                "master_sha256": master_sha,
                "original_resolution_reviewed": True,
                "picture_passed": True,
                "audio_sync_passed": True,
                "captions_passed": True,
                "continuity_passed": True,
                "safety_passed": True,
                "reviewed_by": "human-reviewer",
                "review_channel": "human_original_resolution",
                "reviewed_at": "2026-08-30T08:00:00Z",
                "notes": "结构夹具中的人工证据格式，不作为真实审片声明。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = seal_payload(
        include_qa=True,
        include_shot_manifest=True,
        include_postproduction_manifest=True,
        include_visual_continuity_manifest=True,
    )
    payload["artifacts"].append(
        {
            "kind": "cover",
            "relative_path": "E01_COVER.jpg",
            "media_type": "image/jpeg",
        }
    )
    seal = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=payload,
    ).json()
    media_qa = api.post(f"/v1/production-runs/{run['id']}/media-structure-qa").json()
    assert media_qa["status"] == "PASS"
    decoded_qa = api.post(f"/v1/production-runs/{run['id']}/decoded-media-qa").json()
    assert decoded_qa["status"] == "PASS"
    semantic_qa = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    ).json()
    assert semantic_qa["status"] == "PASS"
    lineage_qa = api.post(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa").json()
    assert lineage_qa["status"] == "PASS"
    visual_qa = api.post(f"/v1/production-runs/{run['id']}/visual-continuity-qa").json()
    assert visual_qa["status"] == "PASS"
    too_early = api.post(
        f"/v1/production-runs/{run['id']}/release-package",
        json={
            "title": "离开故乡",
            "description": "第一集",
            "prepared_by": "local-user",
        },
    )
    assert too_early.status_code == 409

    completed = api.post(
        f"/v1/production-runs/{run['id']}/complete",
        json={
            "output_seal_sha256": seal["manifest_sha256"],
            "completed_by": "local-user",
            "spoken_confirmation": "我确认这份成片",
        },
    )
    assert completed.status_code == 200
    release_request = {
        "title": "离开故乡",
        "description": "林叔穿着蓝色外套回到家。",
        "prepared_by": "local-user",
    }
    release = api.post(
        f"/v1/production-runs/{run['id']}/release-package",
        json=release_request,
    )
    assert release.status_code == 201
    package = release.json()
    assert package["publishing_enabled"] is False
    assert package["platform_approvals"] == []
    assert package["output_seal_sha256"] == seal["manifest_sha256"]
    assert package["media_qa_report_sha256"] == media_qa["report_sha256"]
    assert package["decoded_media_qa_report_sha256"] == decoded_qa["report_sha256"]
    assert package["semantic_media_qa_report_sha256"] == semantic_qa["report_sha256"]
    assert package["postproduction_lineage_qa_report_sha256"] == lineage_qa["report_sha256"]
    assert package["visual_continuity_qa_report_sha256"] == visual_qa["report_sha256"]
    assert {artifact["kind"] for artifact in package["artifacts"]} >= {
        "master_video",
        "captions",
        "cover",
    }
    replay = api.post(
        f"/v1/production-runs/{run['id']}/release-package",
        json=release_request,
    )
    assert replay.status_code == 201
    assert replay.json() == package
    changed = api.post(
        f"/v1/production-runs/{run['id']}/release-package",
        json={**release_request, "title": "静默替换标题"},
    )
    assert changed.status_code == 409
    assert "different metadata" in changed.text

    mismatch = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json={
            "platform": "youtube",
            "confirmed_platform": "bilibili",
            "channel_reference": "local-test-channel",
            "approved_by": "local-user",
            "spoken_confirmation": "我确认进行 YouTube 发布演练",
        },
    )
    assert mismatch.status_code == 422

    dry_run_request = {
        "platform": "youtube",
        "confirmed_platform": "youtube",
        "channel_reference": "local-test-channel",
        "approved_by": "local-user",
        "spoken_confirmation": "我确认进行 YouTube 发布演练",
    }
    publication = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    )
    assert publication.status_code == 201
    dry_run = publication.json()
    assert dry_run["platform"] == "youtube"
    assert dry_run["adapter_version"] == "nalu.youtube-dry-run/v1"
    assert dry_run["dry_run"] is True
    assert dry_run["network_call_performed"] is False
    assert dry_run["episode_state_changed"] is False
    assert dry_run["compiled_plan"]["network_operations"] == []
    assert dry_run["compiled_plan"]["media"]["master"]["sha256"] == master_sha
    assert len(dry_run["duplicate_guard_sha256"]) == 64
    assert api.get(f"/v1/episodes/{episode['id']}").json()["status"] == "ready_to_publish"
    assert (
        api.get(f"/v1/production-runs/{run['id']}/publication-dry-runs/youtube").json() == dry_run
    )
    assert (
        api.post(
            f"/v1/production-runs/{run['id']}/publication-dry-runs",
            json=dry_run_request,
        ).json()
        == dry_run
    )
    changed_channel = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json={**dry_run_request, "channel_reference": "different-channel"},
    )
    assert changed_channel.status_code == 409
    assert "different approval" in changed_channel.text

    with api.app.state.repository.db.connect() as connection:
        connection.execute(
            "UPDATE projects SET audience_mode = 'child' WHERE id = ?",
            (package["project_id"],),
        )
    child_without_guardian = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json={
            "platform": "bilibili",
            "confirmed_platform": "bilibili",
            "channel_reference": "guardian-test-channel",
            "approved_by": "guardian",
            "spoken_confirmation": "我确认进行哔哩哔哩发布演练",
            "guardian_approval": False,
        },
    )
    assert child_without_guardian.status_code == 409
    assert "guardian approval" in child_without_guardian.text
    child_with_guardian = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json={
            "platform": "bilibili",
            "confirmed_platform": "bilibili",
            "channel_reference": "guardian-test-channel",
            "approved_by": "guardian",
            "spoken_confirmation": "我确认进行哔哩哔哩发布演练",
            "guardian_approval": True,
        },
    )
    assert child_with_guardian.status_code == 201
    assert child_with_guardian.json()["adapter_version"] == "nalu.bilibili-dry-run/v1"
    assert child_with_guardian.json()["approval"]["guardian_approval"] is True

    dry_run_path = Path(run["package_path"]).parent / "publication-dry-run-youtube.json"
    tampered = json.loads(dry_run_path.read_text(encoding="utf-8"))
    tampered["compiled_plan"]["channel_reference"] = "tampered-channel"
    dry_run_path.write_text(json.dumps(tampered), encoding="utf-8")
    damaged_dry_run = api.get(f"/v1/production-runs/{run['id']}/publication-dry-runs/youtube")
    assert damaged_dry_run.status_code == 409
    assert "digest mismatch" in damaged_dry_run.text


def test_output_seal_fails_closed_for_state_paths_and_empty_files(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    not_qa = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    assert not_qa.status_code == 409
    assert "QA review" in not_qa.text

    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    traversal = seal_payload()
    traversal["artifacts"][0]["relative_path"] = "../production-package.json"
    assert (
        api.post(
            f"/v1/production-runs/{run['id']}/rendered-output-seal", json=traversal
        ).status_code
        == 422
    )

    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    (exports / "E01_MASTER.mp4").write_bytes(b"")
    (exports / "E01_zh-CN.vtt").write_text("WEBVTT\n", encoding="utf-8")
    empty = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    assert empty.status_code == 409
    assert "empty" in empty.text

    (exports / "E01_MASTER.mp4").unlink()
    (exports / "E01_MASTER.mp4").symlink_to(exports / "E01_zh-CN.vtt")
    linked = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    assert linked.status_code == 409
    assert "regular file" in linked.text

    no_master = seal_payload()
    no_master["artifacts"] = no_master["artifacts"][1:]
    assert (
        api.post(
            f"/v1/production-runs/{run['id']}/rendered-output-seal", json=no_master
        ).status_code
        == 422
    )
