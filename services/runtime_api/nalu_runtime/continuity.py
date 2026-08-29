from __future__ import annotations

from typing import Any

from .models import (
    ContinuityConflict,
    ContinuityPreflightRequest,
    ContinuityPreflightResult,
    ContinuitySnapshot,
    ContinuityState,
)


def _append_if_changed(
    conflicts: list[ContinuityConflict],
    path: str,
    inherited: Any,
    proposed: Any,
) -> None:
    if isinstance(proposed, list) and isinstance(inherited, list):
        changed = sorted(proposed) != sorted(inherited)
    else:
        changed = proposed != inherited
    if inherited is not None and changed:
        conflicts.append(
            ContinuityConflict(
                path=path,
                inherited_value=inherited,
                proposed_value=proposed,
            )
        )


def _raw_conflicts(
    inherited: ContinuityState, proposed: ContinuityState
) -> list[ContinuityConflict]:
    conflicts: list[ContinuityConflict] = []
    for field in ("scene_location", "story_time", "weather"):
        _append_if_changed(
            conflicts,
            field,
            getattr(inherited, field),
            getattr(proposed, field),
        )

    for character_id, previous in inherited.characters.items():
        opening = proposed.characters.get(character_id)
        if opening is None:
            conflicts.append(
                ContinuityConflict(
                    path=f"characters.{character_id}",
                    inherited_value=previous.model_dump(mode="json", exclude_none=True),
                    proposed_value=None,
                )
            )
            continue
        for field in ("location", "wardrobe", "injuries", "held_props"):
            _append_if_changed(
                conflicts,
                f"characters.{character_id}.{field}",
                getattr(previous, field),
                getattr(opening, field),
            )
        if previous.relationships is not None:
            if opening.relationships is None:
                conflicts.append(
                    ContinuityConflict(
                        path=f"characters.{character_id}.relationships",
                        inherited_value=previous.relationships,
                        proposed_value=None,
                    )
                )
            else:
                for person_id, relationship in previous.relationships.items():
                    _append_if_changed(
                        conflicts,
                        f"characters.{character_id}.relationships.{person_id}",
                        relationship,
                        opening.relationships.get(person_id),
                    )
        if previous.revealed_facts is not None:
            if opening.revealed_facts is None:
                conflicts.append(
                    ContinuityConflict(
                        path=f"characters.{character_id}.revealed_facts",
                        inherited_value=previous.revealed_facts,
                        proposed_value=None,
                    )
                )
            else:
                missing = sorted(set(previous.revealed_facts) - set(opening.revealed_facts))
                if missing:
                    conflicts.append(
                        ContinuityConflict(
                            path=f"characters.{character_id}.revealed_facts",
                            inherited_value=previous.revealed_facts,
                            proposed_value=opening.revealed_facts,
                        )
                    )

    for prop_id, previous in inherited.props.items():
        opening = proposed.props.get(prop_id)
        if opening is None:
            conflicts.append(
                ContinuityConflict(
                    path=f"props.{prop_id}",
                    inherited_value=previous.model_dump(mode="json", exclude_none=True),
                    proposed_value=None,
                )
            )
            continue
        for field in ("owner", "location", "condition"):
            _append_if_changed(
                conflicts,
                f"props.{prop_id}.{field}",
                getattr(previous, field),
                getattr(opening, field),
            )
    return conflicts


def audit_continuity(
    inherited_snapshot: ContinuitySnapshot | None,
    request: ContinuityPreflightRequest,
) -> ContinuityPreflightResult:
    if inherited_snapshot is None:
        return ContinuityPreflightResult(
            can_proceed=True,
            explanation="no earlier episode continuity snapshot exists",
        )

    conflicts = _raw_conflicts(inherited_snapshot.state, request.opening_state)
    override_paths = set(request.override.conflict_paths) if request.override else set()
    actual_paths = {conflict.path for conflict in conflicts}
    if request.override and override_paths != actual_paths:
        return ContinuityPreflightResult(
            inherited_snapshot_id=inherited_snapshot.id,
            can_proceed=False,
            conflicts=conflicts,
            explanation=(
                "continuity override paths must exactly match the current conflicts; "
                "review the latest inherited state"
            ),
        )

    blocked = False
    resolved: list[ContinuityConflict] = []
    for conflict in conflicts:
        explanation = request.transition_explanations.get(conflict.path, "").strip()
        overridden = conflict.path in override_paths
        if not explanation and not overridden:
            blocked = True
        resolved.append(
            conflict.model_copy(
                update={"explanation": explanation, "overridden": overridden}
            )
        )
    if not conflicts:
        message = "opening state is consistent with the previous episode"
    elif blocked:
        message = "unexplained continuity conflicts block production"
    else:
        message = "all continuity changes are explained or explicitly overridden"
    return ContinuityPreflightResult(
        inherited_snapshot_id=inherited_snapshot.id,
        can_proceed=not blocked,
        conflicts=resolved,
        explanation=message,
    )
