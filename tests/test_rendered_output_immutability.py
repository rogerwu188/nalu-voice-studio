import hashlib
from pathlib import Path

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


def seal_payload() -> dict:
    return {
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
