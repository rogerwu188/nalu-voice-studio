import hashlib
import json
import math
import sqlite3
import struct
import subprocess
import threading
import urllib.parse
from array import array
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import av
import pytest
from fastapi.testclient import TestClient
from nalu_runtime import postproduction_lineage_qa
from nalu_runtime.app import create_app
from nalu_runtime.models import RunStatus
from nalu_runtime.postproduction_lineage_qa import audio_energy_fingerprint
from nalu_runtime.publication_learning import (
    PublicationMetricsVerification,
    PublicationVerification,
)
from nalu_runtime.semantic_recognizer import (
    AppleSpeechRecognizer,
    LocalSemanticRecognition,
    SemanticRecognizerError,
)


class DeterministicSemanticRecognizer:
    def __init__(self) -> None:
        self.transcript = "回家"
        self.source_master_sha256_override: str | None = None
        self.decoded_audio_fingerprint_override: str | None = None
        self.network_used = False
        self.calls = 0

    def recognize(
        self, master_path: Path, *, source_master_sha256: str
    ) -> LocalSemanticRecognition:
        self.calls += 1
        return LocalSemanticRecognition(
            transcript=self.transcript,
            segments=[
                {
                    "start_seconds": 0.1,
                    "end_seconds": 1.8,
                    "text": self.transcript,
                    "confidence": 0.95,
                }
            ],
            recognizer_id="apple-speech-on-device",
            recognizer_version="macOS-test-double",
            locale="zh-CN",
            generated_at="2026-08-31T00:20:00Z",
            source_master_sha256=(
                self.source_master_sha256_override or source_master_sha256
            ),
            decoded_audio_fingerprint=(
                self.decoded_audio_fingerprint_override
                or audio_energy_fingerprint(master_path)
            ),
            recognizer_executable_sha256=hashlib.sha256(
                b"deterministic-local-semantic-recognizer-fixture"
            ).hexdigest(),
            network_used=self.network_used,
        )


def client(tmp_path: Path, publication_learning_verifier=None) -> TestClient:
    return TestClient(
        create_app(
            tmp_path / "test.sqlite3",
            tmp_path / "data",
            publication_learning_verifier=publication_learning_verifier,
            semantic_recognizer=DeterministicSemanticRecognizer(),
        )
    )


class DeterministicPublicationVerifier:
    def __init__(self, release_manifest_sha256: str):
        self.release_manifest_sha256 = release_manifest_sha256
        self.publication_calls = 0
        self.metrics_calls = 0

    def lookup_publication(self, **request) -> PublicationVerification:
        self.publication_calls += 1
        return PublicationVerification(
            platform=request["platform"],
            remote_publication_id=request["remote_publication_id"],
            remote_state="published",
            release_manifest_sha256=self.release_manifest_sha256,
            published_at="2026-09-01T06:00:00+00:00",
            channel_reference=request["channel_reference"],
            evidence={"provider": "authorized-read-only-fixture", "status": "published"},
        )

    def lookup_metrics(self, **request) -> PublicationMetricsVerification:
        self.metrics_calls += 1
        return PublicationMetricsVerification(
            platform=request["platform"],
            remote_publication_id=request["remote_publication_id"],
            window_start=request["window_start"],
            window_end=request["window_end"],
            views=1000,
            unique_viewers=800,
            watch_time_seconds=32000,
            average_view_duration_seconds=32.0,
            completion_rate=0.52,
            likes=80,
            comments=30,
            shares=40,
            followers_gained=12,
            evidence={"provider": "authorized-read-only-fixture", "snapshot": "metrics-1"},
        )


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
            "attributes": {
                "wardrobe": ["蓝色外套"],
                "space_axis": "screen-left",
                "pose": "standing",
                "held_props": [],
            },
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


class DeterministicVisualAnalyzer:
    version = "test-apple-vision-baseline/v1"
    model_sha256 = hashlib.sha256(b"deterministic-local-vision-model").hexdigest()

    def __init__(self) -> None:
        self.call_count = 0

    def analyze(self, request: dict, working_directory: Path) -> dict:
        self.call_count += 1
        assert working_directory.is_dir()
        assert request["schema_version"] == "nalu.apple-vision-request/v1"
        character_ids = [
            item["entity_id"] for item in request["subjects"] if item["kind"] == "character"
        ]
        assert len(character_ids) == 1
        return {
            "schema_version": "nalu.apple-vision-measurements/v1",
            "framework": "Apple Vision test double",
            "local_analysis": True,
            "shots": [
                {
                    "shot_id": frame["shot_id"],
                    "frame_sha256": frame["frame_sha256"],
                    "subjects": [
                        {
                            "entity_id": character_ids[0],
                            "identity_distance": 0.0,
                            "dominant_color": "蓝色",
                            "color_confidence": 0.99,
                            "space_axis": "screen-left",
                            "axis_confidence": 0.99,
                            "subject_center_x": 0.25,
                            "pose": "standing",
                            "pose_confidence": 0.99,
                            "body_joint_count": 15,
                            "prop_distances": {},
                        }
                    ],
                }
                for frame in request["frames"]
            ],
        }


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
    duration_seconds: int = 2,
) -> bytes:
    width = height = 64
    fps = 10
    sample_rate = 48000
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
                        5600 * math.sin(2 * math.pi * 440 * (sample_cursor + offset) / sample_rate)
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


def create_audio_stem(path: Path, *, frequency: int = 440, amplitude: int = 5600) -> bytes:
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
                    amplitude
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


def test_release_loudness_is_measured_from_media_and_fails_closed(tmp_path: Path) -> None:
    compliant = tmp_path / "compliant.wav"
    too_loud = tmp_path / "too-loud.wav"
    create_audio_stem(compliant)
    create_audio_stem(too_loud, amplitude=28000)

    compliant_metrics = postproduction_lineage_qa.measure_ebu_r128(compliant)
    loud_metrics = postproduction_lineage_qa.measure_ebu_r128(too_loud)

    assert compliant_metrics["measurement_standard"] == "EBU_R128_LIBAVFILTER"
    assert postproduction_lineage_qa.release_loudness_failures(
        compliant_metrics, "FINAL_MASTER"
    ) == []
    assert "FINAL_MASTER_INTEGRATED_LOUDNESS_OUT_OF_RANGE" in (
        postproduction_lineage_qa.release_loudness_failures(
            loud_metrics, "FINAL_MASTER"
        )
    )


def write_postproduction_lineage_manifest(
    run: dict,
    exports: Path,
    *,
    corrupt_admission: bool = False,
    corrupt_editorial_window: bool = False,
) -> None:
    package = json.loads(Path(run["package_path"]).read_text(encoding="utf-8"))
    master_path = exports / "E01_MASTER.mp4"
    captions_path = exports / "E01_zh-CN.vtt"
    source_path = exports / "source-clips" / "S01.mp4"
    normalized_path = exports / "normalized-segments" / "S01.mp4"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    create_playable_mp4(source_path, duration_seconds=3)
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
                    "source_out_seconds": 3.0 if corrupt_editorial_window else 2.0,
                    "source_duration_seconds": 3.0,
                    "editorial_selection": (
                        "USE_FULL_PROVIDER_MEDIA"
                        if corrupt_editorial_window
                        else "EXPLICIT_SOURCE_WINDOW"
                    ),
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
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (exports / "E01_VISUAL_CONTINUITY.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def postproduction_materialization_fixture(run: dict, exports: Path) -> dict:
    provider = exports / "provider-results"
    provider.mkdir(parents=True, exist_ok=True)
    source_path = provider / "provider-shot.mp4"
    source_bytes = create_playable_mp4(source_path)
    audio_layers = []
    for index, layer in enumerate(("dialogue", "ambience", "foley", "music", "sfx")):
        audio_path = provider / f"{layer}.wav"
        audio_bytes = create_audio_stem(audio_path, frequency=330 + index * 55)
        audio_layers.append(
            {
                "layer": layer,
                "source_relative_path": str(audio_path.relative_to(exports)),
                "source_sha256": hashlib.sha256(audio_bytes).hexdigest(),
                "source_cue_sha256s": [
                    hashlib.sha256(f"materialized-cue-{layer}".encode()).hexdigest()
                ],
                "gain_db": -3 if layer == "music" else 0,
            }
        )
    captions_path = provider / "captions.vtt"
    captions_path.write_text("WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8")
    return {
        "requested_by": "local-postproduction-worker",
        "shots": [
            {
                "shot_id": "S01",
                "source_relative_path": str(source_path.relative_to(exports)),
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "source_task_id": "provider-task-1",
                "source_receipt_sha256": hashlib.sha256(b"provider-receipt-1").hexdigest(),
                "source_in_seconds": 0,
                "source_out_seconds": 1,
            },
            {
                "shot_id": "S02",
                "source_relative_path": str(source_path.relative_to(exports)),
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "source_task_id": "provider-task-2",
                "source_receipt_sha256": hashlib.sha256(b"provider-receipt-2").hexdigest(),
                "source_in_seconds": 1,
                "source_out_seconds": 2,
            },
        ],
        "audio_layers": audio_layers,
        "captions_source_relative_path": str(captions_path.relative_to(exports)),
        "captions_source_sha256": hashlib.sha256(captions_path.read_bytes()).hexdigest(),
        "subtitle_contract_sha256": hashlib.sha256(b"subtitle-contract").hexdigest(),
        "width": 64,
        "height": 64,
        "frame_rate": 10,
    }


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


def prepare_semantic_qa_fixture(api: TestClient) -> tuple[dict, str]:
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    master = create_playable_mp4(exports / "E01_MASTER.mp4")
    master_sha = hashlib.sha256(master).hexdigest()
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_shot_manifest(run, exports)
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_shot_manifest=True),
    ).raise_for_status()
    assert (
        api.post(f"/v1/production-runs/{run['id']}/media-structure-qa").json()["status"]
        == "PASS"
    )
    assert (
        api.post(f"/v1/production-runs/{run['id']}/decoded-media-qa").json()["status"]
        == "PASS"
    )
    return run, master_sha


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


