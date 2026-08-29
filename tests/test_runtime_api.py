import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

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
    rejected = api.patch(
        f"/v1/episodes/{first['id']}", json={"title": "不允许覆盖的标题"}
    )
    assert rejected.status_code == 409

    assert api.patch(
        f"/v1/episodes/{third['id']}", json={"title": "未来的团圆"}
    ).status_code == 200
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
    renamed = source.patch(
        f"/v1/projects/{project_id}", json={"title": "十集人生故事"}
    )
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
    assert restarted.get(f"/v1/production-runs/{run['id']}/events").json()[0][
        "event_type"
    ] == "run_created"
    assert restarted.get(f"/v1/episodes/{episode['id']}/events").json()[-1][
        "to_status"
    ] == "preproduction"
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
    assert api.state.repository.db.schema_version() == 5
    with sqlite3.connect(database_path) as connection:
        marker = connection.execute("SELECT value FROM legacy_marker").fetchone()[0]
        approval_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'approval_records'"
        ).fetchone()
    assert marker == "preserve-me"
    assert approval_table == ("approval_records",)


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
    assert after.app.state.repository.db.schema_version() == 5
    assert after.get(f"/v1/projects/{project['id']}").json()["title"] == "我的一生"
    assert after.get(f"/v1/episodes/{episode['id']}").json()[
        "approved_script_revision"
    ] == 1
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
    response = api.post(
        f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}
    )
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
