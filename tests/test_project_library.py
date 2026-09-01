import json
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def create_and_approve_script(api: TestClient, episode_id: str) -> None:
    script = api.post(
        f"/v1/episodes/{episode_id}/scripts",
        json={
            "content": "经过用户确认的剧本",
            "summary_for_voice_review": "人物继续完成旅程。",
        },
    ).json()
    approved = api.post(
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}/approve",
        json={"approved_by": "tester", "spoken_confirmation": "我确认当前剧本"},
    )
    assert approved.status_code == 200


def library_payload(kind: str, name: str) -> dict:
    return {
        "kind": kind,
        "name": name,
        "description": f"{name}的项目级设定",
        "attributes": {"tone": "温暖", "canonical": True},
        "source_channel": "voice",
        "change_summary": "用户第一次口述确认前草稿",
    }


def confirm(api: TestClient, entity_id: str, revision: int) -> None:
    response = api.post(
        f"/v1/library-entities/{entity_id}/confirmations",
        json={
            "confirmed_by": "local-user",
            "reviewed_revision": revision,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这份项目设定",
        },
    )
    assert response.status_code == 201


def test_five_project_libraries_are_versioned_and_confirmed(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "项目资料库"}).json()
    created = []
    for kind, name in (
        ("character", "林叔"),
        ("scene", "老火车站"),
        ("prop", "旧皮箱"),
        ("voice", "林叔旁白"),
        ("style", "温暖旧胶片"),
    ):
        response = api.post(
            f"/v1/projects/{project['id']}/library-entities",
            json=library_payload(kind, name),
        )
        assert response.status_code == 201
        created.append(response.json())

    duplicate = api.post(
        f"/v1/projects/{project['id']}/library-entities",
        json=library_payload("character", "  林叔  "),
    )
    assert duplicate.status_code == 409

    character = created[0]
    ambiguous = api.post(
        f"/v1/library-entities/{character['id']}/confirmations",
        json={
            "confirmed_by": "local-user",
            "reviewed_revision": 1,
            "review_channel": "voice",
            "spoken_confirmation": "听起来可以",
        },
    )
    assert ambiguous.status_code == 422
    confirm(api, character["id"], 1)

    revision = api.post(
        f"/v1/library-entities/{character['id']}/revisions",
        json={
            "name": "林叔",
            "description": "林叔戴旧眼镜，左手有伤。",
            "attributes": {"wardrobe": ["蓝色外套"], "injury": "左手包扎"},
            "source_channel": "voice",
            "change_summary": "补充外形和伤势",
        },
    )
    assert revision.status_code == 201
    assert revision.json()["current_revision"] == 2
    assert revision.json()["confirmed_revision"] == 1
    stale = api.post(
        f"/v1/library-entities/{character['id']}/confirmations",
        json={
            "confirmed_by": "local-user",
            "reviewed_revision": 1,
            "review_channel": "visual",
            "spoken_confirmation": "我确认旧版本",
        },
    )
    assert stale.status_code == 409

    listed = api.get(f"/v1/projects/{project['id']}/library-entities").json()
    assert {item["kind"] for item in listed} == {
        "character", "scene", "prop", "voice", "style"
    }
    history = api.get(
        f"/v1/library-entities/{character['id']}/revisions"
    ).json()
    assert [item["revision"] for item in history] == [1, 2]

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v19"
    restored_api = client(tmp_path / "restored")
    restored = restored_api.post("/v1/project-imports", json=backup)
    assert restored.status_code == 201
    restored_entities = restored_api.get(
        f"/v1/projects/{project['id']}/library-entities"
    ).json()
    assert len(restored_entities) == 5
    assert restored_entities[0]["current_revision"] >= 1


