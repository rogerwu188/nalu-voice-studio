import hashlib
import io
import json
import sqlite3
import stat
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path / "test.sqlite3", tmp_path / "data")
    return TestClient(app)


def create_approved_episode(api: TestClient) -> tuple[dict, dict, dict]:
    project = api.post(
        "/v1/projects",
        json={
            "title": "我的一生",
            "audience_mode": "older_adult",
            "planned_episode_count": 10,
            "project_bible": {"theme": "family and memory"},
        },
    ).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1, "planned_episode_count": 10},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "离开故乡", "episode_number": 1, "target_seconds": 120},
    ).json()
    script = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={
            "content": "第一集定稿剧本",
            "summary_for_voice_review": "这一集讲述主人公第一次离开故乡。",
        },
    ).json()
    response = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认这个剧本"},
    )
    assert response.status_code == 200
    return project, season, episode


def test_project_season_episode_hierarchy(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, season, episode = create_approved_episode(api)

    assert api.get("/v1/projects").json()[0]["id"] == project["id"]
    assert api.get(f"/v1/projects/{project['id']}/seasons").json()[0]["id"] == season["id"]
    stored = api.get(f"/v1/episodes/{episode['id']}").json()
    assert stored["status"] == "script_approved"
    assert stored["approved_script_revision"] == 1

    approvals = api.get(f"/v1/episodes/{episode['id']}/script-approvals").json()
    assert len(approvals) == 1
    assert approvals[0]["approved_by"] == "user"
    assert approvals[0]["spoken_confirmation"] == "我确认这个剧本"


def test_creative_format_routes_projects_without_faking_an_adapter(tmp_path: Path) -> None:
    api = client(tmp_path)
    animation = api.post(
        "/v1/projects",
        json={
            "title": "小海豚历险记",
            "creative_format": "animation_series",
            "production_pipeline": "qingshan-short-drama",
        },
    )
    assert animation.status_code == 201
    assert animation.json()["creative_format"] == "animation_series"

    commercial = api.post(
        "/v1/projects",
        json={
            "title": "护肤品广告",
            "creative_format": "commercial_campaign",
            "production_pipeline": "unassigned",
        },
    )
    assert commercial.status_code == 201
    assert commercial.json()["production_pipeline"] == "unassigned"
    commercial_id = commercial.json()["id"]
    season = api.post(
        f"/v1/projects/{commercial_id}/seasons",
        json={"title": "广告活动", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "30秒主片", "episode_number": 1},
    ).json()
    script = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={"content": "广告脚本", "summary_for_voice_review": "主片摘要"},
    ).json()
    assert (
        api.post(
            f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
            json={"approved_by": "user"},
        ).status_code
        == 200
    )
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "no-adapter"},
    )
    assert blocked.status_code == 409
    assert "no approved production adapter" in blocked.text


def test_documentary_readiness_requires_confirmed_citable_sources(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={
            "title": "父亲的远行",
            "creative_format": "documentary_series",
            "production_pipeline": "unassigned",
            "project_bible": {"documentary_mode": "archival_with_reenactment"},
        },
    ).json()
    empty = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert empty["can_plan_chapters"] is False
    assert empty["can_enter_production"] is False
    assert empty["generated_reenactment_label_required"] is True

    asset = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "station-1982.jpg",
            "kind": "source_document",
            "name": "1982 年火车站老照片",
        },
        content=b"local archive bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    unlinked = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert unlinked["evidence"][0]["confirmation_status"] == "unlinked"
    assert unlinked["draft_or_unlinked_source_count"] == 1

    card = api.post(
        f"/v1/projects/{project['id']}/memory-cards",
        json={
            "asset_id": asset["id"],
            "title": "第一次离开家乡",
            "description": "父亲在火车站准备南下工作。",
            "approximate_date": "1982 年秋天",
            "place": "杭州火车站",
            "story_relevance": "作为第一章的真实开场。",
            "allowed_use": "story_development",
        },
    ).json()
    draft = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert draft["evidence"][0]["confirmation_status"] == "draft"
    assert draft["can_plan_chapters"] is False

    confirmed = api.post(
        f"/v1/memory-cards/{card['id']}/confirm",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 1,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这份资料可以归档并用于故事规划",
        },
    )
    assert confirmed.status_code == 200
    ready = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert ready["confirmed_narrative_source_count"] == 1
    assert ready["evidence"][0]["narrative_authority"] is True
    assert ready["can_plan_chapters"] is True
    assert ready["can_enter_production"] is False
    assert any("adapter" in blocker for blocker in ready["blockers"])

    portrait = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "father.jpg",
            "kind": "character_image",
            "name": "父亲照片",
            "subject_name": "父亲",
            "consent_granted": True,
            "consent_granted_by": "本人",
            "consent_statement": "同意用于本纪录片项目",
        },
        content=b"portrait bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    portrait_card = api.post(
        f"/v1/projects/{project['id']}/memory-cards",
        json={
            "asset_id": portrait["id"],
            "title": "父亲青年照",
            "allowed_use": "visual_generation",
        },
    ).json()
    assert api.post(
        f"/v1/memory-cards/{portrait_card['id']}/confirm",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 1,
            "review_channel": "voice",
            "spoken_confirmation": "我确认这张记忆卡并归档",
        },
    ).status_code == 200
    before_revocation = api.get(
        f"/v1/projects/{project['id']}/documentary-readiness"
    ).json()
    portrait_evidence = next(
        item for item in before_revocation["evidence"]
        if item["asset_id"] == portrait["id"]
    )
    assert portrait_evidence["visual_generation_authorized"] is True
    assert api.post(
        f"/v1/assets/{portrait['id']}/consent-revocations",
        json={"requested_by": "本人", "reason": "不再允许生成画面"},
    ).status_code == 201
    after_revocation = api.get(
        f"/v1/projects/{project['id']}/documentary-readiness"
    ).json()
    portrait_evidence = next(
        item for item in after_revocation["evidence"]
        if item["asset_id"] == portrait["id"]
    )
    assert portrait_evidence["visual_generation_authorized"] is False

    drama = api.post("/v1/projects", json={"title": "剧情短剧"}).json()
    wrong_format = api.get(f"/v1/projects/{drama['id']}/documentary-readiness")
    assert wrong_format.status_code == 409


