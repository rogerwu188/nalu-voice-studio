"""Creative director choices, never visual QA or spending authorization."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class DirectorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CameraDraft(DirectorModel):
    shot_scale: str = Field(min_length=1, max_length=500)
    camera_height: str = Field(min_length=1, max_length=500)
    camera_side: str = Field(min_length=1, max_length=500)
    axis_relation: str = Field(min_length=1, max_length=500)
    motion_family: str = Field(min_length=1, max_length=500)
    motion_direction: str = Field(min_length=1, max_length=500)
    start_framing: str = Field(min_length=1, max_length=500)
    end_framing: str = Field(min_length=1, max_length=500)
    motivation: str = Field(min_length=1, max_length=500)
    lens_intent: str = Field(min_length=1, max_length=500)


class StateDimension(DirectorModel):
    dimension: Literal["POSITION", "POSTURE", "CONTACT", "POSSESSION", "INTEGRITY", "MOMENTUM"]
    entry: str = Field(min_length=1, max_length=1000)
    exit: str = Field(min_length=1, max_length=1000)


class StateDeltaDraft(DirectorModel):
    mode: Literal["CHANGE", "INTENTIONAL_HOLD"]
    dimensions: list[StateDimension] = Field(min_length=1, max_length=6)
    hold_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def coherent_delta(self):
        if len({item.dimension for item in self.dimensions}) != len(self.dimensions):
            raise ValueError("repeated state dimension")
        changed = any(item.entry != item.exit for item in self.dimensions)
        if (self.mode == "CHANGE" and not changed) or (self.mode == "INTENTIONAL_HOLD" and (changed or not self.hold_reason)):
            raise ValueError("state change or intentional hold must be explicit")
        return self


class PropEndpointDraft(DirectorModel):
    owner: str = Field(min_length=1, max_length=160)
    hand: str = Field(min_length=1, max_length=500)
    position: str = Field(min_length=1, max_length=500)
    disposition: str = Field(min_length=1, max_length=500)


class PropDraft(DirectorModel):
    design_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    entry: PropEndpointDraft
    exit: PropEndpointDraft
    transition_description: str = Field(min_length=1, max_length=1000)


class DirectorDraft(DirectorModel):
    camera: CameraDraft
    state_delta: StateDeltaDraft
    props: list[PropDraft] = Field(max_length=12)
    visible_character_counts: dict[str, StrictInt] = Field(max_length=12)
    combat_or_chase: bool = Field(strict=True)
    prior_event_relation: Literal["CONTINUING", "RESOLVED", "ELAPSED", "UNKNOWN"]
    continuation_action: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def coherent_scope(self):
        if any(type(count) is not int or not 1 <= count <= 20 for count in self.visible_character_counts.values()):
            raise ValueError("visible character counts must be positive bounded integers")
        if len({prop.design_key for prop in self.props}) != len(self.props):
            raise ValueError("repeated prop design")
        if self.prior_event_relation == "CONTINUING" and not self.continuation_action:
            raise ValueError("continuation needs an explicit proposed action")
        return self
