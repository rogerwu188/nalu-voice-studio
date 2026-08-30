from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app

HOOK = "父亲的信还没有打开"


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def setup_two_episodes(api: TestClient, audience_mode: str = "general") -> tuple[dict, dict, dict]:
    plan = api.post(
        "/v1/project-plans",
        json={
            "project": {
                "title": "悬念关闭测试",
                "audience_mode": audience_mode,
                "planned_episode_count": 2,
            }
        },
    ).json()
    first, second = plan["episodes"]
    snapshot = api.post(
        f"/v1/episodes/{first['id']}/continuity-snapshots",
        json={"state": {"scene_location": "旧火车站"}, "unresolved_hooks": [HOOK]},
    ).json()
    return plan, second, snapshot


def review(snapshot: dict, disposition: str, *, guardian: bool = False) -> dict:
    return {
        "schema_version": "nalu.continuity-hook-review/v1",
        "inherited_snapshot_id": snapshot["id"],
        "resolutions": [
            {
                "hook": HOOK,
                "disposition": disposition,
                "explanation": "本集继续追查" if disposition == "carry_forward" else "信在本集打开",
            }
        ],
        "reviewed_by": "本人",
        "spoken_confirmation": "我确认这份悬念安排",
        "guardian_approval": guardian,
    }


def test_hook_review_is_exact_versioned_and_fail_closed(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, second, snapshot = setup_two_episodes(api)
    endpoint = f"/v1/episodes/{second['id']}/continuity-preflight"

    missing = api.post(endpoint, json={"opening_state": {"scene_location": "旧火车站"}})
    assert missing.status_code == 200
    assert missing.json()["hook_review_status"] == "missing"
    assert missing.json()["can_proceed"] is False

    stale_review = review(snapshot, "carry_forward")
    stale_review["inherited_snapshot_id"] = "con_stale"
    stale = api.post(
        endpoint,
        json={"opening_state": {"scene_location": "旧火车站"}, "hook_review": stale_review},
    ).json()
    assert stale["hook_review_status"] == "stale"

    incomplete_review = review(snapshot, "carry_forward")
    incomplete_review["resolutions"][0]["hook"] = "另一个悬念"
    incomplete = api.post(
        endpoint,
        json={
            "opening_state": {"scene_location": "旧火车站"},
            "hook_review": incomplete_review,
        },
    ).json()
    assert incomplete["hook_review_status"] == "incomplete"

    ambiguous = review(snapshot, "resolved")
    ambiguous["spoken_confirmation"] = "应该可以"
    assert api.post(
        endpoint,
        json={"opening_state": {"scene_location": "旧火车站"}, "hook_review": ambiguous},
    ).status_code == 422


def test_child_hook_review_requires_guardian(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, second, snapshot = setup_two_episodes(api, audience_mode="child")
    endpoint = f"/v1/episodes/{second['id']}/continuity-preflight"
    payload = {
        "opening_state": {"scene_location": "旧火车站"},
        "hook_review": review(snapshot, "carry_forward"),
    }
    assert api.post(endpoint, json=payload).status_code == 409
    payload["hook_review"]["guardian_approval"] = True
    assert api.post(endpoint, json=payload).json()["can_proceed"] is True


def test_production_rechecks_missing_hook_review(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, second, _ = setup_two_episodes(api)
    script = api.post(
        f"/v1/episodes/{second['id']}/scripts",
        json={
            "content": "第二集没有交代上一集的信。",
            "summary_for_voice_review": "继续从火车站开始。",
            "narrative_metadata": {
                "opening_continuity": {"scene_location": "旧火车站"}
            },
        },
    ).json()
    assert api.post(
        f"/v1/episodes/{second['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "本人", "spoken_confirmation": "我确认这个剧本"},
    ).status_code == 200
    blocked = api.post(
        f"/v1/episodes/{second['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "missing-hook-review"},
    )
    assert blocked.status_code == 409
    assert "every inherited unresolved hook" in blocked.text


def test_confirmed_ending_must_match_resolved_or_carried_hook(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, second, snapshot = setup_two_episodes(api)
    hook_review = review(snapshot, "resolved")
    script = api.post(
        f"/v1/episodes/{second['id']}/scripts",
        json={
            "content": "第二集打开了父亲的信。",
            "summary_for_voice_review": "父亲的信已经打开。",
            "narrative_metadata": {
                "opening_continuity": {"scene_location": "旧火车站"},
                "continuity_hook_review": hook_review,
                "ending_continuity": {"scene_location": "姐姐家"},
                "ending_unresolved_hooks": [],
            },
        },
    ).json()
    assert api.post(
        f"/v1/episodes/{second['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "本人", "spoken_confirmation": "我确认这个剧本"},
    ).status_code == 200
    proposal = api.get(
        f"/v1/episodes/{second['id']}/continuity-extraction-proposal"
    ).json()
    bad = {
        "reviewed_script_revision": proposal["script_revision"],
        "proposal_sha256": proposal["proposal_sha256"],
        "reviewed_state": proposal["state"],
        "unresolved_hooks": [HOOK],
        "confirmed_by": "本人",
        "spoken_confirmation": "我确认这个结尾交接卡",
        "review_channel": "voice_and_visual",
        "change_summary": "把已经解决的悬念又标成未解决",
    }
    blocked = api.post(
        f"/v1/episodes/{second['id']}/continuity-extraction-confirmations", json=bad
    )
    assert blocked.status_code == 409
    assert "closed hook remains" in blocked.text

    good = dict(bad)
    good["unresolved_hooks"] = []
    good["change_summary"] = ""
    accepted = api.post(
        f"/v1/episodes/{second['id']}/continuity-extraction-confirmations", json=good
    )
    assert accepted.status_code == 201
    assert accepted.json()["snapshot"]["unresolved_hooks"] == []