def test_feedback_is_local_redacted_and_child_sharing_fails_closed(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={"title": "儿童动画", "audience_mode": "child"},
    ).json()
    local = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "usability",
            "message": "按钮看不清，我的邮箱是 child@example.com，密钥 sk-secret123456789",
            "source": "voice",
        },
    )
    assert local.status_code == 201
    assert local.json()["status"] == "local_only"
    assert local.json()["redaction_applied"] is True
    assert "child@example.com" not in local.json()["message"]
    assert "sk-secret" not in local.json()["message"]

    blocked = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "feature_request",
            "message": "我希望字再大一点",
            "share_authorized": True,
        },
    )
    assert blocked.status_code == 409
    shared = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "feature_request",
            "message": "我希望字再大一点",
            "share_authorized": True,
            "guardian_approval": True,
        },
    )
    assert shared.status_code == 201
    assert shared.json()["status"] == "ready_for_review"
    listed = api.get("/v1/feedback", params={"project_id": project["id"]}).json()
    assert [item["id"] for item in listed] == [local.json()["id"], shared.json()["id"]]

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert len(backup["payload"]["feedback_items"]) == 2
    deleted = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}",
        json={
            "confirmation_title": "儿童动画",
            "requested_by": "local-user",
            "delete_production_snapshots": False,
        },
    )
    assert deleted.status_code == 200
    assert api.get("/v1/feedback").json() == []


