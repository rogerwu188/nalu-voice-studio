import hashlib
import json
import struct
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import RunStatus


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


def seal_payload(*, include_qa: bool = False) -> dict:
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

    intact = api.get(
        f"/v1/production-runs/{run['id']}/rendered-output-integrity"
    ).json()
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
    damaged = api.get(
        f"/v1/production-runs/{run['id']}/rendered-output-integrity"
    ).json()
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
    master_bytes = b"original-resolution-completed-master"
    master_sha = hashlib.sha256(master_bytes).hexdigest()
    (exports / "E01_MASTER.mp4").write_bytes(master_bytes)
    (exports / "E01_zh-CN.vtt").write_text("WEBVTT\n", encoding="utf-8")
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
        json=seal_payload(include_qa=True),
    ).json()
    completion_payload = {
        "output_seal_sha256": seal["manifest_sha256"],
        "completed_by": "local-user",
        "spoken_confirmation": "我确认这份成片和人工质量检查记录",
    }
    repository = api.app.state.repository
    with patch.object(
        repository,
        "_record_episode_transition",
        side_effect=RuntimeError("simulated crash before SQLite commit"),
    ), pytest.raises(RuntimeError, match="simulated crash"):
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
    integrity = api.get(
        f"/v1/production-runs/{run['id']}/rendered-output-integrity"
    ).json()
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
    plan = api.get(
        f"/v1/production-runs/{run['id']}/postproduction-repair-plan"
    ).json()
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
    plan = api.get(
        f"/v1/production-runs/{run['id']}/postproduction-repair-plan"
    ).json()
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
    rejected_plan = api.get(
        f"/v1/production-runs/{run['id']}/postproduction-repair-plan"
    )
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
    api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    passed = api.post(
        f"/v1/production-runs/{run['id']}/media-structure-qa"
    ).json()
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
    failed_exports = (
        Path(failed_run["package_path"]).parent / "qingshan-workspace" / "exports"
    )
    (failed_exports / "E01_MASTER.mp4").write_bytes(
        minimal_mp4(include_media_data=False)
    )
    (failed_exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:03.000\n超出成片\n",
        encoding="utf-8",
    )
    api.post(
        f"/v1/production-runs/{failed_run['id']}/rendered-output-seal",
        json=seal_payload(),
    )
    failed = api.post(
        f"/v1/production-runs/{failed_run['id']}/media-structure-qa"
    ).json()
    assert failed["status"] == "FAIL"
    assert "mp4:MP4_MDAT_MISSING" in failed["failures"]
    assert "captions:WEBVTT_CUE_EXCEEDS_MASTER_DURATION" in failed["failures"]
    repair = api.get(
        f"/v1/production-runs/{failed_run['id']}/postproduction-repair-plan"
    ).json()
    assert [task["code"] for task in repair["repair_tasks"]] == [
        "caption_timeline",
        "mp4_structure",
    ]


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
    master = minimal_mp4(duration_milliseconds=2000)
    master_sha = hashlib.sha256(master).hexdigest()
    (exports / "E01_MASTER.mp4").write_bytes(master)
    (exports / "E01_zh-CN.vtt").write_text(
        "WEBVTT\n\n00:00.000 --> 00:01.900\n回家\n",
        encoding="utf-8",
    )
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
    payload = seal_payload(include_qa=True)
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
    media_qa = api.post(
        f"/v1/production-runs/{run['id']}/media-structure-qa"
    ).json()
    assert media_qa["status"] == "PASS"
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
    assert api.get(
        f"/v1/production-runs/{run['id']}/publication-dry-runs/youtube"
    ).json() == dry_run
    assert api.post(
        f"/v1/production-runs/{run['id']}/publication-dry-runs",
        json=dry_run_request,
    ).json() == dry_run
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
    damaged_dry_run = api.get(
        f"/v1/production-runs/{run['id']}/publication-dry-runs/youtube"
    )
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
    assert api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal", json=traversal
    ).status_code == 422

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
    assert api.post(
        f"/v1/production-runs/{run['id']}/rendered-output-seal", json=no_master
    ).status_code == 422