def test_rendered_output_seal_recovers_exactly_one_event_after_file_commit_crash(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _project, episode, _entity = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    run_directory = Path(run["package_path"]).parent
    exports = run_directory / "qingshan-workspace" / "exports"
    master_bytes = b"durable-master-before-event-crash"
    (exports / "E01_MASTER.mp4").write_bytes(master_bytes)
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.000\n回家\n", encoding="utf-8"
    )
    request = seal_payload()

    repository = api.app.state.repository
    with (
        patch.object(
            repository,
            "append_run_event",
            side_effect=RuntimeError("simulated exit before seal event commit"),
        ),
        pytest.raises(RuntimeError, match="simulated exit"),
    ):
        api.post(
            f"/v1/production-runs/{run['id']}/rendered-output-seal",
            json=request,
        )

    seal_path = run_directory / "rendered-output-seal.json"
    durable_bytes = seal_path.read_bytes()
    durable_sha256 = hashlib.sha256(durable_bytes).hexdigest()
    assert not any(
        event.event_type == "rendered_outputs_sealed"
        for event in repository.list_run_events(run["id"])
    )

    restarted = client(tmp_path)
    (exports / "E01_MASTER.mp4").write_bytes(b"changed-after-seal")
    rejected = restarted.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=request,
    )
    assert rejected.status_code == 409
    assert "already sealed" in rejected.text
    assert not any(
        event["event_type"] == "rendered_outputs_sealed"
        for event in restarted.get(f"/v1/production-runs/{run['id']}/events").json()
    )
    (exports / "E01_MASTER.mp4").write_bytes(master_bytes)

    recovered = restarted.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=request,
    )
    assert recovered.status_code == 201, recovered.text
    assert seal_path.read_bytes() == durable_bytes
    assert hashlib.sha256(seal_path.read_bytes()).hexdigest() == durable_sha256
    events = restarted.get(f"/v1/production-runs/{run['id']}/events").json()
    seal_events = [event for event in events if event["event_type"] == "rendered_outputs_sealed"]
    assert len(seal_events) == 1
    assert seal_events[0]["payload"]["manifest_sha256"] == recovered.json()["manifest_sha256"]
    assert seal_events[0]["payload"]["recovered_after_restart"] is True

    duplicate = restarted.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=request,
    )
    assert duplicate.status_code == 409
    assert "already sealed" in duplicate.text
    assert len(
        [
            event
            for event in restarted.get(f"/v1/production-runs/{run['id']}/events").json()
            if event["event_type"] == "rendered_outputs_sealed"
        ]
    ) == 1


def test_media_qa_recovers_exactly_one_event_after_durable_report_crash(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _project, episode, _entity = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    run_directory = Path(run["package_path"]).parent
    exports = run_directory / "qingshan-workspace" / "exports"
    create_playable_mp4(exports / "E01_MASTER.mp4")
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    ).raise_for_status()

    repository = api.app.state.repository
    with (
        patch.object(
            repository,
            "append_run_event_once",
            side_effect=RuntimeError("simulated exit before media QA event commit"),
        ),
        pytest.raises(RuntimeError, match="simulated exit"),
    ):
        api.post(f"/v1/production-runs/{run['id']}/media-structure-qa")

    report_path = run_directory / "media-structure-qa.json"
    durable_bytes = report_path.read_bytes()
    durable_sha256 = hashlib.sha256(durable_bytes).hexdigest()
    assert not any(
        event.event_type == "media_structure_qa_completed"
        for event in repository.list_run_events(run["id"])
    )

    restarted = client(tmp_path)
    recovered = restarted.post(f"/v1/production-runs/{run['id']}/media-structure-qa")
    assert recovered.status_code == 200, recovered.text
    assert report_path.read_bytes() == durable_bytes
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == durable_sha256
    replay = restarted.post(f"/v1/production-runs/{run['id']}/media-structure-qa")
    assert replay.json() == recovered.json()
    events = restarted.get(f"/v1/production-runs/{run['id']}/events").json()
    report_events = [
        event for event in events if event["event_type"] == "media_structure_qa_completed"
    ]
    assert len(report_events) == 1
    assert report_events[0]["payload"]["report_sha256"] == recovered.json()["report_sha256"]

    recovered_repository = restarted.app.state.repository
    first = recovered_repository.append_run_event_once(
        run["id"],
        "qa_event_dedupe_fixture",
        dedupe_key="report_sha256",
        dedupe_value="a" * 64,
        payload={"report_sha256": "a" * 64},
    )
    replayed = recovered_repository.append_run_event_once(
        run["id"],
        "qa_event_dedupe_fixture",
        dedupe_key="report_sha256",
        dedupe_value="a" * 64,
        payload={"report_sha256": "a" * 64},
    )
    changed = recovered_repository.append_run_event_once(
        run["id"],
        "qa_event_dedupe_fixture",
        dedupe_key="report_sha256",
        dedupe_value="b" * 64,
        payload={"report_sha256": "b" * 64},
    )
    assert replayed.id == first.id
    assert changed.id != first.id
    with pytest.raises(ValueError, match="dedupe value"):
        recovered_repository.append_run_event_once(
            run["id"],
            "qa_event_dedupe_fixture",
            dedupe_key="report_sha256",
            dedupe_value="c" * 64,
            payload={"report_sha256": "different"},
        )


