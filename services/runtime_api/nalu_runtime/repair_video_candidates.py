"""Read validated original clips for repair review; never adopt or submit them."""

from .repair_shot_draft import repair_shot_draft_context
from .repository import ConflictError
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest
from .video_tail import VideoTailService


def same_referenced_assets(shot, source_assets, target_assets):
    """Unrelated later audio uploads must not invalidate an unchanged picture."""
    for identity in shot.reference_asset_ids:
        old = [asset for asset in source_assets if asset.get("id") == identity]
        new = [asset for asset in target_assets if asset.get("id") == identity]
        if len(old) != 1 or len(new) != 1 or old != new:
            return False
    return True


def repair_video_candidates(production, run_id):
    repo = production.repository
    context = repair_shot_draft_context(production, run_id)
    if context is None:
        raise ConflictError("this production is not a repair")
    target = repo.get_run(run_id)
    package = ShotPlanningService(repo)._package(target)
    original = repo.get_run_event(context.source_event_id)
    source = repo.get_run(context.source_run_id)
    old_package = ShotPlanningService.read_immutable_package(source)
    repair = production.postproduction_repair_plan(source.id)
    lineage = package["production_policy"]["repair_lineage"]
    if (source.status != "qa_review"
            or lineage.get("repair_plan_sha256") != repair.plan_sha256
            or lineage.get("output_seal_sha256") != repair.output_seal_sha256
            or old_package.get("approved_script") != package.get("approved_script")
            or original.payload.get("production_package_sha256") != old_package["package_sha256"]):
        raise ConflictError("repair source changed")
    current = ShotReviewService(repo).current(run_id)
    if (current is None or current.payload.get("plan_sha256") != digest({
            k: v for k, v in current.payload.items() if k != "plan_sha256"})
            or current.payload.get("production_package_sha256") != package["package_sha256"]):
        raise ConflictError("repair creative plan is unavailable")
    try:
        target_plan = ShotPlan.model_validate(current.payload.get("plan"))
        source_plan = ShotPlan.model_validate(original.payload.get("plan"))
        shots, old_shots = target_plan.shots, source_plan.shots
    except ValueError:
        raise ConflictError("repair creative plan is invalid") from None
    events = repo.list_run_events(source.id)
    items = []
    for index, shot in enumerate(shots):
        item = {"shot_index": index, "status": "needs_new_video", "requires_review": True}
        # Match exact position and creative content; do not guess reordered shots.
        if index >= len(old_shots) or shot != old_shots[index]:
            item["reason"] = "creative_shot_changed"
        elif (source_plan.visual_assets != target_plan.visual_assets
              or not same_referenced_assets(shot, old_package.get("inherited_assets", []),
                                            package.get("inherited_assets", []))):
            item["reason"] = "asset_snapshot_changed"
        else:
            tasks = [t for t in original.payload.get("tasks", []) if t.get("shot_index") == index]
            reviews = [] if len(tasks) != 1 else [e for e in events
                if e.event_type == "video_shot_reviewed" and e.payload.get("task_key") == tasks[0]["task_key"]]
            if not reviews:
                item["reason"] = "no_original_adopted_video"
            else:
                try:
                    review, media, _ = VideoTailService(repo, production.data_root).accepted_video(
                        source.id, reviews[-1].id, _repair_target=run_id)
                    if (review.payload.get("approved_plan_event_id") != original.id
                            or review.payload.get("approved_plan_sha256") != original.payload["plan_sha256"]):
                        raise ConflictError("original video belongs to another creative plan")
                except ConflictError:
                    item["reason"] = "original_video_no_longer_valid"
                else:
                    item.update(status="available_for_review", source_run_id=source.id,
                        source_review_id=review.id, source_review_sha256=review.payload["review_sha256"],
                        materialization_id=media.id, video_sha256=media.payload["video"]["sha256"])
        items.append(item)
    result = {"run_id": run_id, "source_run_id": source.id,
              "plan_event_id": current.id, "plan_sha256": current.payload["plan_sha256"],
              "items": items, "adopted": False, "generation_performed": False}
    result["candidates_sha256"] = digest(result)
    return result
