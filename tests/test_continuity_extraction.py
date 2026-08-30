from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def create_plan(api: TestClient, audience_mode: str = "general") -> dict:
    return api.post(
        "/v1/project-plans",
        json={
            "project": {
                "title": "结尾状态提取测试",
                "audience_mode": audience_mode,
                "planned_episode_count": 2,
            }
        },
    ).json()


def approve_script(
    api: TestClient,
    episode_id: str,
    *,
    content: str = "第一集定稿剧本",
    narrative_metadata: dict | None = None,
    guardian_approval: bool = False,
) -> dict:
    script = api.post(
        f"/v1/episodes/{episode_id}/scripts",
        json={
            "content": content,
            "summary_for_voice_review": "这一集结束在旧火车站。",
            "narrative_metadata": narrative_metadata or {},
        },
    ).json()
    response = api.post(
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}/approve",
        json={
            "approved_by": "本人",
            "spoken_confirmation": "我确认这个剧本",
            "guardian_approval": guardian_approval,
        },
    )
    assert response.status_code == 200
    return response.json()


def ending_state() -> dict:
    return {
        "characters": {
            "林叔": {
                "location": "旧火车站",
                "wardrobe": ["蓝色外套"],
                "injuries": ["左手包扎"],
                "held_props": ["旧皮箱"],
                "relationships": {"姐姐": "已经和解"},
                "revealed_facts": ["父亲留下了一封信"],
            }
        },
        "props": {
            "旧皮箱": {
                "owner": "林叔",
                "location": "旧火车站",
                "condition": "锁扣损坏",
            }
        },
        "scene_location": "旧火车站",
        "story_time": "1986年冬夜",
        "weather": "大雪",
    }


def confirmation_payload(proposal: dict, *, guardian_approval: bool = False) -> dict:
    return {
        "reviewed_script_revision": proposal["script_revision"],
        "proposal_sha256": proposal["proposal_sha256"],
        "reviewed_state": proposal["state"],
        "unresolved_hooks": proposal["unresolved_hooks"],
        "confirmed_by": "本人",
        "spoken_confirmation": "我确认这个结尾交接卡",
        "review_channel": "voice_and_visual",
        "guardian_approval": guardian_approval,
    }


