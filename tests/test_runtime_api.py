import sqlite3
from concurrent.futures import ThreadPoolExecutor
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


def test_database_migration_preserves_existing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE legacy_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserve-me')")

    api = create_app(database_path, tmp_path / "data")
    assert api.state.repository.db.schema_version() == 1
    with sqlite3.connect(database_path) as connection:
        marker = connection.execute("SELECT value FROM legacy_marker").fetchone()[0]
        approval_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'approval_records'"
        ).fetchone()
    assert marker == "preserve-me"
    assert approval_table == ("approval_records",)


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