def test_memory_card_requires_explicit_confirmation_and_keeps_evidence(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={"title": "家庭记忆", "audience_mode": "older_adult"},
    ).json()
    asset = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "notebook.jpg",
            "kind": "source_document",
            "name": "手写回忆第一页",
        },
        content=b"image bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    created = api.post(
        f"/v1/projects/{project['id']}/memory-cards",
        json={
            "asset_id": asset["id"],
            "title": "在杭州的全家福",
            "description": "我和妻子带着女儿第一次去杭州。",
            "ocr_text": "一九八零年春天",
            "spoken_context": "照片里左边是我的妻子，前面是女儿。",
            "approximate_date": "1980年春天",
            "place": "杭州西湖",
            "people": [
                {"name": "妻子", "relationship": "配偶"},
                {"name": "女儿", "relationship": "女儿"},
            ],
            "story_relevance": "可以作为第二集家庭旅行的素材。",
            "allowed_use": "story_development",
        },
    )
    assert created.status_code == 201
    assert created.json()["confirmation_status"] == "draft"
    assert created.json()["asset_id"] == asset["id"]
    assert (
        api.get(
            f"/v1/projects/{project['id']}/memory-cards",
            params={"confirmed_only": True},
        ).json()
        == []
    )

    corrected = api.patch(
        f"/v1/memory-cards/{created.json()['id']}",
        json={
            "place": "杭州灵隐寺",
            "source_channel": "voice",
            "change_summary": "用户说地点不是西湖，是灵隐寺",
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["current_revision"] == 2
    assert corrected.json()["confirmation_status"] == "draft"
    revisions = api.get(f"/v1/memory-cards/{created.json()['id']}/revisions").json()
    assert [revision["revision"] for revision in revisions] == [1, 2]
    assert revisions[1]["source_channel"] == "voice"
    assert revisions[1]["content"]["place"] == "杭州灵隐寺"

    confirmed = api.post(
        f"/v1/memory-cards/{created.json()['id']}/confirm",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 2,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这张记忆卡并归档",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmation_status"] == "confirmed"
    authoritative = api.get(
        f"/v1/projects/{project['id']}/memory-cards",
        params={"confirmed_only": True},
    ).json()
    assert authoritative[0]["place"] == "杭州灵隐寺"
    assert authoritative[0]["people"][0]["relationship"] == "配偶"
    confirmations = api.get(f"/v1/memory-cards/{created.json()['id']}/confirmations").json()
    assert confirmations[0]["reviewed_revision"] == 2
    assert confirmations[0]["spoken_confirmation"] == "我确认这张记忆卡并归档"

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v8"
    assert backup["payload"]["memory_cards"][0]["asset_id"] == asset["id"]

    other = api.post("/v1/projects", json={"title": "另一个项目"}).json()
    cross_project = api.post(
        f"/v1/projects/{other['id']}/memory-cards",
        json={"asset_id": asset["id"], "title": "错误关联"},
    )
    assert cross_project.status_code == 409


def test_archive_audio_and_video_import_as_reference_without_generation_consent(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects", json={"title": "家庭档案", "audience_mode": "older_adult"}
    ).json()
    for kind, filename, content_type in (
        ("archive_audio", "口述回忆.m4a", "audio/mp4"),
        ("archive_video", "家庭录像.mov", "video/quicktime"),
    ):
        imported = api.post(
            f"/v1/projects/{project['id']}/asset-imports",
            params={"filename": filename, "kind": kind, "name": filename},
            content=b"local family archive",
            headers={"Content-Type": content_type},
        )
        assert imported.status_code == 201
        assert imported.json()["consent_granted"] is False

        card = api.post(
            f"/v1/projects/{project['id']}/memory-cards",
            json={
                "asset_id": imported.json()["id"],
                "title": filename,
                "allowed_use": "reference_only",
            },
        )
        assert card.status_code == 201
        assert card.json()["confirmation_status"] == "draft"


def test_script_history_stale_approval_and_revocation(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "剧本版本"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "第一集", "episode_number": 1},
    ).json()
    first = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={"content": "第一版", "summary_for_voice_review": "第一版摘要"},
    ).json()
    second = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={"content": "第二版", "summary_for_voice_review": "第二版摘要"},
    ).json()
    history = api.get(f"/v1/episodes/{episode['id']}/scripts").json()
    assert [script["revision"] for script in history] == [1, 2]
    assert history[0]["content"] == "第一版"

    stale = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{first['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "误选旧版"},
    )
    assert stale.status_code == 409
    approved = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{second['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认第二版"},
    )
    assert approved.status_code == 200

    revoked = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{second['revision']}/revoke",
        json={"requested_by": "user", "reason": "发现人物年龄有误"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["approved_at"] is None
    stored = api.get(f"/v1/episodes/{episode['id']}").json()
    assert stored["status"] == "script_review"
    assert stored["approved_script_revision"] is None
    records = api.get(f"/v1/episodes/{episode['id']}/script-approvals").json()
    assert [record["action_type"] for record in records] == [
        "script_approved",
        "script_revoked",
    ]
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "revoked-script"},
    )
    assert blocked.status_code == 409


def test_atomic_multi_episode_project_plan(tmp_path: Path) -> None:
    api = client(tmp_path)
    response = api.post(
        "/v1/project-plans",
        json={
            "project": {
                "title": "十集自传",
                "audience_mode": "older_adult",
                "planned_episode_count": 10,
            },
            "season_title": "人生第一季",
        },
    )
    assert response.status_code == 201
    plan = response.json()
    assert plan["season"]["project_id"] == plan["project"]["id"]
    assert [row["episode_number"] for row in plan["episodes"]] == list(range(1, 11))

    rejected = api.post(
        "/v1/project-plans",
        json={
            "project": {"title": "不完整计划", "planned_episode_count": 3},
            "episode_titles": ["只有一集"],
        },
    )
    assert rejected.status_code == 409
    projects = api.get("/v1/projects").json()
    assert [project["title"] for project in projects] == ["十集自传"]


def test_draft_project_is_finalized_in_place_with_existing_assets(tmp_path: Path) -> None:
    api = client(tmp_path)
    draft = api.post(
        "/v1/projects",
        json={"title": "未命名故事", "description": "语音采访进行中"},
    ).json()
    imported = api.post(
        f"/v1/projects/{draft['id']}/asset-imports",
        params={
            "filename": "memory.jpg",
            "kind": "scene_reference",
            "name": "老照片",
        },
        content=b"memory",
        headers={"Content-Type": "image/jpeg"},
    )
    assert imported.status_code == 201

    finalized = api.post(
        "/v1/project-plans",
        json={
            "project_id": draft["id"],
            "project": {
                "title": "外婆的夏天",
                "description": "外婆讲年轻时的故事",
                "audience_mode": "older_adult",
                "planned_episode_count": 3,
            },
        },
    )
    assert finalized.status_code == 201
    assert finalized.json()["project"]["id"] == draft["id"]
    assert finalized.json()["project"]["title"] == "外婆的夏天"
    assert len(finalized.json()["episodes"]) == 3
    assets = api.get(f"/v1/projects/{draft['id']}/assets").json()
    assert [asset["name"] for asset in assets] == ["老照片"]

    repeated = api.post(
        "/v1/project-plans",
        json={
            "project_id": draft["id"],
            "project": {"title": "重复", "planned_episode_count": 1},
        },
    )
    assert repeated.status_code == 409


def test_season_plan_revisions_approval_and_episode_immutability(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "三代人的家", "planned_episode_count": 3}},
    ).json()
    season_id = plan["season"]["id"]
    first, second, third = plan["episodes"]

    changed = api.patch(
        f"/v1/episodes/{second['id']}",
        json={
            "logline": "母亲讲述搬进新城的第一晚",
            "outline": {"turn": "一家人在停电中重新靠近"},
            "source_transcript": "第二集讲妈妈搬家的故事",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["outline"]["turn"] == "一家人在停电中重新靠近"
    season = api.patch(
        f"/v1/seasons/{season_id}",
        json={
            "season_arc": {"theme": "三代人如何成为一家人"},
            "source_transcript": "这一季从分离讲到团聚",
        },
    ).json()
    approval = api.post(
        f"/v1/seasons/{season_id}/plan-approvals",
        json={
            "approved_by": "user",
            "spoken_confirmation": "我看过也听过，同意这个分集计划",
            "review_channel": "voice_and_visual",
        },
    )
    assert approval.status_code == 201
    assert approval.json()["plan_revision"] == season["plan_revision"]

    script = api.post(
        f"/v1/episodes/{first['id']}/scripts",
        json={"content": "锁定的第一集", "summary_for_voice_review": "第一集摘要"},
    ).json()
    api.post(
        f"/v1/episodes/{first['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "确认第一集"},
    )
    locked_before = api.get(f"/v1/episodes/{first['id']}").json()
    rejected = api.patch(f"/v1/episodes/{first['id']}", json={"title": "不允许覆盖的标题"})
    assert rejected.status_code == 409

    assert api.patch(f"/v1/episodes/{third['id']}", json={"title": "未来的团圆"}).status_code == 200
    assert api.get(f"/v1/episodes/{first['id']}").json() == locked_before
    latest_season = api.get(f"/v1/projects/{plan['project']['id']}/seasons").json()[0]
    assert latest_season["plan_revision"] > latest_season["approved_plan_revision"]
    revisions = api.get(f"/v1/seasons/{season_id}/plan-revisions").json()
    assert revisions[-1]["plan"]["episodes"][2]["title"] == "未来的团圆"


def test_concurrent_episode_planning_has_stable_numbering(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "并发分集"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1, "planned_episode_count": 10},
    ).json()

    def create_episode(number: int):
        return api.post(
            f"/v1/seasons/{season['id']}/episodes",
            json={"title": f"第{number}集", "episode_number": number},
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(create_episode, range(1, 11)))
    assert {response.status_code for response in responses} == {201}
    episodes = api.get(f"/v1/seasons/{season['id']}/episodes").json()
    assert [episode["episode_number"] for episode in episodes] == list(range(1, 11))
    assert len({episode["id"] for episode in episodes}) == 10


def test_each_episode_has_independent_production_progress(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "三集进度", "planned_episode_count": 3}},
    ).json()
    season_id = plan["season"]["id"]
    first = plan["episodes"][0]
    initial = api.get(f"/v1/seasons/{season_id}/production-progress").json()
    assert [item["progress_percent"] for item in initial] == [0, 0, 0]
    assert len({item["episode_id"] for item in initial}) == 3

    script = api.post(
        f"/v1/episodes/{first['id']}/scripts",
        json={"content": "第一集剧本", "summary_for_voice_review": "第一集摘要"},
    ).json()
    api.post(
        f"/v1/episodes/{first['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认第一集"},
    )
    ready = api.get(f"/v1/episodes/{first['id']}/production-progress").json()
    assert ready["progress_percent"] == 20
    assert ready["current_action"] == "可以进入制作"

    run = api.post(
        f"/v1/episodes/{first['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "progress-run"},
    ).json()
    progress = api.get(f"/v1/seasons/{season_id}/production-progress").json()
    assert [item["progress_percent"] for item in progress] == [30, 0, 0]
    assert progress[0]["run_id"] == run["id"]
    assert progress[0]["can_cancel"] is True

    api.post(
        f"/v1/production-runs/{run['id']}/cancel",
        json={"requested_by": "user", "reason": "稍后继续"},
    )
    cancelled = api.get(f"/v1/episodes/{first['id']}/production-progress").json()
    assert cancelled["stage"] == "cancelled"
    assert cancelled["can_resume"] is True
    assert cancelled["progress_percent"] == 30