def test_approved_script_metadata_becomes_reviewable_confirmed_handoff(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    plan = create_plan(api)
    first, second = plan["episodes"]
    approve_script(
        api,
        first["id"],
        narrative_metadata={
            "ending_continuity": ending_state(),
            "ending_unresolved_hooks": ["父亲的信还没有打开"],
        },
    )

    proposal_response = api.get(
        f"/v1/episodes/{first['id']}/continuity-extraction-proposal"
    )
    assert proposal_response.status_code == 200
    proposal = proposal_response.json()
    assert proposal["source"] == "approved_script_metadata"
    assert proposal["state"]["characters"]["林叔"]["location"] == "旧火车站"
    assert proposal["unresolved_hooks"] == ["父亲的信还没有打开"]
    assert "characters.林叔" in proposal["extracted_paths"]
    assert len(proposal["proposal_sha256"]) == 64
    assert "待确认草稿" in proposal["spoken_summary"]
    assert "旧皮箱" in proposal["spoken_summary"]
    assert "已经和解" in proposal["spoken_summary"]
    assert "父亲留下了一封信" in proposal["spoken_summary"]
    assert "锁扣损坏" in proposal["spoken_summary"]

    confirmed = api.post(
        f"/v1/episodes/{first['id']}/continuity-extraction-confirmations",
        json=confirmation_payload(proposal),
    )
    assert confirmed.status_code == 201
    result = confirmed.json()
    assert result["snapshot"]["state"] == proposal["state"]
    assert result["approval"]["action_type"] == "continuity_extraction_confirmed"
    assert result["approval"]["script_revision"] == proposal["script_revision"]
    inherited = api.get(f"/v1/episodes/{second['id']}/inherited-continuity").json()
    assert inherited["snapshot"]["id"] == result["snapshot"]["id"]

    duplicate = api.post(
        f"/v1/episodes/{first['id']}/continuity-extraction-confirmations",
        json=confirmation_payload(proposal),
    )
    assert duplicate.status_code == 409
    assert "already has" in duplicate.text

    backup = api.get(f"/v1/projects/{plan['project']['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v9"
    confirmation_record = backup["payload"][
        "continuity_extraction_confirmation_records"
    ][0]
    assert confirmation_record["approval_id"] == result["approval"]["id"]
    assert confirmation_record["snapshot_id"] == result["snapshot"]["id"]
    assert confirmation_record["proposal_sha256"] == proposal["proposal_sha256"]
    assert confirmation_record["review_channel"] == "voice_and_visual"
    assert confirmation_record["change_summary"] == ""
    restored_api = TestClient(
        create_app(tmp_path / "restored.sqlite3", tmp_path / "restored-data")
    )
    restored = restored_api.post("/v1/project-imports", json=backup)
    assert restored.status_code == 201
    restored_snapshots = restored_api.get(
        f"/v1/episodes/{first['id']}/continuity-snapshots"
    ).json()
    restored_approvals = restored_api.get(
        f"/v1/episodes/{first['id']}/script-approvals"
    ).json()
    assert restored_snapshots[0]["id"] == result["snapshot"]["id"]
    assert any(
        record["action_type"] == "continuity_extraction_confirmed"
        for record in restored_approvals
    )
    restored_backup = restored_api.get(
        f"/v1/projects/{plan['project']['id']}/export"
    ).json()
    assert restored_backup["payload"][
        "continuity_extraction_confirmation_records"
    ] == backup["payload"]["continuity_extraction_confirmation_records"]


def test_extraction_is_fail_closed_for_unapproved_missing_and_stale_proposals(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    plan = create_plan(api)
    episode = plan["episodes"][0]
    unapproved = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    )
    assert unapproved.status_code == 409
    approve_script(api, episode["id"])
    missing = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    )
    assert missing.status_code == 409
    assert "no extractable ending continuity" in missing.text

    api.post(
        f"/v1/episodes/{episode['id']}/scripts/1/revoke",
        json={"requested_by": "本人", "reason": "补充结尾状态"},
    )
    approve_script(
        api,
        episode["id"],
        narrative_metadata={"ending_continuity": ending_state()},
    )
    proposal = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    ).json()
    stale = confirmation_payload(proposal)
    stale["proposal_sha256"] = "0" * 64
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/continuity-extraction-confirmations",
        json=stale,
    )
    assert blocked.status_code == 409
    assert "changed after" in blocked.text


def test_explicit_script_markers_are_extracted_without_free_form_inference(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    episode = create_plan(api)["episodes"][0]
    approve_script(
        api,
        episode["id"],
        content="""尾声：列车驶离。
【结尾地点】：杭州旧火车站
【结尾时间】：1986 年冬夜
【结尾天气】：大雪
【未解悬念】：父亲的信没有打开、姐姐是否会回来
""",
    )
    proposal = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    ).json()
    assert proposal["source"] == "approved_script_markers"
    assert proposal["state"]["scene_location"] == "杭州旧火车站"
    assert proposal["state"]["story_time"] == "1986 年冬夜"
    assert proposal["unresolved_hooks"] == ["父亲的信没有打开", "姐姐是否会回来"]


