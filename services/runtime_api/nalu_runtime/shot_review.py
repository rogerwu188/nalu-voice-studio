"""Local, version-bound shot review. Creative confirmation is not spending approval."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .repository import ConflictError, Repository, encode, new_id, utc_now
from .shot_planning import ShotPlan, ShotPlanningService
from .video_preparation import digest

PLAN_EVENTS = {"shot_plan_drafted", "shot_plan_revised", "shot_plan_approved"}


class ShotReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["revise", "approve"]
    plan: ShotPlan | None = None
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_explicit_edit(self):
        if (self.action == "revise") != (self.plan is not None):
            raise ValueError("revisions need a plan; approval must use the exact saved plan")
        return self


class ShotReviewService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def current(self, run_id):
        events = [event for event in self.repository.list_run_events(run_id) if event.event_type in PLAN_EVENTS]
        return events[-1] if events else None

    def review(self, run_id: str, source_id: str, request: ShotReviewRequest):
        request_sha = digest({"source_id": source_id, "request": request.model_dump()})
        event_id, now = new_id("evt"), utc_now()
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = self.repository.get_run(run_id)
            planner = ShotPlanningService(self.repository)
            package = planner._package(run)
            events = db.execute("SELECT * FROM run_events WHERE run_id = ? ORDER BY sequence", (run_id,)).fetchall()
            plans = [row for row in events if row["event_type"] in PLAN_EVENTS]
            if not plans:
                raise ConflictError("no saved shot plan to review")
            latest = plans[-1]
            payload = json.loads(latest["payload_json"])
            plan_sha = digest({k: v for k, v in payload.items() if k != "plan_sha256"})
            if plan_sha != payload.get("plan_sha256"):
                raise ConflictError("saved shot plan integrity failed")
            episode = self.repository.get_episode(run.episode_id)
            script = package.get("approved_script", {})
            if (payload.get("production_package_sha256") != package.get("package_sha256")
                    or payload.get("script_revision") != episode.approved_script_revision
                    or script.get("revision") != episode.approved_script_revision
                    or package.get("episode", {}).get("id") != episode.id
                    or package.get("episode", {}).get("target_seconds") != episode.target_seconds):
                raise ConflictError("episode or package changed; review the current episode")
            saved_script = self.repository.get_script(episode.id, episode.approved_script_revision)
            if not saved_script.approved_at or saved_script.content != script.get("content"):
                raise ConflictError("approved script no longer matches")
            # A restart can replay only the current identical review, never an obsolete one.
            if payload.get("review_request_sha256") == request_sha:
                return self.repository.get_run_event(latest["id"])
            if latest["id"] != source_id or plan_sha != request.expected_plan_sha256:
                raise ConflictError("shot plan changed; reload before confirming")
            if any(row["event_type"] in {"video_estimate_reserved", "video_task_prepared",
                                        "image_submit_intent", "image_submit_unconfirmed",
                                        "image_task_submitted"} for row in events):
                raise ConflictError("shot preparation has started; reconcile downstream tasks before changing the plan")
            if db.execute("SELECT 1 FROM remote_task_bindings WHERE run_id = ? LIMIT 1", (run_id,)).fetchone():
                raise ConflictError("provider task exists; do not overwrite its creative source")
            plan = request.plan if request.action == "revise" else ShotPlan.model_validate(payload["plan"])
            tasks = planner.tasks_for_plan(plan, episode, script, package.get("inherited_assets", []))
            approved = request.action == "approve"
            for task in tasks:
                task["state"] = "awaiting_entry_frame" if approved else "awaiting_plan_review_and_frame"
            record = {"plan": plan.model_dump(), "tasks": tasks, "source_event_id": source_id,
                      "source_plan_sha256": plan_sha, "review_request_sha256": request_sha,
                      "reviewed_by": request.reviewed_by, "confirmation": request.confirmation,
                      "production_package_sha256": package["package_sha256"],
                      "script_revision": episode.approved_script_revision,
                      "approved": approved, "frames_generated": False,
                      "generation_performed": False, "paid_approved": False}
            record["plan_sha256"] = digest(record)
            sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (event_id, run_id, sequence, "shot_plan_approved" if approved else "shot_plan_revised",
                        None, None, "Shot plan reviewed locally; no paid generation authorized.", encode(record), now))
        return self.repository.get_run_event(event_id)