def test_project_rename_archive_export_and_restore(tmp_path: Path) -> None:
    source = client(tmp_path / "source")
    plan = source.post(
        "/v1/project-plans",
        json={"project": {"title": "十集人生", "planned_episode_count": 10}},
    ).json()
    project_id = plan["project"]["id"]
    renamed = source.patch(f"/v1/projects/{project_id}", json={"title": "十集人生故事"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "十集人生故事"

    archived = source.post(f"/v1/projects/{project_id}/archive", json={"archived": True})
    assert archived.json()["archived_at"] is not None
    assert source.get("/v1/projects").json() == []
    assert source.get("/v1/projects?include_archived=true").json()[0]["id"] == project_id

    backup = source.get(f"/v1/projects/{project_id}/export").json()
    target_database = tmp_path / "target" / "nalu.sqlite3"
    target_data = tmp_path / "target" / "data"
    target = TestClient(create_app(target_database, target_data))
    restored = target.post("/v1/project-imports", json=backup)
    assert restored.status_code == 201
    assert restored.json()["id"] == project_id
    seasons = target.get(f"/v1/projects/{project_id}/seasons").json()
    episodes = target.get(f"/v1/seasons/{seasons[0]['id']}/episodes").json()
    assert [episode["episode_number"] for episode in episodes] == list(range(1, 11))

    restarted = TestClient(create_app(target_database, target_data))
    assert restarted.get(f"/v1/projects/{project_id}").json()["title"] == "十集人生故事"

    tampered = deepcopy(backup)
    tampered["payload"]["projects"][0]["title"] = "被篡改"
    rejected = client(tmp_path / "tampered").post("/v1/project-imports", json=tampered)
    assert rejected.status_code == 409

    foreign = deepcopy(backup)
    foreign["payload"]["seasons"][0]["project_id"] = "prj_foreign"
    canonical = json.dumps(foreign["payload"], ensure_ascii=False, sort_keys=True)
    foreign["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    rejected = client(tmp_path / "foreign").post("/v1/project-imports", json=foreign)
    assert rejected.status_code == 409

    legacy = deepcopy(backup)
    legacy["schema_version"] = "nalu.project-export/v1"
    legacy["payload"].pop("season_plan_revisions")
    legacy["payload"].pop("season_plan_approval_records")
    legacy["payload"].pop("asset_consent_records")
    legacy["payload"].pop("feedback_items")
    legacy["payload"].pop("memory_cards")
    legacy["payload"].pop("memory_card_revisions")
    legacy["payload"].pop("memory_card_confirmation_records")
    legacy["payload"].pop("library_entities")
    legacy["payload"].pop("library_entity_revisions")
    legacy["payload"].pop("library_entity_confirmation_records")
    legacy["payload"].pop("continuity_extraction_confirmation_records")
    legacy["payload"]["projects"][0].pop("creative_format")
    legacy["payload"]["projects"][0].pop("production_pipeline")
    canonical = json.dumps(legacy["payload"], ensure_ascii=False, sort_keys=True)
    legacy["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    restored_legacy = client(tmp_path / "legacy").post("/v1/project-imports", json=legacy)
    assert restored_legacy.status_code == 201


def test_project_plan_idempotency_is_concurrent_and_payload_bound(tmp_path: Path) -> None:
    api = client(tmp_path)
    payload = {
        "project": {"title": "只创建一次", "planned_episode_count": 3},
        "season_title": "第一季",
    }

    def create_once(_index: int):
        return api.post(
            "/v1/project-plans",
            json=payload,
            headers={"Idempotency-Key": "voice-session-001"},
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(create_once, range(6)))

    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["project"]["id"] for response in responses}) == 1
    assert len(api.get("/v1/projects").json()) == 1

    conflict = api.post(
        "/v1/project-plans",
        json={"project": {"title": "不同请求", "planned_episode_count": 1}},
        headers={"Idempotency-Key": "voice-session-001"},
    )
    assert conflict.status_code == 409


def test_episode_lifecycle_and_restart_recovery(tmp_path: Path) -> None:
    database_path = tmp_path / "restart.sqlite3"
    data_root = tmp_path / "data"
    first = TestClient(create_app(database_path, data_root))
    _, _, episode = create_approved_episode(first)

    lifecycle = first.get(f"/v1/episodes/{episode['id']}/events").json()
    assert [(row["from_status"], row["to_status"]) for row in lifecycle] == [
        ("planned", "script_review"),
        ("script_review", "script_approved"),
    ]
    invalid = first.post(
        f"/v1/episodes/{episode['id']}/transition",
        json={
            "target_status": "published",
            "requested_by": "test",
            "reason": "attempt to skip required gates",
        },
    )
    assert invalid.status_code == 409

    production_path = f"/v1/episodes/{episode['id']}/production-runs"
    run = first.post(
        production_path,
        json={"dry_run": True},
        headers={"Idempotency-Key": "restart-safe-run"},
    ).json()
    assert first.get(f"/v1/episodes/{episode['id']}").json()["status"] == "preproduction"

    restarted = TestClient(create_app(database_path, data_root))
    assert restarted.get(f"/v1/production-runs/{run['id']}").json()["id"] == run["id"]
    assert (
        restarted.get(f"/v1/production-runs/{run['id']}/events").json()[0]["event_type"]
        == "run_created"
    )
    assert (
        restarted.get(f"/v1/episodes/{episode['id']}/events").json()[-1]["to_status"]
        == "preproduction"
    )
    replay = restarted.post(
        production_path,
        json={"dry_run": True},
        headers={"Idempotency-Key": "restart-safe-run"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == run["id"]


def test_database_migration_preserves_existing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE legacy_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserve-me')")

    api = create_app(database_path, tmp_path / "data")
    assert api.state.repository.db.schema_version() == 12
    with sqlite3.connect(database_path) as connection:
        marker = connection.execute("SELECT value FROM legacy_marker").fetchone()[0]
        approval_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'approval_records'"
        ).fetchone()
    assert marker == "preserve-me"
    assert approval_table == ("approval_records",)


def test_local_runtime_files_are_private_to_current_user(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "private.txt",
            "kind": "source_document",
            "name": "私人采访",
        },
        content=b"private",
        headers={"Content-Type": "text/plain"},
    ).json()
    stored_path = Path(unquote(urlparse(imported["local_uri"]).path))
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "private-file-modes"},
    ).json()
    package_path = Path(run["package_path"])

    assert stat.S_IMODE((tmp_path / "test.sqlite3").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "data").stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(package_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(package_path.stat().st_mode) == 0o600


def test_populated_v1_database_upgrades_without_project_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "populated.sqlite3"
    data_root = tmp_path / "data"
    before = TestClient(create_app(database_path, data_root))
    project, _, episode = create_approved_episode(before)

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TABLE episode_events")
        connection.execute("DROP TABLE idempotency_records")
        connection.execute("DROP TABLE idempotent_operations")
        connection.execute("DELETE FROM schema_migrations WHERE version >= 2")

    after = TestClient(create_app(database_path, data_root))
    assert after.app.state.repository.db.schema_version() == 12
    assert after.get(f"/v1/projects/{project['id']}").json()["title"] == "我的一生"
    assert after.get(f"/v1/episodes/{episode['id']}").json()["approved_script_revision"] == 1
    approvals = after.get(f"/v1/episodes/{episode['id']}/script-approvals").json()
    assert approvals[0]["spoken_confirmation"] == "我确认这个剧本"


def test_biometric_asset_requires_consent(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, _ = create_approved_episode(api)
    response = api.post(
        f"/v1/projects/{project['id']}/assets",
        json={
            "kind": "character_image",
            "name": "主角正面照",
            "local_uri": "file:///tmp/portrait.jpg",
            "consent_granted": False,
        },
    )
    assert response.status_code == 422


def test_local_asset_import_consent_revocation_and_path_safety(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    endpoint = f"/v1/projects/{project['id']}/asset-imports"

    traversal = api.post(
        endpoint,
        params={
            "filename": "../../portrait.jpg",
            "kind": "character_image",
            "name": "不安全文件",
            "consent_granted": True,
            "consent_granted_by": "user",
            "consent_statement": "我同意用于本项目",
        },
        content=b"fake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert traversal.status_code == 409
    legacy_escape = api.post(
        f"/v1/projects/{project['id']}/assets",
        json={
            "kind": "source_document",
            "name": "系统文件",
            "local_uri": "file:///etc/passwd",
        },
    )
    assert legacy_escape.status_code == 409

    missing_consent = api.post(
        endpoint,
        params={
            "filename": "portrait.jpg",
            "kind": "character_image",
            "name": "主角照片",
        },
        content=b"fake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert missing_consent.status_code == 409

    imported = api.post(
        endpoint,
        params={
            "filename": "portrait.jpg",
            "kind": "character_image",
            "name": "主角照片",
            "subject_name": "主人公",
            "episode_id": episode["id"],
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "我同意这张照片仅用于本项目",
        },
        content=b"fake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert imported.status_code == 201
    asset = imported.json()
    stored_path = Path(unquote(urlparse(asset["local_uri"]).path)).resolve()
    assert stored_path.is_relative_to((tmp_path / "data" / "assets").resolve())
    assert stored_path.read_bytes() == b"fake-jpeg"
    records = api.get(f"/v1/assets/{asset['id']}/consent-records").json()
    assert records[0]["action_type"] == "granted"
    assert records[0]["statement"] == "我同意这张照片仅用于本项目"

    revoked = api.post(
        f"/v1/assets/{asset['id']}/consent-revocations",
        json={"requested_by": "本人", "reason": "我不再同意使用照片"},
    )
    assert revoked.status_code == 201
    assert revoked.json()["action_type"] == "revoked"
    stored_asset = api.get(f"/v1/projects/{project['id']}/assets").json()[0]
    assert stored_asset["consent_granted"] is False
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "revoked-biometric"},
    )
    assert blocked.status_code == 409


def test_project_season_and_episode_asset_scope_inheritance(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, season, episode = create_approved_episode(api)
    endpoint = f"/v1/projects/{project['id']}/asset-imports"

    project_asset = api.post(
        endpoint,
        params={
            "filename": "bible.txt",
            "kind": "source_document",
            "name": "项目资料",
        },
        content=b"project",
        headers={"Content-Type": "text/plain"},
    )
    season_asset = api.post(
        endpoint,
        params={
            "filename": "season.jpg",
            "kind": "scene_reference",
            "name": "本季场景",
            "season_id": season["id"],
        },
        content=b"season",
        headers={"Content-Type": "image/jpeg"},
    )
    episode_asset = api.post(
        endpoint,
        params={
            "filename": "episode.jpg",
            "kind": "prop_reference",
            "name": "本集道具",
            "episode_id": episode["id"],
        },
        content=b"episode",
        headers={"Content-Type": "image/jpeg"},
    )
    assert [response.status_code for response in (project_asset, season_asset, episode_asset)] == [
        201,
        201,
        201,
    ]
    assert season_asset.json()["season_id"] == season["id"]
    assert episode_asset.json()["episode_id"] == episode["id"]

    season_assets = api.get(
        f"/v1/projects/{project['id']}/assets", params={"season_id": season["id"]}
    ).json()
    assert {asset["name"] for asset in season_assets} == {"项目资料", "本季场景"}
    episode_assets = api.get(
        f"/v1/projects/{project['id']}/assets", params={"episode_id": episode["id"]}
    ).json()
    assert {asset["name"] for asset in episode_assets} == {
        "项目资料",
        "本季场景",
        "本集道具",
    }
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "three-level-asset-scope"},
    )
    assert run.status_code == 201
    for asset in (project_asset.json(), season_asset.json(), episode_asset.json()):
        dependencies = api.get(f"/v1/assets/{asset['id']}/dependencies").json()
        assert dependencies["production_run_ids"] == [run.json()["id"]]

    ambiguous = api.post(
        endpoint,
        params={
            "filename": "ambiguous.jpg",
            "kind": "scene_reference",
            "name": "范围不明确",
            "season_id": season["id"],
            "episode_id": episode["id"],
        },
        content=b"ambiguous",
        headers={"Content-Type": "image/jpeg"},
    )
    assert ambiguous.status_code == 409

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    legacy_v3 = deepcopy(backup)
    legacy_v3["schema_version"] = "nalu.project-export/v3"
    legacy_v3["payload"].pop("feedback_items")
    legacy_v3["payload"].pop("memory_cards")
    legacy_v3["payload"].pop("memory_card_revisions")
    legacy_v3["payload"].pop("memory_card_confirmation_records")
    legacy_v3["payload"].pop("library_entities")
    legacy_v3["payload"].pop("library_entity_revisions")
    legacy_v3["payload"].pop("library_entity_confirmation_records")
    legacy_v3["payload"].pop("continuity_extraction_confirmation_records")
    legacy_v3["payload"]["projects"][0].pop("creative_format")
    legacy_v3["payload"]["projects"][0].pop("production_pipeline")
    for asset in legacy_v3["payload"]["assets"]:
        asset.pop("season_id")
    canonical = json.dumps(legacy_v3["payload"], ensure_ascii=False, sort_keys=True)
    legacy_v3["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    restored = client(tmp_path / "legacy-v3").post("/v1/project-imports", json=legacy_v3)
    assert restored.status_code == 201


def test_asset_dependency_blocks_deletion_after_snapshot(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "room.jpg",
            "kind": "scene_reference",
            "name": "老屋",
        },
        content=b"scene-image",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "asset-snapshot"},
    )
    report = api.get(f"/v1/assets/{imported['id']}/dependencies").json()
    assert report["can_delete"] is False
    assert len(report["production_run_ids"]) == 1
    assert api.delete(f"/v1/assets/{imported['id']}").status_code == 409


def test_complete_privacy_export_and_confirmed_project_deletion(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "portrait.jpg",
            "kind": "character_image",
            "name": "本人照片",
            "consent_granted": True,
            "consent_granted_by": "本人",
            "consent_statement": "我同意仅用于这部短剧",
        },
        content=b"private-photo-bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "privacy-deletion-run"},
    ).json()

    exported = api.get(f"/v1/projects/{project['id']}/privacy-export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = set(archive.namelist())
        media_name = f"media/{imported['id']}/portrait.jpg"
        assert {"project-export.json", "privacy-manifest.json", media_name} <= names
        assert archive.read(media_name) == b"private-photo-bytes"
        project_backup = json.loads(archive.read("project-export.json"))
        assert project_backup["schema_version"] == "nalu.project-export/v8"
        assert project_backup["payload"]["asset_consent_records"][0]["action_type"] == "granted"
        manifest = json.loads(archive.read("privacy-manifest.json"))
        assert manifest["database_included"] is False
        assert manifest["secret_material_included"] is False

    preview = api.get(f"/v1/projects/{project['id']}/deletion-preview").json()
    assert preview["asset_count"] == 1
    assert preview["production_run_count"] == 1
    refused = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}",
        json={
            "confirmation_title": project["title"],
            "requested_by": "user",
            "delete_production_snapshots": False,
        },
    )
    assert refused.status_code == 409
    assert api.get(f"/v1/projects/{project['id']}").status_code == 200

    deleted = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}",
        json={
            "confirmation_title": project["title"],
            "requested_by": "user",
            "delete_production_snapshots": True,
        },
    )
    assert deleted.status_code == 200
    assert deleted.json() == {
        "project_id": project["id"],
        "deleted": True,
        "removed_asset_count": 1,
        "removed_production_run_count": 1,
        "verified_absent": True,
    }
    assert api.get(f"/v1/projects/{project['id']}").status_code == 404
    assert not (tmp_path / "data" / "assets" / project["id"]).exists()
    assert not (tmp_path / "data" / "runs" / run["id"]).exists()
    assert list((tmp_path / "data" / "privacy-exports").glob(f"{project['id']}-*")) == []


