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


def test_prohibited_model_is_rejected(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    response = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "seedance-2.0-fast"},
    )
    assert response.status_code == 409
