"""Reuse approved creative work after a library-only, immutable snapshot refresh."""

from pydantic import BaseModel, ConfigDict, Field

from .repository import ConflictError, encode, new_id, utc_now
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest


class ShotPlanInheritanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_run_id: str = Field(min_length=1, max_length=160)
    source_event_id: str = Field(min_length=1, max_length=160)
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ShotPlanInheritanceService:
    def __init__(self, repository):
        self.repository = repository

    def inherit(self, run_id, request: ShotPlanInheritanceRequest):
        repo = self.repository
        request_sha = digest(request.model_dump())
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            target, source = repo.get_run(run_id), repo.get_run(request.source_run_id)
            if (source.id == target.id or source.episode_id != target.episode_id
                    or source.project_id != target.project_id or source.season_id != target.season_id
                    or source.status not in {"preflight", "waiting_for_approval"}):
                raise ConflictError("inheritance requires distinct preflight snapshots of the same episode")
            planner = ShotPlanningService(repo)
            package = planner._package(target)
            old_package = planner.read_immutable_package(source)
            if package["package_sha256"] != request.expected_package_sha256:
                raise ConflictError("target production snapshot changed")
            # Only the confirmed library can change. Do not carry approvals across
            # different scripts, assets, permissions, continuity or spending policies.
            omitted = {"package_sha256", "resolved_library"}
            if ({k: v for k, v in package.items() if k not in omitted}
                    != {k: v for k, v in old_package.items() if k not in omitted}):
                raise ConflictError("only confirmed library changes permit shot-plan inheritance")
            if package.get("resolved_library", []) != repo.resolved_project_library(target.project_id):
                raise ConflictError("confirmed project library changed; prepare a current snapshot")
            current = ShotReviewService(repo).current(source.id)
            if (current is None or current.id != request.source_event_id
                    or current.event_type != "shot_plan_approved"):
                raise ConflictError("source shot approval is no longer current")
            payload = current.payload
            if (payload.get("approved") is not True
                    or payload.get("plan_sha256") != request.expected_plan_sha256
                    or digest({k: v for k, v in payload.items() if k != "plan_sha256"}) != request.expected_plan_sha256
                    or payload.get("production_package_sha256") != old_package["package_sha256"]):
                raise ConflictError("source shot-plan integrity failed")
            episode = repo.get_episode(target.episode_id)
            script = package.get("approved_script", {})
            if (episode.approved_script_revision != script.get("revision")
                    or payload.get("script_revision") != episode.approved_script_revision
                    or package.get("episode", {}).get("id") != episode.id):
                raise ConflictError("approved script changed")
            saved_script = repo.get_script(episode.id, episode.approved_script_revision)
            if not saved_script.approved_at or saved_script.content != script.get("content"):
                raise ConflictError("approved script content changed")
            existing = ShotReviewService(repo).current(target.id)
            if existing is not None:
                if (existing.payload.get("inheritance_request_sha256") == request_sha
                        and existing.payload.get("plan_sha256") == digest({
                            k: v for k, v in existing.payload.items() if k != "plan_sha256"})):
                    return existing
                raise ConflictError("target already has a creative plan; do not overwrite it")
            # Local preparation/price reservations count as downstream work too.
            # An allowlist makes future unknown work fail closed, not silently reset.
            allowed = {"run_created", "shot_plan_drafted", "shot_plan_revised", "shot_plan_approved",
                       "shot_character_library_prepared"}
            for identity in (source.id, target.id):
                if any(event.event_type not in allowed for event in repo.list_run_events(identity)):
                    raise ConflictError("downstream work exists; reconcile it before snapshot inheritance")
                if db.execute("SELECT 1 FROM remote_task_bindings WHERE run_id=? LIMIT 1", (identity,)).fetchone():
                    raise ConflictError("provider tasks cannot be copied to another snapshot")
            plan = ShotPlan.model_validate(payload["plan"])
            tasks = planner.tasks_for_plan(plan, episode, script, package.get("inherited_assets", []))
            for task in tasks:
                task["state"] = "awaiting_entry_frame"
            record = {"plan": plan.model_dump(), "tasks": tasks, "approved": True,
                      "production_package_sha256": package["package_sha256"],
                      "script_revision": episode.approved_script_revision,
                      "source_run_id": source.id, "source_event_id": current.id,
                      "source_plan_sha256": request.expected_plan_sha256,
                      "source_package_sha256": old_package["package_sha256"],
                      "inheritance_request_sha256": request_sha,
                      "reviewed_by": payload.get("reviewed_by"), "confirmation": payload.get("confirmation"),
                      "frames_generated": False, "generation_performed": False, "paid_approved": False}
            record["plan_sha256"] = digest(record)
            identity, now = new_id("evt"), utc_now()
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (identity, run_id, sequence, "shot_plan_approved", None, None,
                        "Preserved reviewed creative work on a library-only snapshot; no provider tasks copied.", encode(record), now))
        return repo.get_run_event(identity)