def test_failed_media_qa_recovers_repair_plan_after_event_commit_crash(tmp_path: Path) -> None:
    api = client(tmp_path)
    _project, episode, _entity = approved_episode_with_library(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}
    ).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    run_directory = Path(run["package_path"]).parent
    exports = run_directory / "qingshan-workspace" / "exports"
    (exports / "E01_MASTER.mp4").write_bytes(b"invalid-mp4-fixture")
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.000\n回家\n", encoding="utf-8"
    )
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal", json=seal_payload()
    ).raise_for_status()

    production = api.app.state.production
    with (
        patch.object(
            production,
            "_record_postproduction_repair_plan",
            side_effect=RuntimeError("simulated exit before repair plan"),
        ),
        pytest.raises(RuntimeError, match="simulated exit"),
    ):
        api.post(f"/v1/production-runs/{run['id']}/media-structure-qa")

    assert (run_directory / "media-structure-qa.json").is_file()
    assert not (run_directory / "postproduction-repair-plan.json").exists()
    restarted = client(tmp_path)
    replay = restarted.post(f"/v1/production-runs/{run['id']}/media-structure-qa")
    assert replay.status_code == 200
    assert replay.json()["status"] == "FAIL"
    repair = restarted.get(
        f"/v1/production-runs/{run['id']}/postproduction-repair-plan"
    )
    assert repair.status_code == 200
    assert [task["code"] for task in repair.json()["repair_tasks"]] == ["mp4_structure"]
    events = restarted.get(f"/v1/production-runs/{run['id']}/events").json()
    assert sum(event["event_type"] == "media_structure_qa_completed" for event in events) == 1
    assert sum(event["event_type"] == "postproduction_repair_required" for event in events) == 1


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
    execution = semantic_qa["recognizer_execution"]
    assert execution["source_master_sha256"] == master_sha
    assert execution["local_recognition"] is True
    assert execution["network_used"] is False
    assert len(execution["decoded_audio_fingerprint"]) == 64
    assert len(execution["recognizer_executable_sha256"]) == 64
    assert len(execution["recognizer_output_sha256"]) == 64
    assert len(execution["evidence_sha256"]) == 64
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
    published_loudness = lineage_qa["audio_mix"]["published_mix"]["release_loudness"]
    master_loudness = lineage_qa["audio_mix"]["final_master_release_loudness"]
    assert published_loudness["measurement_standard"] == "EBU_R128_LIBAVFILTER"
    assert -17 <= published_loudness["integrated_loudness_lufs"] <= -15
    assert -17 <= master_loudness["integrated_loudness_lufs"] <= -15
    assert master_loudness["true_peak_dbtp"] <= -1
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
    assert [task["code"] for task in repair["repair_tasks"]] == ["visual_continuity_qa_presence"]
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
    api.app.state.production.semantic_recognizer.transcript = "天气不错"
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
    api.app.state.production.semantic_recognizer.transcript = "回家"
    changed = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha, transcript="回家"),
    )
    assert changed.status_code == 409
    assert "different evidence" in changed.text


def test_semantic_qa_fails_closed_without_runtime_registered_recognizer(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run, master_sha = prepare_semantic_qa_fixture(api)

    response = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    )

    assert response.status_code == 409
    assert "approved local semantic recognizer is not configured" in response.text


def test_semantic_qa_ignores_client_claims_and_rejects_untrusted_execution_provenance(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    run, master_sha = prepare_semantic_qa_fixture(api)
    recognizer = api.app.state.production.semantic_recognizer

    mismatch = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha, transcript="客户端伪造文本"),
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["semantic_asr"]["transcript"] == "回家"
    assert mismatch.json()["recognizer_execution"]["recognizer_output"]["transcript"] == "回家"

    recognizer.decoded_audio_fingerprint_override = "0" * 64
    wrong_audio = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    )
    assert wrong_audio.status_code == 409
    assert "different decoded audio" in wrong_audio.text

    recognizer.decoded_audio_fingerprint_override = None
    recognizer.network_used = True
    networked = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    )
    assert networked.status_code == 409
    assert "local-only recognition execution" in networked.text