def test_production_requires_approved_script(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "测试项目"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "第一集", "episode_number": 1},
    ).json()
    response = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True})
    assert response.status_code == 409


def test_dry_run_writes_immutable_package(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    response = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "seedance-2.0-pro"},
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "preflight"
    package = Path(run["package_path"])
    assert package.exists()
    assert "package_sha256" in package.read_text(encoding="utf-8")
    assert package.with_name("qingshan-preflight-report.json").exists()
    workspace = package.with_name("qingshan-workspace")
    assert (workspace / "workspace-manifest.json").exists()
    assert (workspace / "source" / "E01_APPROVED_SCRIPT.md").exists()
    assert (workspace / "workflow" / "work_queue.json").exists()


def test_production_run_idempotency_and_paid_key_requirement(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    path = f"/v1/episodes/{episode['id']}/production-runs"
    headers = {"Idempotency-Key": "episode-1-production-v1"}
    first = api.post(path, json={"dry_run": True}, headers=headers)
    replay = api.post(path, json={"dry_run": True}, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    changed = api.post(
        path,
        json={"dry_run": True, "requested_model": "MiniMax-H3"},
        headers=headers,
    )
    assert changed.status_code == 409

    other_api = client(tmp_path / "paid")
    _, _, paid_episode = create_approved_episode(other_api)
    paid = other_api.post(
        f"/v1/episodes/{paid_episode['id']}/production-runs",
        json={
            "dry_run": False,
            "paid_generation_approved": True,
            "approved_by": "owner",
        },
    )
    assert paid.status_code == 409
    assert "Idempotency-Key" in paid.json()["detail"]


def test_prohibited_model_is_rejected(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    response = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "seedance-2.0-fast"},
    )
    assert response.status_code == 409


def test_run_events_cancel_and_resume(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "MiniMax-H3"},
    ).json()

    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert [event["event_type"] for event in events] == ["run_created"]

    cancelled = api.post(
        f"/v1/production-runs/{run['id']}/cancel",
        json={"requested_by": "user", "reason": "先暂停，稍后继续"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    resumed = api.post(
        f"/v1/production-runs/{run['id']}/resume",
        json={"requested_by": "user", "reason": "继续制作"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "preflight"

    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert [event["sequence"] for event in events] == [1, 2, 3]


def test_run_events_are_ordered_under_concurrent_writes(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    repository = api.app.state.repository

    def append(index: int) -> None:
        repository.append_run_event(run["id"], "progress", payload={"index": index})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(8)))

    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert [event["sequence"] for event in events] == list(range(1, 10))