def test_production_packages_freeze_confirmed_library_revision(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "库快照回归", "planned_episode_count": 2}},
    ).json()
    project_id = plan["project"]["id"]
    first, second = plan["episodes"]
    for episode in (first, second):
        create_and_approve_script(api, episode["id"])

    entity = api.post(
        f"/v1/projects/{project_id}/library-entities",
        json=library_payload("character", "林叔"),
    ).json()
    confirm(api, entity["id"], 1)

    first_run = api.post(
        f"/v1/episodes/{first['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "library-first"},
    )
    assert first_run.status_code == 201
    first_path = Path(first_run.json()["package_path"])
    first_package_before = first_path.read_bytes()
    assert json.loads(first_package_before)["resolved_library"][0][
        "confirmed_revision"
    ] == 1

    updated = api.post(
        f"/v1/library-entities/{entity['id']}/revisions",
        json={
            "name": "林叔",
            "description": "第二版设定",
            "attributes": {"wardrobe": ["灰色大衣"]},
            "source_channel": "visual",
            "change_summary": "用户更换了服装设定",
        },
    ).json()
    confirm(api, entity["id"], updated["current_revision"])

    second_run = api.post(
        f"/v1/episodes/{second['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "library-second"},
    )
    assert second_run.status_code == 201
    second_package = json.loads(
        Path(second_run.json()["package_path"]).read_text(encoding="utf-8")
    )
    assert second_package["resolved_library"][0]["confirmed_revision"] == 2
    character_index = json.loads(
        (
            Path(second_run.json()["package_path"]).parent
            / "qingshan-workspace/libraries/characters/index.json"
        ).read_text(encoding="utf-8")
    )
    assert character_index["schema_version"] == "nalu.qingshan-resolved-library/v1"
    assert character_index["confirmed_entities"][0]["confirmed_revision"] == 2
    assert first_path.read_bytes() == first_package_before


def test_confirmed_aliases_resolve_and_collisions_fail_closed(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "家人称呼消歧"}).json()
    mother_payload = library_payload("character", "李小梅")
    mother_payload["attributes"] = {"aliases": ["妈妈", "照片左边的人"]}
    mother = api.post(
        f"/v1/projects/{project['id']}/library-entities", json=mother_payload
    ).json()
    confirm(api, mother["id"], 1)

    resolved = api.get(
        f"/v1/projects/{project['id']}/library-entity-resolution",
        params={"kind": "character", "mention": "  妈妈  "},
    )
    assert resolved.status_code == 200
    assert resolved.json()["entity_id"] == mother["id"]
    assert resolved.json()["matched_by"] == "alias"

    aunt_payload = library_payload("character", "王阿姨")
    aunt_payload["attributes"] = {"aliases": ["妈妈"]}
    aunt = api.post(
        f"/v1/projects/{project['id']}/library-entities", json=aunt_payload
    ).json()
    collision = api.post(
        f"/v1/library-entities/{aunt['id']}/confirmations",
        json={
            "confirmed_by": "local-user",
            "reviewed_revision": 1,
            "review_channel": "voice",
            "spoken_confirmation": "我确认这份项目设定",
        },
    )
    assert collision.status_code == 409

    unresolved = api.get(
        f"/v1/projects/{project['id']}/library-entity-resolution",
        params={"kind": "character", "mention": "没出现过的人"},
    )
    assert unresolved.status_code == 404


def test_documentary_projects_cannot_silently_use_short_drama_adapter(tmp_path: Path) -> None:
    api = client(tmp_path)
    blocked = api.post(
        "/v1/projects",
        json={
            "title": "父亲的照片",
            "creative_format": "documentary_series",
            "production_pipeline": "qingshan-short-drama",
        },
    )
    assert blocked.status_code == 422

    planned = api.post(
        "/v1/projects",
        json={
            "title": "父亲的照片",
            "creative_format": "documentary_series",
            "production_pipeline": "unassigned",
            "project_bible": {
                "documentary_mode": "archival_voiceover",
                "generated_reenactment_label_required": True,
            },
        },
    )
    assert planned.status_code == 201
    assert planned.json()["production_pipeline"] == "unassigned"
