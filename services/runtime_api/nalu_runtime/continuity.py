from __future__ import annotations

from typing import Any

from .models import (
    ContinuityConflict,
    ContinuityHookReview,
    ContinuityPreflightRequest,
    ContinuityPreflightResult,
    ContinuitySnapshot,
    ContinuityState,
)


def audit_hook_review(
    inherited_snapshot: ContinuitySnapshot,
    review: ContinuityHookReview | None,
) -> tuple[str, str]:
    inherited_hooks = inherited_snapshot.unresolved_hooks
    if not inherited_hooks:
        return "not_required", ""
    if review is None:
        return "missing", "every inherited unresolved hook requires an explicit review"
    if review.inherited_snapshot_id != inherited_snapshot.id:
        return "stale", "hook review targets a stale inherited snapshot"
    reviewed_hooks = {item.hook for item in review.resolutions}
    if reviewed_hooks != set(inherited_hooks):
        return "incomplete", "hook review must cover exactly the inherited unresolved hooks"
    return "accepted", ""


def ending_hooks_match_review(
    inherited_snapshot: ContinuitySnapshot | None,
    review: ContinuityHookReview | None,
    ending_hooks: list[str],
) -> tuple[bool, str]:
    if inherited_snapshot is None or not inherited_snapshot.unresolved_hooks:
        return True, ""
    status, message = audit_hook_review(inherited_snapshot, review)
    if status != "accepted" or review is None:
        return False, message
    ending = set(ending_hooks)
    for resolution in review.resolutions:
        remains = resolution.hook in ending
        if resolution.disposition == "carry_forward" and not remains:
            return False, f"carried-forward hook is missing from the ending: {resolution.hook}"
        if resolution.disposition != "carry_forward" and remains:
            return False, f"closed hook remains unresolved at the ending: {resolution.hook}"
    return True, ""


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
    hook_status, hook_message = audit_hook_review(
        inherited_snapshot, request.hook_review
    )
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

    blocked = hook_status not in {"not_required", "accepted"}
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
    if hook_message:
        message = hook_message
    elif not conflicts:
        message = "opening state is consistent with the previous episode"
    elif blocked:
        message = "unexplained continuity conflicts block production"
    else:
        message = "all continuity changes are explained or explicitly overridden"
    return ContinuityPreflightResult(
        inherited_snapshot_id=inherited_snapshot.id,
        can_proceed=not blocked,
        conflicts=resolved,
        hook_review_status=hook_status,
        hook_resolutions=request.hook_review.resolutions if request.hook_review else [],
        explanation=message,
    )
