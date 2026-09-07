from copy import deepcopy

import pytest
from nalu_runtime.director_contract import apply_reviewed_director, compile_director_fields
from nalu_runtime.director_draft import DirectorDraft
from nalu_runtime.qingshan_compilers import _canonical_sha256
from nalu_runtime.repository import ConflictError
from test_director_draft import director_fixture


def test_reviewed_camera_and_state_compile_without_visual_or_spending_claims():
    draft = DirectorDraft.model_validate(director_fixture())
    request = {"prompt": "用户写的拍法"}
    apply_reviewed_director(request, draft, 0)
    assert request["prompt"] == "用户写的拍法"
    assert request["camera_authority"]["selection_mode"] == "LOCKED"
    assert request["camera_authority"]["protected_fields_sha256"] == _canonical_sha256(request["camera_plan"])
    assert request["shot_state_delta_contract"]["dimensions"][0]["exit"] == "抬头"
    assert request["prior_episode_event_relation"] == "UNKNOWN"
    assert not {"opening_anchor", "provider_scope_projection", "paid_approved", "qa_passed"} & request.keys()
    original = deepcopy(request)
    apply_reviewed_director(request, draft, 0)
    assert request == original
    request["camera_plan"]["shot_scale"] = "改成另一个机位"
    before = deepcopy(request)
    with pytest.raises(ConflictError):
        apply_reviewed_director(request, draft, 0)
    assert request == before


def test_prop_confirmation_is_never_invented_and_existing_evidence_is_preserved():
    data = director_fixture()
    data["props"] = [{"design_key": "letter",
        "entry": {"owner": "grandma", "hand": "左手", "position": "身前", "disposition": "握着"},
        "exit": {"owner": "none", "hand": "无", "position": "桌上", "disposition": "放下"},
        "transition_description": "外婆把信放到桌上"}]
    draft = DirectorDraft.model_validate(data)
    result = compile_director_fields(draft, 1)
    assert result["visible_prop_ids"] == ["letter"]
    assert "start_frame_visual_confirmation" not in result["prop_state_contracts"][0]
    assert result["episode_scene_role"] == "OTHER_SCENE"
    result["prop_state_contracts"][0]["start_frame_visual_confirmation"] = {"status": "PENDING"}
    apply_reviewed_director(result, draft, 1)
    assert result["prop_state_contracts"][0]["start_frame_visual_confirmation"] == {"status": "PENDING"}
    result["prop_state_contracts"][0]["entry"]["owner"] = "invented-person"
    with pytest.raises(ConflictError):
        apply_reviewed_director(result, draft, 1)


def test_intentional_hold_and_continuing_story_keep_reviewed_reason():
    data = director_fixture()
    data["state_delta"] = {"mode": "INTENTIONAL_HOLD", "hold_reason": "等待回声",
                           "dimensions": [{"dimension": "POSTURE", "entry": "坐着", "exit": "坐着"}]}
    data["prior_event_relation"] = "CONTINUING"
    data["continuation_action"] = "继续上一集的谈话"
    result = compile_director_fields(DirectorDraft.model_validate(data), 0)
    assert result["shot_state_delta_contract"]["writer_authored_hold_reason"] == "等待回声"
    assert result["writer_authored_continuation_action"] == "继续上一集的谈话"
