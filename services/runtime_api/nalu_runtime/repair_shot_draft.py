"""Carry creative content into a repair draft, never production authority."""

from .repository import ConflictError, encode, new_id, utc_now
from .shot_plan_inheritance import ShotPlanInheritanceRequest
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest


def repair_shot_draft_context(production, run_id):
    """Resolve immutable identifiers for the native client, never raw local paths."""
    repo = production.repository
    target = repo.get_run(run_id)
    package = ShotPlanningService(repo)._package(target)
    source_id = package.get("production_policy", {}).get("repair_lineage", {}).get("source_run_id")
    if not source_id:
        raise ConflictError("this run is not a repair version")
    source = repo.get_run(source_id)
    if (source.project_id, source.season_id, source.episode_id) != (target.project_id, target.season_id, target.episode_id):
        raise ConflictError("repair source belongs to another episode")
    original = ShotReviewService(repo).current(source_id)
    if original is None or original.event_type != "shot_plan_approved":
        raise ConflictError("original reviewed shot plan is unavailable")
    return ShotPlanInheritanceRequest(source_run_id=source_id, source_event_id=original.id,
        expected_plan_sha256=original.payload["plan_sha256"], expected_package_sha256=package["package_sha256"])


def prepare_repair_shot_draft(production, run_id, request):
    repo = production.repository
    with repo.db.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        target = repo.get_run(run_id)
        source = repo.get_run(request.source_run_id)
        package = ShotPlanningService(repo)._package(target)
        old = ShotPlanningService.read_immutable_package(source)
        lineage = package.get("production_policy", {}).get("repair_lineage", {})
        repair = production.postproduction_repair_plan(source.id)
        if (source.id == target.id or source.status != "qa_review"
                or (source.project_id, source.season_id, source.episode_id)
                != (target.project_id, target.season_id, target.episode_id)
                or lineage.get("source_run_id") != source.id
                or lineage.get("repair_plan_sha256") != repair.plan_sha256
                or lineage.get("output_seal_sha256") != repair.output_seal_sha256
                or package["package_sha256"] != request.expected_package_sha256
                or old.get("approved_script") != package.get("approved_script")):
            raise ConflictError("repair source or approved script changed")
        original = ShotReviewService(repo).current(source.id)
        if (original is None or original.id != request.source_event_id
                or original.event_type != "shot_plan_approved"
                or original.payload.get("approved") is not True
                or original.payload.get("plan_sha256") != request.expected_plan_sha256
                or original.payload.get("plan_sha256") != digest({
                    k: v for k, v in original.payload.items() if k != "plan_sha256"})
                or original.payload.get("production_package_sha256") != old["package_sha256"]):
            raise ConflictError("original creative plan is unavailable or changed")
        request_sha = digest(request.model_dump())
        existing = ShotReviewService(repo).current(target.id)
        if existing is not None:
            if (existing.event_type == "shot_plan_drafted"
                    and existing.payload.get("repair_draft_request_sha256") == request_sha
                    and existing.payload.get("plan_sha256") == digest({
                        k: v for k, v in existing.payload.items() if k != "plan_sha256"})):
                return existing
            raise ConflictError("repair already has creative work; do not overwrite it")
        if any(e.event_type != "run_created" for e in repo.list_run_events(target.id)):
            raise ConflictError("repair downstream work already exists")
        if db.execute("SELECT 1 FROM remote_task_bindings WHERE run_id=? LIMIT 1", (target.id,)).fetchone():
            raise ConflictError("repair already has provider tasks")
        plan = ShotPlan.model_validate(original.payload["plan"])
        episode = repo.get_episode(target.episode_id)
        script = package["approved_script"]
        saved = repo.get_script(episode.id, episode.approved_script_revision)
        if (script.get("revision") != episode.approved_script_revision
                or not saved.approved_at or saved.content != script.get("content")
                or sum(shot.duration_seconds for shot in plan.shots) != episode.target_seconds):
            raise ConflictError("repair script or duration changed")
        tasks = ShotPlanningService.tasks_for_plan(plan, episode, script, package.get("inherited_assets", []))
        payload = {"plan": plan.model_dump(), "tasks": tasks,
                   "production_package_sha256": package["package_sha256"],
                   "script_revision": episode.approved_script_revision,
                   "source_run_id": source.id, "source_event_id": original.id,
                   "repair_draft_request_sha256": request_sha,
                   "repair_plan_sha256": repair.plan_sha256,
                   "approved": False, "frames_generated": False,
                   "generation_performed": False, "paid_approved": False}
        payload["plan_sha256"] = digest(payload)
        event_id = new_id("evt")
        sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
        db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (
            event_id, run_id, sequence, "shot_plan_drafted", None, None,
            "Original creative plan retained as unapproved repair draft; no provider authority copied.",
            encode(payload), utc_now()))
    return repo.get_run_event(event_id)
