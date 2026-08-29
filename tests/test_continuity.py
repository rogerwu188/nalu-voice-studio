import json
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def two_episode_project(api: TestClient) -> dict:
    return api.post(
        "/v1/project-plans",
        json={"project": {"title": "连续性测试", "planned_episode_count": 2}},
    ).json()


def end_state() -> dict:
    return {
        "characters": {
            "lin": {
                "location": "老火车站",
                "wardrobe": ["蓝色外套"],
                "injuries": ["左手包扎"],
                "held_props": ["旧皮箱"],
                "relationships": {"mei": "已经和解的姐姐"},
                "revealed_facts": ["父亲留下了一封信"],
            }
        },
        "props": {
            "suitcase": {
                "owner": "lin",
                "location": "老火车站",
                "condition": "锁扣损坏",
            }
        },
        "scene_location": "老火车站",
        "story_time": "1986年冬夜",
        "weather": "大雪",
    }


def create_snapshot(api: TestClient, first_episode_id: str) -> dict:
    response = api.post(
        f"/v1/episodes/{first_episode_id}/continuity-snapshots",
        json={
            "state": end_state(),
            "unresolved_hooks": ["父亲的信还没有打开"],
        },
    )
    assert response.status_code == 201
    return response.json()


def approve_script(api: TestClient, episode_id: str, metadata: dict) -> dict:
    script = api.post(
        f"/v1/episodes/{episode_id}/scripts",
        json={
            "content": "第二集连续性剧本",
            "summary_for_voice_review": "主人公从车站继续出发。",
            "narrative_metadata": metadata,
        },
    ).json()
    approved = api.post(
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认这个剧本"},
    )
    assert approved.status_code == 200
    return approved.json()


def test_matching_opening_state_passes_and_is_snapshotted(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = two_episode_project(api)
    first, second = plan["episodes"]
    snapshot = create_snapshot(api, first["id"])

    preflight = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={"opening_state": end_state()},
    )
    assert preflight.status_code == 200
    assert preflight.json() == {
        "inherited_snapshot_id": snapshot["id"],
        "can_proceed": True,
        "conflicts": [],
        "explanation": "opening state is consistent with the previous episode",
    }

    approve_script(api, second["id"], {"opening_continuity": end_state()})
    run = api.post(
        f"/v1/episodes/{second['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "continuity-match"},
    )
    assert run.status_code == 201
    package = json.loads(Path(run.json()["package_path"]).read_text(encoding="utf-8"))
    assert package["continuity"]["id"] == snapshot["id"]
    assert package["continuity_preflight"]["can_proceed"] is True


def test_unexplained_character_prop_and_time_conflicts_block(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = two_episode_project(api)
    first, second = plan["episodes"]
    create_snapshot(api, first["id"])
    opening = end_state()
    opening["characters"]["lin"]["location"] = "姐姐家"
    opening["characters"]["lin"]["wardrobe"] = ["白色衬衫"]
    opening["characters"]["lin"]["injuries"] = []
    opening["characters"]["lin"]["revealed_facts"] = []
    opening["props"]["suitcase"]["owner"] = "mei"
    opening["story_time"] = "1987年春晨"

    preflight = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={"opening_state": opening},
    ).json()
    paths = {item["path"] for item in preflight["conflicts"]}
    assert preflight["can_proceed"] is False
    assert paths == {
        "story_time",
        "characters.lin.location",
        "characters.lin.wardrobe",
        "characters.lin.injuries",
        "characters.lin.revealed_facts",
        "props.suitcase.owner",
    }

    approve_script(api, second["id"], {"opening_continuity": opening})
    blocked = api.post(
        f"/v1/episodes/{second['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "continuity-blocked"},
    )
    assert blocked.status_code == 409
    assert "characters.lin.location" in blocked.text
    assert "props.suitcase.owner" in blocked.text


def test_explanations_and_exact_versioned_override_are_fail_closed(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = two_episode_project(api)
    first, second = plan["episodes"]
    create_snapshot(api, first["id"])
    opening = end_state()
    opening["scene_location"] = "姐姐家"
    opening["weather"] = "晴"

    explained = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={
            "opening_state": opening,
            "transition_explanations": {
                "scene_location": "字幕说明三天后，主人公已经回到姐姐家。",
                "weather": "场景发生在暴雪后的晴天。",
            },
        },
    ).json()
    assert explained["can_proceed"] is True
    assert all(item["explanation"] for item in explained["conflicts"])

    bad_override = {
        "schema_version": "nalu.continuity-override/v1",
        "conflict_paths": ["scene_location"],
        "reason": "用户决定跳过天气交代",
        "reviewed_by": "user",
        "spoken_confirmation": "我确认这个连续性覆盖",
    }
    rejected = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={"opening_state": opening, "override": bad_override},
    ).json()
    assert rejected["can_proceed"] is False
    assert "exactly match" in rejected["explanation"]

    ambiguous = dict(bad_override)
    ambiguous["spoken_confirmation"] = "大概可以"
    invalid_confirmation = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={"opening_state": opening, "override": ambiguous},
    )
    assert invalid_confirmation.status_code == 422

    exact_override = dict(bad_override)
    exact_override["conflict_paths"] = ["scene_location", "weather"]
    accepted = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={"opening_state": opening, "override": exact_override},
    ).json()
    assert accepted["can_proceed"] is True
    assert all(item["overridden"] for item in accepted["conflicts"])

    approve_script(
        api,
        second["id"],
        {
            "opening_continuity": opening,
            "continuity_override": exact_override,
        },
    )
    run = api.post(
        f"/v1/episodes/{second['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "continuity-override"},
    )
    assert run.status_code == 201


def test_inherited_state_requires_an_opening_declaration(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = two_episode_project(api)
    first, second = plan["episodes"]
    create_snapshot(api, first["id"])
    approve_script(api, second["id"], {})
    blocked = api.post(
        f"/v1/episodes/{second['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "continuity-missing"},
    )
    assert blocked.status_code == 409
    assert "opening_continuity" in blocked.text

    omitted = api.post(
        f"/v1/episodes/{second['id']}/continuity-preflight",
        json={"opening_state": {}},
    ).json()
    assert omitted["can_proceed"] is False
    assert {item["path"] for item in omitted["conflicts"]} >= {
        "characters.lin",
        "props.suitcase",
        "scene_location",
        "story_time",
        "weather",
    }