def test_unstructured_legacy_final_scene_becomes_evidence_bound_proposal(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    episode = create_plan(api)["episodes"][0]
    approve_script(
        api,
        episode["id"],
        content="""第一幕：1980年夏天，林叔站在北京车站，窗外下着大雨。
尾声
1986年冬夜，夜里下起大雪。
林叔站在杭州旧火车站。林叔穿着蓝色外套，林叔提着旧皮箱。
林叔的左手缠着绷带。林叔终于知道了父亲留下了一封信。
姐姐是否会回来？信里的秘密仍是个谜。""",
    )

    response = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    )
    assert response.status_code == 200
    proposal = response.json()
    assert proposal["source"] == "approved_script_semantic"
    assert proposal["state"]["scene_location"] == "杭州旧火车站"
    assert proposal["state"]["story_time"] == "1986年冬夜"
    assert proposal["state"]["weather"] == "大雪"
    character = proposal["state"]["characters"]["林叔"]
    assert character["location"] == "杭州旧火车站"
    assert character["wardrobe"] == ["蓝色外套"]
    assert character["held_props"] == ["旧皮箱"]
    assert character["injuries"] == ["左手缠着绷带"]
    assert character["revealed_facts"] == ["父亲留下了一封信"]
    assert proposal["state"]["props"]["旧皮箱"] == {
        "owner": "林叔",
        "location": "杭州旧火车站",
        "condition": None,
    }
    assert proposal["unresolved_hooks"] == [
        "姐姐是否会回来",
        "信里的秘密仍是个谜",
    ]
    evidence_paths = {item["path"] for item in proposal["evidence"]}
    assert {
        "scene_location",
        "story_time",
        "weather",
        "characters.林叔.location",
        "characters.林叔.wardrobe",
        "characters.林叔.held_props",
        "characters.林叔.injuries",
        "characters.林叔.revealed_facts",
        "props.旧皮箱.owner",
        "unresolved_hooks",
    } <= evidence_paths
    assert all(item["excerpt"] for item in proposal["evidence"])
    assert "北京车站" not in str(proposal["state"])
    assert "大雨" not in str(proposal["state"])

    confirmed = api.post(
        f"/v1/episodes/{episode['id']}/continuity-extraction-confirmations",
        json=confirmation_payload(proposal),
    )
    assert confirmed.status_code == 201
    assert confirmed.json()["snapshot"]["state"] == proposal["state"]


def test_semantic_extraction_rejects_ambiguous_mentions_and_dialogue_questions(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    episode = create_plan(api)["episodes"][0]
    approve_script(
        api,
        episode["id"],
        content="""尾声
林叔说：“我们也许在旧火车站，也许已经回家。你吃饭了吗？”
镜头慢慢变黑。""",
    )
    response = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    )
    assert response.status_code == 409
    assert "safe to propose" in response.text


def test_user_edits_require_explanation_and_child_confirmation_requires_guardian(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    plan = create_plan(api, audience_mode="child")
    episode = plan["episodes"][0]
    approve_script(
        api,
        episode["id"],
        narrative_metadata={"ending_continuity": ending_state()},
        guardian_approval=True,
    )
    proposal = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    ).json()
    edited = confirmation_payload(proposal)
    edited["reviewed_state"]["weather"] = "小雪"
    no_guardian = api.post(
        f"/v1/episodes/{episode['id']}/continuity-extraction-confirmations",
        json=edited,
    )
    assert no_guardian.status_code == 409
    assert "guardian" in no_guardian.text
    edited["guardian_approval"] = True
    no_summary = api.post(
        f"/v1/episodes/{episode['id']}/continuity-extraction-confirmations",
        json=edited,
    )
    assert no_summary.status_code == 409
    assert "change summary" in no_summary.text
    edited["change_summary"] = "孩子和监护人核对后，把天气从大雪改为小雪"
    accepted = api.post(
        f"/v1/episodes/{episode['id']}/continuity-extraction-confirmations",
        json=edited,
    )
    assert accepted.status_code == 201
    assert accepted.json()["snapshot"]["state"]["weather"] == "小雪"
    backup = api.get(f"/v1/projects/{plan['project']['id']}/export").json()
    record = backup["payload"]["continuity_extraction_confirmation_records"][0]
    assert record["guardian_approval"] == 1
    assert record["change_summary"] == edited["change_summary"]


def test_ambiguous_confirmation_language_is_rejected(tmp_path: Path) -> None:
    api = client(tmp_path)
    episode = create_plan(api)["episodes"][0]
    approve_script(
        api,
        episode["id"],
        narrative_metadata={"ending_continuity": ending_state()},
    )
    proposal = api.get(
        f"/v1/episodes/{episode['id']}/continuity-extraction-proposal"
    ).json()
    payload = confirmation_payload(proposal)
    payload["spoken_confirmation"] = "看起来差不多"
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/continuity-extraction-confirmations",
        json=payload,
    )
    assert blocked.status_code == 422
