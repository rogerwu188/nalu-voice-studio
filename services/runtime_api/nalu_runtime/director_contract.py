"""Compile reviewed creative choices, without manufacturing visual or paid authority."""

from copy import deepcopy

from .director_draft import DirectorDraft
from .qingshan_compilers import _canonical_sha256
from .repository import ConflictError


def compile_director_fields(director: DirectorDraft, shot_index: int) -> dict:
    camera = director.camera.model_dump()
    delta = director.state_delta.model_dump(exclude_none=True)
    if "hold_reason" in delta:
        delta["writer_authored_hold_reason"] = delta.pop("hold_reason")
    result = {
        "camera_plan": camera,
        "camera_authority": {"selection_mode": "LOCKED", "authored_protected_fields": deepcopy(camera),
                             "protected_fields_sha256": _canonical_sha256(camera), "auto_filled_fields": []},
        "combat_or_chase": director.combat_or_chase,
        "shot_state_delta_contract": delta,
        "visible_prop_ids": [prop.design_key for prop in director.props],
        "prop_state_contracts": [
            {"prop_id": prop.design_key, "entry": prop.entry.model_dump(), "exit": prop.exit.model_dump(),
             "writer_authored_transition": True, "transition_description": prop.transition_description}
            for prop in director.props],
        "episode_scene_role": "FIRST_SCENE" if shot_index == 0 else "OTHER_SCENE",
    }
    if shot_index == 0:
        # UNKNOWN remains unknown, rather than inventing an earlier episode event.
        result["prior_episode_event_relation"] = director.prior_event_relation
        if director.prior_event_relation == "CONTINUING":
            result["writer_authored_continuation_action"] = director.continuation_action
            result["event_motion_class"] = "CONTINUING_ACTION"
    return result


def apply_reviewed_director(request: dict, director: DirectorDraft, shot_index: int) -> None:
    """Populate missing creative fields; reject attempts to override reviewed choices.

    Called only after the runtime validates the exact current approved plan.
    Independent prop-image confirmation is carried through, never generated here.
    Build a copy before mutation so a conflict cannot leave a half-compiled request.
    """
    fields = compile_director_fields(director, shot_index)
    supplied_props = request.get("prop_state_contracts")
    if supplied_props is not None:
        if not isinstance(supplied_props, list) or len(supplied_props) != len(fields["prop_state_contracts"]):
            raise ConflictError("prop contract differs from the reviewed director choices")
        for expected, supplied in zip(fields["prop_state_contracts"], supplied_props, strict=True):
            if not isinstance(supplied, dict) or any(supplied.get(key) != value for key, value in expected.items()):
                raise ConflictError("prop contract differs from the reviewed director choices")
            if "start_frame_visual_confirmation" in supplied:
                expected["start_frame_visual_confirmation"] = deepcopy(supplied["start_frame_visual_confirmation"])
    for key, value in fields.items():
        if key in request and request[key] != value:
            raise ConflictError(f"{key} differs from the reviewed director choices")
    request.update(deepcopy(fields))
