from copy import deepcopy

import pytest
from nalu_runtime.director_draft import DirectorDraft
from nalu_runtime.qingshan_compilers import CAMERA_PROTECTED_FIELDS
from pydantic import ValidationError


def director_fixture():
    return {"camera": {key: "待审阅的创作机位" for key in CAMERA_PROTECTED_FIELDS},
            "state_delta": {"mode": "CHANGE", "dimensions": [{"dimension": "POSTURE", "entry": "低头", "exit": "抬头"}]},
            "props": [], "visible_character_counts": {"grandma": 1}, "combat_or_chase": False,
            "prior_event_relation": "UNKNOWN"}


@pytest.mark.parametrize("invalid", [None, "camera", "bool_count", "zero_count", "hold", "duplicate", "continuation", "qa"])
def test_director_choices_are_bounded_creative_data_not_authorization(invalid):
    data = director_fixture()
    if invalid == "camera":
        data["camera"].pop("lens_intent")
    if invalid in {"bool_count", "zero_count"}:
        data["visible_character_counts"]["grandma"] = True if invalid == "bool_count" else 0
    if invalid == "hold":
        data["state_delta"]["mode"] = "INTENTIONAL_HOLD"
    if invalid == "duplicate":
        data["state_delta"]["dimensions"] *= 2
    if invalid == "continuation":
        data["prior_event_relation"] = "CONTINUING"
    if invalid == "qa":
        data["qa_passed"] = True
    if invalid:
        with pytest.raises(ValidationError):
            DirectorDraft.model_validate(data)
    else:
        draft = DirectorDraft.model_validate(data)
        assert set(draft.camera.model_dump()) == set(CAMERA_PROTECTED_FIELDS)
        assert DirectorDraft.model_validate(draft.model_dump()) == draft
        hold = deepcopy(data)
        hold["state_delta"] = {"mode": "INTENTIONAL_HOLD", "hold_reason": "留出回忆时间",
            "dimensions": [{"dimension": "POSTURE", "entry": "坐着", "exit": "坐着"}]}
        assert DirectorDraft.model_validate(hold).state_delta.hold_reason == "留出回忆时间"