def test_stored_semantic_qa_rejects_rehashed_execution_provenance_tampering(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    run, master_sha = prepare_semantic_qa_fixture(api)
    created = api.post(
        f"/v1/production-runs/{run['id']}/semantic-media-qa",
        json=semantic_qa_payload(master_sha),
    )
    assert created.status_code == 200
    report_path = Path(run["package_path"]).parent / "semantic-media-qa.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    def canonical_sha256(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    execution = report["recognizer_execution"]
    execution["network_used"] = True
    execution["evidence_sha256"] = canonical_sha256(
        {key: value for key, value in execution.items() if key != "evidence_sha256"}
    )
    report["report_sha256"] = canonical_sha256(
        {key: value for key, value in report.items() if key != "report_sha256"}
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    network_tamper = api.get(f"/v1/production-runs/{run['id']}/semantic-media-qa")
    assert network_tamper.status_code == 409
    assert "not proven local-only" in network_tamper.text

    execution["network_used"] = False
    execution["decoded_audio_fingerprint"] = "0" * 64
    execution["evidence_sha256"] = canonical_sha256(
        {key: value for key, value in execution.items() if key != "evidence_sha256"}
    )
    report["report_sha256"] = canonical_sha256(
        {key: value for key, value in report.items() if key != "report_sha256"}
    )
    report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    audio_tamper = api.get(f"/v1/production-runs/{run['id']}/semantic-media-qa")
    assert audio_tamper.status_code == 409
    assert "decoded audio fingerprint mismatch" in audio_tamper.text


def test_apple_speech_runner_binds_executable_master_and_local_only_result(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "nalu-semantic-recognizer"
    binary.write_bytes(b"reviewed semantic recognizer fixture")
    binary.chmod(0o700)
    master_path = tmp_path / "master.mp4"
    master = create_playable_mp4(master_path)
    master_sha = hashlib.sha256(master).hexdigest()
    response = {
        "schema_version": "nalu.apple-speech-result/v1",
        "source_master_sha256": master_sha,
        "transcript": "回家",
        "segments": [
            {
                "start_seconds": 0.1,
                "end_seconds": 1.8,
                "text": "回家",
                "confidence": 0.95,
            }
        ],
        "recognizer_version": "Apple Speech fixture",
        "locale": "zh-CN",
        "generated_at": "2026-09-01T12:30:00Z",
        "local_recognition": True,
        "network_used": False,
    }

    def completed(command, **kwargs):
        request = json.loads(kwargs["input"])
        assert command == [str(binary)]
        assert request["source_master_sha256"] == master_sha
        assert request["requires_on_device_recognition"] is True
        assert request["network_fallback_allowed"] is False
        assert set(kwargs["env"]) == {"PATH", "TMPDIR", "LANG"}
        return subprocess.CompletedProcess(command, 0, json.dumps(response).encode(), b"")

    runner = AppleSpeechRecognizer(binary)
    with patch("nalu_runtime.semantic_recognizer.subprocess.run", side_effect=completed):
        result = runner.recognize(master_path, source_master_sha256=master_sha)
    assert result.transcript == "回家"
    assert result.network_used is False
    assert result.decoded_audio_fingerprint == audio_energy_fingerprint(master_path)
    assert result.recognizer_executable_sha256 == hashlib.sha256(binary.read_bytes()).hexdigest()

    response["network_used"] = True
    with (
        patch("nalu_runtime.semantic_recognizer.subprocess.run", side_effect=completed),
        pytest.raises(SemanticRecognizerError, match="local execution policy"),
    ):
        runner.recognize(master_path, source_master_sha256=master_sha)

    response["network_used"] = False
    response["segments"][0]["confidence"] = math.inf
    with (
        patch("nalu_runtime.semantic_recognizer.subprocess.run", side_effect=completed),
        pytest.raises(SemanticRecognizerError, match="segment is invalid"),
    ):
        runner.recognize(master_path, source_master_sha256=master_sha)


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


def test_postproduction_lineage_rejects_missing_real_editorial_cut(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    api.app.state.repository.update_run_status(run["id"], RunStatus.QA_REVIEW)
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    create_playable_mp4(exports / "E01_MASTER.mp4")
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.100 --> 00:01.800\n回家\n", encoding="utf-8"
    )
    write_postproduction_lineage_manifest(run, exports, corrupt_editorial_window=True)
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(include_postproduction_manifest=True),
    ).raise_for_status()

    report = api.post(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa").json()

    assert report["status"] == "FAIL"
    assert "EDITORIAL_SOURCE_WINDOW_MISSING" in report["failures"]
    assert "WHOLE_PROVIDER_MEDIA_PASSTHROUGH_FORBIDDEN" in report["failures"]
    assert report["shot_selection"]["shots"][0]["status"] == "FAIL"


def test_visual_continuity_redecodes_frames_and_creates_domain_repair(
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
    frame_exports = Path(frame_run["package_path"]).parent / "qingshan-workspace" / "exports"
    create_playable_mp4(frame_exports / "E01_MASTER.mp4")
    (frame_exports / "E01_zh-CN.vtt").write_text("WEBVTT\n", encoding="utf-8")
    write_visual_continuity_manifest(frame_run, frame_exports, corrupt_frame=True)
    api.post(
        f"/v1/production-runs/{frame_run['id']}/rendered-output-seal",
        json=seal_payload(include_visual_continuity_manifest=True),
    )
    frame_report = api.post(f"/v1/production-runs/{frame_run['id']}/visual-continuity-qa").json()
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


def test_runtime_materializes_postproduction_and_recovers_after_state_commit_crash(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    repository = api.app.state.repository
    repository.update_run_status(run["id"], RunStatus.RUNNING)
    for target in ("generating", "postproduction"):
        assert (
            api.post(
                f"/v1/episodes/{episode['id']}/transition",
                json={
                    "target_status": target,
                    "requested_by": "local-production-worker",
                    "reason": f"fixture entered {target}",
                },
            ).status_code
            == 200
        )
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    request = postproduction_materialization_fixture(run, exports)

    from nalu_runtime import postproduction_materializer

    class SimulatedProcessExit(BaseException):
        pass

    with (
        patch.object(
            postproduction_materializer,
            "_after_durable_promotion",
            side_effect=SimulatedProcessExit("simulated crash after durable promotion"),
        ),
        pytest.raises(SimulatedProcessExit, match="simulated crash"),
    ):
        api.post(
            f"/v1/production-runs/{run['id']}/postproduction-materializations",
            json=request,
        )
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "running"
    assert api.get(f"/v1/episodes/{episode['id']}").json()["status"] == "postproduction"
    finalized = list((exports / "materialized").glob("*/materialization-result.json"))
    assert len(finalized) == 1
    assert not list(exports.glob(".nalu-postproduction-*"))

    restarted = client(tmp_path)
    restarted_repository = restarted.app.state.repository
    with (
        patch.object(
            restarted_repository,
            "mark_postproduction_materialized",
            side_effect=RuntimeError("simulated crash before SQLite state commit"),
        ),
        pytest.raises(RuntimeError, match="simulated crash"),
    ):
        restarted.post(
            f"/v1/production-runs/{run['id']}/postproduction-materializations",
            json=request,
        )
    assert len(list((exports / "materialized").glob("*/materialization-result.json"))) == 1

    completed = restarted.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=request,
    )
    assert completed.status_code == 201, completed.text
    result = completed.json()
    assert result["schema_version"] == "nalu.postproduction-materialization/v1"
    assert result["master"]["kind"] == "master_video"
    assert result["captions"]["kind"] == "captions"
    assert result["postproduction_manifest"]["kind"] == "postproduction_manifest"
    assert [item["shot_id"] for item in result["normalized_segments"]] == ["S01", "S02"]
    assert {item["layer"] for item in result["audio_stems"]} == {
        "dialogue",
        "ambience",
        "foley",
        "music",
        "sfx",
    }
    assert restarted.get(f"/v1/production-runs/{run['id']}").json()["status"] == "qa_review"
    assert restarted.get(f"/v1/episodes/{episode['id']}").json()["status"] == "qa_review"
    replay = restarted.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=request,
    )
    assert replay.status_code == 201
    assert replay.json() == result
    events = restarted.get(f"/v1/production-runs/{run['id']}/events").json()
    assert sum(event["event_type"] == "postproduction_materialized" for event in events) == 1

    changed = {**request, "requested_by": "different-worker"}
    changed_response = restarted.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=changed,
    )
    assert changed_response.status_code == 409
    assert "different plan" in changed_response.text

    seal = restarted.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json={
            "sealed_by": "local-qa-worker",
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
    )
    assert seal.status_code == 201
    lineage = restarted.post(f"/v1/production-runs/{run['id']}/postproduction-lineage-qa")
    assert lineage.status_code == 200
    report = lineage.json()
    assert report["status"] == "PASS"
    assert report["shot_selection"]["shot_count"] == 2
    assert {item["layer"] for item in report["audio_mix"]["stems"]} == {
        "dialogue",
        "ambience",
        "foley",
        "music",
        "sfx",
    }

    after_seal = restarted.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=request,
    )
    assert after_seal.status_code == 409
    assert "sealed outputs cannot be rematerialized" in after_seal.text


def test_running_materialization_cancels_cooperatively_and_reaps_abandoned_stage(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    repository = api.app.state.repository
    repository.update_run_status(run["id"], RunStatus.RUNNING)
    for target in ("generating", "postproduction"):
        assert (
            api.post(
                f"/v1/episodes/{episode['id']}/transition",
                json={
                    "target_status": target,
                    "requested_by": "local-production-worker",
                    "reason": f"fixture entered {target}",
                },
            ).status_code
            == 200
        )
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    request = postproduction_materialization_fixture(run, exports)

    from nalu_runtime import postproduction_materializer

    reached_probe = threading.Event()
    permit_probe = threading.Event()
    original_check = postproduction_materializer._raise_if_cancelled

    def controlled_check(probe):
        if probe is not None and not reached_probe.is_set():
            reached_probe.set()
            if not permit_probe.wait(timeout=5):
                raise AssertionError("cancellation test did not release materialization")
        original_check(probe)

    with (
        patch.object(
            postproduction_materializer,
            "_raise_if_cancelled",
            side_effect=controlled_check,
        ),
        ThreadPoolExecutor(max_workers=1) as pool,
    ):
        future = pool.submit(
            api.post,
            f"/v1/production-runs/{run['id']}/postproduction-materializations",
            json=request,
        )
        assert reached_probe.wait(timeout=5)
        cancelled = api.post(
            f"/v1/production-runs/{run['id']}/cancel",
            json={
                "requested_by": "local-user",
                "reason": "用户在长时后期中要求暂停",
            },
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        permit_probe.set()
        response = future.result(timeout=10)

    assert response.status_code == 409
    assert "materialization was cancelled" in response.text
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "cancelled"
    assert not list(exports.glob(".nalu-postproduction-*"))
    assert not list((exports / "materialized").glob("*/materialization-result.json"))
    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert sum(event["event_type"] == "run_cancelled" for event in events) == 1
    assert not any(event["event_type"] == "postproduction_materialized" for event in events)

    resumed = api.post(
        f"/v1/production-runs/{run['id']}/resume",
        json={
            "requested_by": "local-user",
            "reason": "继续未完成的后期制作",
            "resume_from_preflight": False,
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"
    repository.update_run_status(run["id"], RunStatus.RUNNING)
    abandoned = exports / ".nalu-postproduction-abandoned"
    abandoned.mkdir()
    (abandoned / "partial.wav").write_bytes(b"incomplete")

    completed = api.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=request,
    )
    assert completed.status_code == 201, completed.text
    assert not abandoned.exists()
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "qa_review"
    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert sum(event["event_type"] == "postproduction_materialized" for event in events) == 1


def test_postproduction_rejects_whole_provider_media_passthrough(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    repository = api.app.state.repository
    repository.update_run_status(run["id"], RunStatus.RUNNING)
    for target in ("generating", "postproduction"):
        api.post(
            f"/v1/episodes/{episode['id']}/transition",
            json={
                "target_status": target,
                "requested_by": "local-production-worker",
                "reason": f"fixture entered {target}",
            },
        ).raise_for_status()
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    request = postproduction_materialization_fixture(run, exports)
    request["shots"] = [
        {
            **request["shots"][0],
            "source_in_seconds": 0,
            "source_out_seconds": 2,
        }
    ]

    response = api.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=request,
    )

    assert response.status_code == 409
    assert "whole-provider-media passthrough is forbidden" in response.text


def test_local_visual_analysis_rehashes_references_decodes_master_and_recovers(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project, episode, _ = approved_episode_with_library(api)
    reference_bytes = b"local-character-reference"
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "lin-shu.jpg",
            "kind": "character_image",
            "name": "林叔参考照",
            "subject_name": "林叔",
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "我同意仅在这个项目的本机进行视觉核对",
        },
        content=reference_bytes,
        headers={"Content-Type": "image/jpeg"},
    )
    assert imported.status_code == 201
    reference_path = Path(urllib.parse.urlparse(imported.json()["local_uri"]).path)

    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    repository = api.app.state.repository
    repository.update_run_status(run["id"], RunStatus.RUNNING)
    for target in ("generating", "postproduction"):
        assert (
            api.post(
                f"/v1/episodes/{episode['id']}/transition",
                json={
                    "target_status": target,
                    "requested_by": "local-production-worker",
                    "reason": f"fixture entered {target}",
                },
            ).status_code
            == 200
        )
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    materialized = api.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=postproduction_materialization_fixture(run, exports),
    )
    assert materialized.status_code == 201
    materialization = materialized.json()

    analyzer = DeterministicVisualAnalyzer()
    api.app.state.production.visual_analyzer = analyzer
    reference_path.write_bytes(b"tampered-reference")
    rejected = api.post(f"/v1/production-runs/{run['id']}/local-visual-analysis")
    assert rejected.status_code == 409
    assert "reference digest changed" in rejected.text
    assert analyzer.call_count == 0
    reference_path.write_bytes(reference_bytes)

    with (
        patch.object(
            repository,
            "record_local_visual_analysis",
            side_effect=RuntimeError("simulated crash before visual event commit"),
        ),
        pytest.raises(RuntimeError, match="simulated crash"),
    ):
        api.post(f"/v1/production-runs/{run['id']}/local-visual-analysis")

    result_path = Path(run["package_path"]).parent / "local-visual-analysis-result.json"
    assert result_path.is_file()
    completed = api.post(f"/v1/production-runs/{run['id']}/local-visual-analysis")
    assert completed.status_code == 201
    result = completed.json()
    assert result["schema_version"] == "nalu.local-visual-analysis/v1"
    assert result["status"] == "PASS"
    assert result["provider_upload_performed"] is False
    assert result["analyzed_shot_count"] == 2
    assert analyzer.call_count == 1
    assert api.post(f"/v1/production-runs/{run['id']}/local-visual-analysis").json() == result
    assert analyzer.call_count == 1
    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert sum(event["event_type"] == "local_visual_analysis_completed" for event in events) == 1

    seal = api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json={
            "sealed_by": "local-qa-worker",
            "artifacts": [
                {
                    "kind": item["kind"],
                    "relative_path": item["relative_path"],
                    "media_type": item["media_type"],
                }
                for item in (
                    materialization["master"],
                    materialization["captions"],
                    materialization["postproduction_manifest"],
                    result["manifest"],
                )
            ],
        },
    )
    assert seal.status_code == 201
    visual_qa = api.post(f"/v1/production-runs/{run['id']}/visual-continuity-qa")
    assert visual_qa.status_code == 200
    report = visual_qa.json()
    assert report["status"] == "PASS"
    assert report["shot_count"] == 2
    assert report["passed_shot_count"] == 2
    manifest = json.loads((exports / result["manifest"]["relative_path"]).read_text())
    assert manifest["analyzer"]["local_analysis"] is True
    assert manifest["analyzer"]["provider_upload_performed"] is False


def test_postproduction_materializer_rejects_drift_and_unsafe_sources(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    repository = api.app.state.repository
    repository.update_run_status(run["id"], RunStatus.RUNNING)
    for target in ("generating", "postproduction"):
        api.post(
            f"/v1/episodes/{episode['id']}/transition",
            json={
                "target_status": target,
                "requested_by": "local-production-worker",
                "reason": f"fixture entered {target}",
            },
        )
    exports = Path(run["package_path"]).parent / "qingshan-workspace" / "exports"
    request = postproduction_materialization_fixture(run, exports)

    unsafe = json.loads(json.dumps(request))
    unsafe["shots"][0]["source_relative_path"] = "../production-package.json"
    assert (
        api.post(
            f"/v1/production-runs/{run['id']}/postproduction-materializations",
            json=unsafe,
        ).status_code
        == 422
    )
    missing_layer = json.loads(json.dumps(request))
    missing_layer["audio_layers"] = missing_layer["audio_layers"][:-1]
    assert (
        api.post(
            f"/v1/production-runs/{run['id']}/postproduction-materializations",
            json=missing_layer,
        ).status_code
        == 422
    )

    drifted = json.loads(json.dumps(request))
    drifted["shots"][0]["source_sha256"] = "0" * 64
    mismatch = api.post(
        f"/v1/production-runs/{run['id']}/postproduction-materializations",
        json=drifted,
    )
    assert mismatch.status_code == 409
    assert "source digest changed" in mismatch.text
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "running"
    assert not list((exports / "materialized").glob("*/materialization-result.json"))

    from nalu_runtime import postproduction_materializer

    original_encode = postproduction_materializer._encode_mp4
    encode_count = 0

    def mutate_after_render(*args, **kwargs):
        nonlocal encode_count
        encoded = original_encode(*args, **kwargs)
        encode_count += 1
        if encode_count == 3:
            source = exports / request["shots"][0]["source_relative_path"]
            source.write_bytes(source.read_bytes() + b"changed-after-render")
        return encoded

    with patch.object(postproduction_materializer, "_encode_mp4", side_effect=mutate_after_render):
        changed_during_render = api.post(
            f"/v1/production-runs/{run['id']}/postproduction-materializations",
            json=request,
        )
    assert changed_during_render.status_code == 409
    assert "source digest changed" in changed_during_render.text
    assert api.get(f"/v1/production-runs/{run['id']}").json()["status"] == "running"
    assert not list((exports / "materialized").glob("*/materialization-result.json"))


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
    repository = api.app.state.repository
    with (
        patch.object(
            repository,
            "append_run_event_once",
            side_effect=RuntimeError("simulated exit before release package event commit"),
        ),
        pytest.raises(RuntimeError, match="simulated exit"),
    ):
        api.post(
            f"/v1/production-runs/{run['id']}/release-package",
            json=release_request,
        )
    release_path = Path(run["package_path"]).parent / "release-package.json"
    release_bytes = release_path.read_bytes()
    release_file_sha256 = hashlib.sha256(release_bytes).hexdigest()
    assert not any(
        event.event_type == "release_package_created"
        for event in repository.list_run_events(run["id"])
    )

    external_package = tmp_path / "external-release-package.json"
    external_package.write_bytes(release_bytes)
    release_path.unlink()
    release_path.symlink_to(external_package)
    linked_replay = client(tmp_path).post(
        f"/v1/production-runs/{run['id']}/release-package", json=release_request
    )
    assert linked_replay.status_code == 409
    assert "path is unsafe" in linked_replay.text
    assert not any(
        event.event_type == "release_package_created"
        for event in repository.list_run_events(run["id"])
    )
    release_path.unlink()
    release_path.write_bytes(release_bytes)

    api = client(tmp_path)
    release = api.post(
        f"/v1/production-runs/{run['id']}/release-package", json=release_request
    )
    assert release.status_code == 201
    package = release.json()
    assert release_path.read_bytes() == release_bytes
    assert hashlib.sha256(release_path.read_bytes()).hexdigest() == release_file_sha256
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
    release_events = [
        event
        for event in api.get(f"/v1/production-runs/{run['id']}/events").json()
        if event["event_type"] == "release_package_created"
    ]
    assert len(release_events) == 1
    assert release_events[0]["payload"]["manifest_sha256"] == package["manifest_sha256"]
    assert release_events[0]["payload"]["recovered_after_restart"] is True

    def artifact_sha256(value: dict, digest_field: str) -> str:
        return hashlib.sha256(
            json.dumps(
                {key: item for key, item in value.items() if key != digest_field},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    tampered_package = deepcopy(package)
    tampered_package["project_id"] = "project_from_another_local_record"
    tampered_package["manifest_sha256"] = artifact_sha256(
        tampered_package, "manifest_sha256"
    )
    release_path.write_text(
        json.dumps(tampered_package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cross_project = api.post(
        f"/v1/production-runs/{run['id']}/release-package", json=release_request
    )
    assert cross_project.status_code == 409
    assert "binding mismatch" in cross_project.text
    assert len(
        [
            event
            for event in api.get(f"/v1/production-runs/{run['id']}/events").json()
            if event["event_type"] == "release_package_created"
        ]
    ) == 1
    release_path.write_bytes(release_bytes)

    tampered_package = deepcopy(package)
    tampered_package["artifacts"][0]["sha256"] = "f" * 64
    tampered_package["manifest_sha256"] = artifact_sha256(
        tampered_package, "manifest_sha256"
    )
    release_path.write_text(
        json.dumps(tampered_package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_artifact = api.post(
        f"/v1/production-runs/{run['id']}/release-package", json=release_request
    )
    assert changed_artifact.status_code == 409
    assert "artifact set" in changed_artifact.text
    release_path.write_bytes(release_bytes)

    tampered_package = deepcopy(package)
    tampered_package["media_qa_report_sha256"] = "f" * 64
    tampered_package["manifest_sha256"] = artifact_sha256(
        tampered_package, "manifest_sha256"
    )
    release_path.write_text(
        json.dumps(tampered_package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_qa = api.post(
        f"/v1/production-runs/{run['id']}/release-package", json=release_request
    )
    assert changed_qa.status_code == 409
    assert "QA binding mismatch" in changed_qa.text
    release_path.write_bytes(release_bytes)
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
    repository = api.app.state.repository
    with (
        patch.object(
            repository,
            "append_run_event_once",
            side_effect=RuntimeError("simulated exit before publication dry-run event commit"),
        ),
        pytest.raises(RuntimeError, match="simulated exit"),
    ):
        api.post(
            f"/v1/production-runs/{run['id']}/publication-dry-runs",
            json=dry_run_request,
        )
    dry_run_path = (
        Path(run["package_path"]).parent / "publication-dry-run-youtube.json"
    )
    dry_run_bytes = dry_run_path.read_bytes()
    dry_run_file_sha256 = hashlib.sha256(dry_run_bytes).hexdigest()
    assert not any(
        event.event_type == "publication_dry_run_created"
        for event in repository.list_run_events(run["id"])
    )

    api = client(tmp_path)
    publication = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    )
    assert publication.status_code == 201
    dry_run = publication.json()
    assert dry_run_path.read_bytes() == dry_run_bytes
    assert hashlib.sha256(dry_run_path.read_bytes()).hexdigest() == dry_run_file_sha256
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
    dry_run_events = [
        event
        for event in api.get(f"/v1/production-runs/{run['id']}/events").json()
        if event["event_type"] == "publication_dry_run_created"
    ]
    assert len(dry_run_events) == 1
    assert dry_run_events[0]["payload"]["plan_sha256"] == dry_run["plan_sha256"]
    assert dry_run_events[0]["payload"]["recovered_after_restart"] is True
    tampered_dry_run = deepcopy(dry_run)
    tampered_dry_run["episode_id"] = "episode_from_another_local_record"
    tampered_dry_run["plan_sha256"] = artifact_sha256(
        tampered_dry_run, "plan_sha256"
    )
    dry_run_path.write_text(
        json.dumps(tampered_dry_run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cross_episode = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    )
    assert cross_episode.status_code == 409
    assert "binding mismatch" in cross_episode.text
    assert len(
        [
            event
            for event in api.get(f"/v1/production-runs/{run['id']}/events").json()
            if event["event_type"] == "publication_dry_run_created"
        ]
    ) == 1
    dry_run_path.write_bytes(dry_run_bytes)

    tampered_dry_run = deepcopy(dry_run)
    tampered_dry_run["duplicate_guard_sha256"] = "f" * 64
    tampered_dry_run["plan_sha256"] = artifact_sha256(
        tampered_dry_run, "plan_sha256"
    )
    dry_run_path.write_text(
        json.dumps(tampered_dry_run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_guard = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    )
    assert changed_guard.status_code == 409
    assert "duplicate guard mismatch" in changed_guard.text
    dry_run_path.write_bytes(dry_run_bytes)

    tampered_dry_run = deepcopy(dry_run)
    tampered_dry_run["adapter_version"] = "untrusted-adapter/v999"
    tampered_dry_run["plan_sha256"] = artifact_sha256(
        tampered_dry_run, "plan_sha256"
    )
    dry_run_path.write_text(
        json.dumps(tampered_dry_run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_adapter = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    )
    assert changed_adapter.status_code == 409
    assert "adapter version mismatch" in changed_adapter.text
    dry_run_path.write_bytes(dry_run_bytes)

    tampered_dry_run = deepcopy(dry_run)
    tampered_dry_run["compiled_plan"]["network_operations"] = ["upload"]
    tampered_dry_run["plan_sha256"] = artifact_sha256(
        tampered_dry_run, "plan_sha256"
    )
    dry_run_path.write_text(
        json.dumps(tampered_dry_run, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_plan = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    )
    assert changed_plan.status_code == 409
    assert "compiled plan mismatch" in changed_plan.text
    dry_run_path.write_bytes(dry_run_bytes)
    changed_channel = api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json={**dry_run_request, "channel_reference": "different-channel"},
    )
    assert changed_channel.status_code == 409
    assert "different approval" in changed_channel.text

    season = api.get(f"/v1/projects/{package['project_id']}/seasons").json()[0]
    next_episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={
            "title": "下一集",
            "episode_number": 2,
            "logline": "林叔继续寻找家人。",
        },
    ).json()
    reconciliation_request = {
        "platform": "youtube",
        "remote_publication_id": "yt_verified_001",
        "release_manifest_sha256": package["manifest_sha256"],
        "confirmation_text": "我确认只读核验这次发行",
    }
    disabled = api.post(
        f"/v1/production-runs/{run['id']}/publication-reconciliation",
        headers={"Idempotency-Key": "publication-reconcile-001"},
        json=reconciliation_request,
    )
    assert disabled.status_code == 409
    assert "could not be independently verified" in disabled.text
    assert api.get(f"/v1/episodes/{episode['id']}").json()["status"] == "ready_to_publish"

    verifier = DeterministicPublicationVerifier(package["manifest_sha256"])
    with client(tmp_path, verifier) as verified_api:
        reconciliation_db = tmp_path / "test.sqlite3"
        original_publication_lookup = verifier.lookup_publication

        def block_episode_after_publication_lookup(**request):
            verified_publication = original_publication_lookup(**request)
            with sqlite3.connect(reconciliation_db) as connection:
                connection.execute(
                    "UPDATE episodes SET status = ? WHERE id = ?",
                    ("blocked", episode["id"]),
                )
            return verified_publication

        with patch.object(
            verifier,
            "lookup_publication",
            side_effect=block_episode_after_publication_lookup,
        ):
            stale_publication_authority = verified_api.post(
                f"/v1/production-runs/{run['id']}/publication-reconciliation",
                headers={"Idempotency-Key": "publication-reconcile-stale-authority"},
                json=reconciliation_request,
            )
        assert stale_publication_authority.status_code == 409
        assert "authority changed" in stale_publication_authority.text
        with sqlite3.connect(reconciliation_db) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM publication_reconciliations"
            ).fetchone()[0] == 0
            connection.execute(
                "UPDATE episodes SET status = ? WHERE id = ?",
                ("ready_to_publish", episode["id"]),
            )
        assert not any(
            event["event_type"] == "publication_reconciled"
            for event in verified_api.get(
                f"/v1/episodes/{episode['id']}/events"
            ).json()
        )
        verifier.publication_calls = 0

        reconciled = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-reconciliation",
            headers={"Idempotency-Key": "publication-reconcile-001"},
            json=reconciliation_request,
        )
        assert reconciled.status_code == 201
        publication_record = reconciled.json()
        assert publication_record["remote_state"] == "published"
        assert publication_record["read_only_verification_performed"] is True
        assert publication_record["publication_performed"] is False
        assert publication_record["replacement_performed"] is False
        assert publication_record["external_write_performed"] is False
        assert verified_api.get(f"/v1/episodes/{episode['id']}").json()["status"] == "published"
        replay_reconciliation = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-reconciliation",
            headers={"Idempotency-Key": "publication-reconcile-001"},
            json=reconciliation_request,
        )
        assert replay_reconciliation.json() == publication_record
        assert verifier.publication_calls == 1
        replacement = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-reconciliation",
            headers={"Idempotency-Key": "publication-reconcile-002"},
            json={**reconciliation_request, "remote_publication_id": "yt_replacement"},
        )
        assert replacement.status_code == 409
        assert "different immutable identity" in replacement.text

        original_record_body = {
            key: value
            for key, value in publication_record.items()
            if key != "record_sha256"
        }

        def rewrite_reconciliation_record(record_body: dict) -> None:
            record_json = json.dumps(record_body, ensure_ascii=False, sort_keys=True)
            record_sha256 = hashlib.sha256(record_json.encode()).hexdigest()
            with sqlite3.connect(reconciliation_db) as connection:
                connection.execute(
                    """UPDATE publication_reconciliations
                       SET record_json = ?, record_sha256 = ?
                       WHERE run_id = ? AND platform = ?""",
                    (record_json, record_sha256, run["id"], "youtube"),
                )

        cross_project_record = deepcopy(original_record_body)
        cross_project_record["project_id"] = "project_from_another_reconciliation"
        rewrite_reconciliation_record(cross_project_record)
        cross_project_reconciliation = verified_api.get(
            f"/v1/production-runs/{run['id']}/publication-reconciliation/youtube"
        )
        assert cross_project_reconciliation.status_code == 409
        assert "entity binding mismatch" in cross_project_reconciliation.text
        rewrite_reconciliation_record(original_record_body)

        changed_guardian_record = deepcopy(original_record_body)
        changed_guardian_record["guardian_approval"] = True
        rewrite_reconciliation_record(changed_guardian_record)
        changed_guardian_reconciliation = verified_api.get(
            f"/v1/production-runs/{run['id']}/publication-reconciliation/youtube"
        )
        assert changed_guardian_reconciliation.status_code == 409
        assert "request digest mismatch" in changed_guardian_reconciliation.text
        rewrite_reconciliation_record(original_record_body)

        with sqlite3.connect(reconciliation_db) as connection:
            connection.execute(
                """UPDATE publication_reconciliations
                   SET remote_publication_id = ?
                   WHERE run_id = ? AND platform = ?""",
                ("yt_row_relinked", run["id"], "youtube"),
            )
        relinked_remote_identity = verified_api.get(
            f"/v1/production-runs/{run['id']}/publication-reconciliation/youtube"
        )
        assert relinked_remote_identity.status_code == 409
        assert "entity binding mismatch" in relinked_remote_identity.text
        with sqlite3.connect(reconciliation_db) as connection:
            connection.execute(
                """UPDATE publication_reconciliations
                   SET remote_publication_id = ?
                   WHERE run_id = ? AND platform = ?""",
                (publication_record["remote_publication_id"], run["id"], "youtube"),
            )

        relinked_release_record = deepcopy(original_record_body)
        relinked_release_record["release_manifest_sha256"] = "f" * 64
        rewrite_reconciliation_record(relinked_release_record)
        relinked_release = verified_api.get(
            f"/v1/production-runs/{run['id']}/publication-reconciliation/youtube"
        )
        assert relinked_release.status_code == 409
        assert "request digest mismatch" in relinked_release.text
        blocked_learning = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-metrics",
            headers={"Idempotency-Key": "publication-metrics-tampered"},
            json={
                "publication_record_sha256": hashlib.sha256(
                    json.dumps(
                        relinked_release_record,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode()
                ).hexdigest(),
                "window_start": "2026-09-01T00:00:00+00:00",
                "window_end": "2026-09-08T00:00:00+00:00",
                "confirmation_text": "我确认只读同步这次发行指标",
            },
        )
        assert blocked_learning.status_code == 409
        assert verifier.metrics_calls == 0
        rewrite_reconciliation_record(original_record_body)

        metrics_request = {
            "publication_record_sha256": publication_record["record_sha256"],
            "window_start": "2026-09-01T00:00:00+00:00",
            "window_end": "2026-09-08T00:00:00+00:00",
            "confirmation_text": "我确认只读同步这次发行指标",
        }
        learning_repository = verified_api.app.state.repository
        original_strategy_content = learning_repository._director_strategy_content

        def lock_strategy_target_after_preflight(verified_metrics):
            with sqlite3.connect(reconciliation_db) as connection:
                connection.execute(
                    "UPDATE episodes SET status = ? WHERE id = ?",
                    ("preproduction", next_episode["id"]),
                )
            return original_strategy_content(verified_metrics)

        with patch.object(
            learning_repository,
            "_director_strategy_content",
            side_effect=lock_strategy_target_after_preflight,
        ):
            stale_target_learning = verified_api.post(
                f"/v1/production-runs/{run['id']}/publication-metrics",
                headers={"Idempotency-Key": "publication-metrics-stale-target"},
                json=metrics_request,
            )
        assert stale_target_learning.status_code == 409
        assert "strategy authority changed" in stale_target_learning.text
        with sqlite3.connect(reconciliation_db) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM publication_metric_snapshots"
            ).fetchone()[0] == 0
            assert connection.execute(
                "SELECT COUNT(*) FROM director_strategy_revisions"
            ).fetchone()[0] == 0
            connection.execute(
                "UPDATE episodes SET status = ? WHERE id = ?",
                ("planned", next_episode["id"]),
            )
        verifier.metrics_calls = 0

        learned = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-metrics",
            headers={"Idempotency-Key": "publication-metrics-001"},
            json=metrics_request,
        )
        assert learned.status_code == 201
        result = learned.json()
        assert result["metrics"]["completion_rate"] == 0.52
        assert result["metrics"]["read_only_sync_performed"] is True
        assert result["metrics"]["publication_performed"] is False
        assert result["metrics"]["production_performed"] is False
        assert result["strategy"]["target_episode_id"] == next_episode["id"]
        assert result["strategy"]["revision"] == 1
        assert result["strategy"]["requires_script_revision_and_approval"] is True
        assert result["strategy"]["production_started"] is False
        assert any("前 15 秒" in item for item in result["strategy"]["directives"])
        assert (
            verified_api.get(
                f"/v1/publication-metrics/{result['metrics']['id']}"
            ).json()
            == result["metrics"]
        )
        assert verified_api.get(
            f"/v1/projects/{package['project_id']}/director-strategies"
        ).json() == [result["strategy"]]

        original_metrics_body = {
            key: value
            for key, value in result["metrics"].items()
            if key != "snapshot_sha256"
        }
        original_strategy_body = {
            key: value
            for key, value in result["strategy"].items()
            if key != "strategy_sha256"
        }

        def rewrite_metrics_snapshot(snapshot_body: dict) -> None:
            snapshot_json = json.dumps(snapshot_body, ensure_ascii=False, sort_keys=True)
            snapshot_sha256 = hashlib.sha256(snapshot_json.encode()).hexdigest()
            with sqlite3.connect(reconciliation_db) as connection:
                connection.execute(
                    """UPDATE publication_metric_snapshots
                       SET snapshot_json = ?, snapshot_sha256 = ? WHERE id = ?""",
                    (snapshot_json, snapshot_sha256, result["metrics"]["id"]),
                )

        def rewrite_director_strategy(strategy_body: dict) -> None:
            strategy_json = json.dumps(strategy_body, ensure_ascii=False, sort_keys=True)
            strategy_sha256 = hashlib.sha256(strategy_json.encode()).hexdigest()
            with sqlite3.connect(reconciliation_db) as connection:
                connection.execute(
                    """UPDATE director_strategy_revisions
                       SET strategy_json = ?, strategy_sha256 = ? WHERE id = ?""",
                    (strategy_json, strategy_sha256, result["strategy"]["id"]),
                )

        cross_project_metrics = deepcopy(original_metrics_body)
        cross_project_metrics["project_id"] = "project_from_another_metrics_snapshot"
        rewrite_metrics_snapshot(cross_project_metrics)
        rejected_metrics_entity = verified_api.get(
            f"/v1/publication-metrics/{result['metrics']['id']}"
        )
        assert rejected_metrics_entity.status_code == 409
        assert "entity binding mismatch" in rejected_metrics_entity.text
        rewrite_metrics_snapshot(original_metrics_body)

        changed_metrics_request = deepcopy(original_metrics_body)
        changed_metrics_request["request_sha256"] = "f" * 64
        rewrite_metrics_snapshot(changed_metrics_request)
        with sqlite3.connect(reconciliation_db) as connection:
            connection.execute(
                "UPDATE publication_metric_snapshots SET request_sha256 = ? WHERE id = ?",
                ("f" * 64, result["metrics"]["id"]),
            )
        rejected_metrics_request = verified_api.get(
            f"/v1/publication-metrics/{result['metrics']['id']}"
        )
        assert rejected_metrics_request.status_code == 409
        assert "request digest mismatch" in rejected_metrics_request.text
        rewrite_metrics_snapshot(original_metrics_body)
        with sqlite3.connect(reconciliation_db) as connection:
            connection.execute(
                "UPDATE publication_metric_snapshots SET request_sha256 = ? WHERE id = ?",
                (original_metrics_body["request_sha256"], result["metrics"]["id"]),
            )

        relinked_publication_metrics = deepcopy(original_metrics_body)
        relinked_publication_metrics["publication_record_sha256"] = "f" * 64
        rewrite_metrics_snapshot(relinked_publication_metrics)
        rejected_metrics_publication = verified_api.get(
            f"/v1/publication-metrics/{result['metrics']['id']}"
        )
        assert rejected_metrics_publication.status_code == 409
        assert "publication binding mismatch" in rejected_metrics_publication.text
        rewrite_metrics_snapshot(original_metrics_body)

        relinked_strategy_target = deepcopy(original_strategy_body)
        relinked_strategy_target["target_episode_id"] = episode["id"]
        rewrite_director_strategy(relinked_strategy_target)
        rejected_strategy_target = verified_api.get(
            f"/v1/projects/{package['project_id']}/director-strategies"
        )
        assert rejected_strategy_target.status_code == 409
        assert "entity binding mismatch" in rejected_strategy_target.text
        rewrite_director_strategy(original_strategy_body)

        relinked_strategy_metrics = deepcopy(original_strategy_body)
        relinked_strategy_metrics["source_metrics_sha256"] = "f" * 64
        rewrite_director_strategy(relinked_strategy_metrics)
        rejected_strategy_metrics = verified_api.get(
            f"/v1/projects/{package['project_id']}/director-strategies"
        )
        assert rejected_strategy_metrics.status_code == 409
        assert "metrics binding mismatch" in rejected_strategy_metrics.text
        rewrite_director_strategy(original_strategy_body)

        strategy_content_mutations = (
            ("observations", ["被篡改但重新计算摘要的观察。"]),
            ("directives", ["绕过已确认剧本直接改变下一集。"]),
            ("immutable_constraints", ["允许自动生产和发行。"]),
        )
        for field, changed_value in strategy_content_mutations:
            changed_strategy_content = deepcopy(original_strategy_body)
            changed_strategy_content[field] = changed_value
            rewrite_director_strategy(changed_strategy_content)
            rejected_strategy_content = verified_api.get(
                f"/v1/projects/{package['project_id']}/director-strategies"
            )
            assert rejected_strategy_content.status_code == 409
            assert "content mismatch" in rejected_strategy_content.text
        rewrite_director_strategy(original_strategy_body)

        replay_metrics = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-metrics",
            headers={"Idempotency-Key": "publication-metrics-001"},
            json=metrics_request,
        )
        assert replay_metrics.json() == result
        assert verifier.metrics_calls == 1
        missing_offset = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-metrics",
            headers={"Idempotency-Key": "publication-metrics-002"},
            json={
                **metrics_request,
                "window_start": "2026-09-09T00:00:00",
                "window_end": "2026-09-10T00:00:00",
            },
        )
        assert missing_offset.status_code == 409
        assert "must include a UTC offset" in missing_offset.text
        assert verifier.metrics_calls == 1
        reused_key = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-metrics",
            headers={"Idempotency-Key": "publication-metrics-001"},
            json={
                **metrics_request,
                "window_end": "2026-09-09T00:00:00+00:00",
            },
        )
        assert reused_key.status_code == 409
        assert "idempotency key was already used differently" in reused_key.text
        assert verifier.metrics_calls == 1
        wrong_metrics = verified_api.post(
            f"/v1/production-runs/{run['id']}/publication-metrics",
            headers={"Idempotency-Key": "publication-metrics-002"},
            json={**metrics_request, "publication_record_sha256": "f" * 64},
        )
        assert wrong_metrics.status_code == 409

        backup = verified_api.get(
            f"/v1/projects/{package['project_id']}/export"
        ).json()
        assert backup["schema_version"] == "nalu.project-export/v22"
        assert [row["id"] for row in backup["payload"]["production_runs"]] == [
            run["id"]
        ]
        assert len(backup["payload"]["publication_reconciliations"]) == 1
        assert len(backup["payload"]["publication_metric_snapshots"]) == 1
        assert len(backup["payload"]["director_strategy_revisions"]) == 1
        with client(tmp_path / "publication-learning-restored") as restored_api:
            restored = restored_api.post("/v1/project-imports", json=backup)
            assert restored.status_code == 201
            assert restored_api.get(
                f"/v1/production-runs/{run['id']}/publication-reconciliation/youtube"
            ).json() == publication_record
            restored_learning = restored_api.post(
                f"/v1/production-runs/{run['id']}/publication-metrics",
                headers={"Idempotency-Key": "restored-publication-metrics"},
                json=metrics_request,
            )
            assert restored_learning.status_code == 409
            assert "outside the managed data root" in restored_learning.text
            assert restored_api.get(
                f"/v1/publication-metrics/{result['metrics']['id']}"
            ).json() == result["metrics"]
            assert restored_api.get(
                f"/v1/projects/{package['project_id']}/director-strategies"
            ).json() == [result["strategy"]]
            restored_run = restored_api.get(
                f"/v1/production-runs/{run['id']}"
            ).json()
            assert "restored-publication-sources" in restored_run["package_path"]
            assert restored_run["package_path"] != run["package_path"]

        legacy_v19 = deepcopy(backup)
        legacy_v19["schema_version"] = "nalu.project-export/v19"
        legacy_v19["payload"].pop("script_writer_receipt_reconciliations")
        legacy_v19["payload"].pop("script_writer_provider_reconciliations")
        for table in (
            "production_runs",
            "publication_reconciliations",
            "publication_metric_snapshots",
            "director_strategy_revisions",
        ):
            legacy_v19["payload"].pop(table)
        legacy_v19["payload_sha256"] = hashlib.sha256(
            json.dumps(
                legacy_v19["payload"], ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
        with client(tmp_path / "publication-learning-v19") as legacy_api:
            assert legacy_api.post(
                "/v1/project-imports", json=legacy_v19
            ).status_code == 201
            assert legacy_api.get(
                f"/v1/projects/{package['project_id']}/director-strategies"
            ).json() == []

        tampered_backup = deepcopy(backup)
        snapshot_body = json.loads(
            tampered_backup["payload"]["publication_metric_snapshots"][0][
                "snapshot_json"
            ]
        )
        snapshot_body["project_id"] = "project_from_another_backup"
        tampered_backup["payload"]["publication_metric_snapshots"][0][
            "snapshot_json"
        ] = json.dumps(snapshot_body, ensure_ascii=False, sort_keys=True)
        tampered_backup["payload"]["publication_metric_snapshots"][0][
            "snapshot_sha256"
        ] = hashlib.sha256(
            tampered_backup["payload"]["publication_metric_snapshots"][0][
                "snapshot_json"
            ].encode()
        ).hexdigest()
        tampered_backup["payload_sha256"] = hashlib.sha256(
            json.dumps(
                tampered_backup["payload"], ensure_ascii=False, sort_keys=True
            ).encode()
        ).hexdigest()
        with client(tmp_path / "publication-learning-tampered") as tampered_api:
            rejected = tampered_api.post("/v1/project-imports", json=tampered_backup)
            assert rejected.status_code == 409
            assert "tampered publication metrics" in rejected.text

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

    bilibili_reconciliation = {
        "platform": "bilibili",
        "remote_publication_id": "bili_verified_001",
        "release_manifest_sha256": package["manifest_sha256"],
        "confirmation_text": "我确认只读核验这次发行",
    }
    with client(tmp_path, verifier) as child_api:
        blocked_child_reconciliation = child_api.post(
            f"/v1/production-runs/{run['id']}/publication-reconciliation",
            headers={"Idempotency-Key": "bilibili-reconcile-001"},
            json=bilibili_reconciliation,
        )
        assert blocked_child_reconciliation.status_code == 409
        assert "guardian approval" in blocked_child_reconciliation.text
    mismatched_verifier = DeterministicPublicationVerifier("0" * 64)
    with client(tmp_path, mismatched_verifier) as mismatch_api:
        mismatched_identity = mismatch_api.post(
            f"/v1/production-runs/{run['id']}/publication-reconciliation",
            headers={"Idempotency-Key": "bilibili-reconcile-001"},
            json={**bilibili_reconciliation, "guardian_approval": True},
        )
        assert mismatched_identity.status_code == 409
        assert "does not match the local package" in mismatched_identity.text
    with client(tmp_path, verifier) as child_api:
        reconciled_child_publication = child_api.post(
            f"/v1/production-runs/{run['id']}/publication-reconciliation",
            headers={"Idempotency-Key": "bilibili-reconcile-001"},
            json={**bilibili_reconciliation, "guardian_approval": True},
        )
        assert reconciled_child_publication.status_code == 201
        assert reconciled_child_publication.json()["platform"] == "bilibili"

    with client(tmp_path) as restarted_api:
        assert restarted_api.get(
            f"/v1/production-runs/{run['id']}/publication-reconciliation/youtube"
        ).json() == publication_record
        assert restarted_api.get(
            f"/v1/publication-metrics/{result['metrics']['id']}"
        ).json() == result["metrics"]
        assert restarted_api.get(
            f"/v1/projects/{package['project_id']}/director-strategies"
        ).json() == [result["strategy"]]
        assert restarted_api.get("/health").json()["schema_version"] == "26"

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
