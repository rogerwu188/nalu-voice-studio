"""Explicitly promote a local preflight without discarding its approved story/plan.

This is not a provider submission or a per-task cost approval. Those gates remain
mandatory; an uncertain provider attempt must never be reset by this transition.
"""

import json
import os

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .library_snapshot_refresh import LibrarySnapshotRefreshService
from .qingshan_adapter import QingshanAdapterError
from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest


class ProductionAuthorizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_id: str = Field(min_length=1, max_length=160)
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed_run_budget_credits: int = Field(strict=True, gt=0)
    approved_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)
    guardian_approval: bool = Field(default=False, strict=True)

    @field_validator("approved_by", "confirmation")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("explicit approval cannot be blank")
        return value.strip()


class ProductionAuthorizationService:
    def __init__(self, production):
        self.production = production
        self.repository = production.repository

    def authorize(self, run_id, request: ProductionAuthorizationRequest):
        repo = self.repository
        request_sha = digest(request.model_dump())
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            package = ShotPlanningService(repo)._package(run)
            current = ShotReviewService(repo).current(run_id)
            if current is None:
                raise ConflictError("confirm the shot plan before authorizing production")
            payload = current.payload
            if (payload.get("plan_sha256") != digest({k: v for k, v in payload.items() if k != "plan_sha256"})
                    or payload.get("production_package_sha256") != package["package_sha256"]):
                raise ConflictError("current plan integrity or package binding changed")
            policy = package.get("production_policy", {})
            # Durable replay is read-only, even when a later image task exists.
            if payload.get("production_authorization_request_sha256") == request_sha:
                if (run.dry_run or run.estimated_budget_credits != request.confirmed_run_budget_credits
                        or policy.get("production_authorization_request_sha256") != request_sha
                        or policy.get("paid_generation_approved") is not True):
                    raise ConflictError("production authorization requires reconciliation")
                return current
            if (not run.dry_run or run.status != "preflight" or policy.get("dry_run") is not True
                    or current.id != request.source_event_id or current.event_type != "shot_plan_approved"
                    or payload.get("approved") is not True
                    or payload["plan_sha256"] != request.expected_plan_sha256
                    or package["package_sha256"] != request.expected_package_sha256):
                raise ConflictError("authorization requires the exact current approved dry-run plan")
            project = repo.get_project(run.project_id)
            if project.audience_mode == "child" and not request.guardian_approval:
                raise ConflictError("guardian approval is required for child production")
            if package.get("resolved_library", []) != repo.resolved_project_library(run.project_id):
                raise ConflictError("refresh the confirmed character/library snapshot first")
            allowed = {"run_created", "shot_plan_drafted", "shot_plan_revised", "shot_plan_approved",
                       "shot_character_library_prepared", "image_task_prepared"}
            if any(e.event_type not in allowed for e in repo.list_run_events(run_id)):
                raise ConflictError("production or cost approval already started; do not reset its authority")
            if db.execute("SELECT 1 FROM remote_task_bindings WHERE run_id=? LIMIT 1", (run_id,)).fetchone():
                raise ConflictError("provider tasks already bind this snapshot")
            episode = repo.get_episode(run.episode_id)
            script = package.get("approved_script", {})
            if (episode.approved_script_revision != script.get("revision")
                    or payload.get("script_revision") != episode.approved_script_revision
                    or package.get("episode", {}).get("id") != episode.id):
                raise ConflictError("approved episode changed")
            saved = repo.get_script(episode.id, episode.approved_script_revision)
            if not saved.approved_at or saved.content != script.get("content"):
                raise ConflictError("approved script content changed")
            plan = ShotPlan.model_validate(payload["plan"])
            if sum(shot.duration_seconds for shot in plan.shots) != episode.target_seconds:
                raise ConflictError("approved shot durations no longer match the episode")
            policy = {**policy, "dry_run": False, "paid_generation_approved": True,
                      "approved_by": request.approved_by,
                      "estimated_budget_credits": request.confirmed_run_budget_credits,
                      "production_authorization_request_sha256": request_sha}
            refreshed = {**package, "production_policy": policy}
            refreshed["package_sha256"] = digest({k: v for k, v in refreshed.items() if k != "package_sha256"})
            root = self.production.data_root / "runs" / run_id
            folder = root / ("production-authorization-" + request_sha)
            if root.is_symlink() or folder.is_symlink():
                raise ConflictError("unsafe authorization snapshot directory")
            secure_directory(folder)
            target, staging = folder / "production-package.json", folder / ".production-package.pending"
            encoded = json.dumps(refreshed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            try:
                if target.exists() or target.is_symlink():
                    LibrarySnapshotRefreshService._verify_file(target, encoded)
                elif staging.exists() or staging.is_symlink():
                    LibrarySnapshotRefreshService._verify_file(staging, encoded)
                    os.replace(staging, target)
                    self.production._sync_directory(folder)
                else:
                    self.production._write_and_promote_package(staging, target, encoded)
                workspace = self.production.adapter.materialize_workspace(target)
                self.production.adapter.preflight(target, workspace)
            except (OSError, ValueError, QingshanAdapterError) as exc:
                raise ConflictError("authorization preflight failed; original run and plan retained") from exc
            record = {**payload, "production_package_sha256": refreshed["package_sha256"],
                      "source_event_id": current.id, "source_plan_sha256": payload["plan_sha256"],
                      "source_package_sha256": package["package_sha256"], "source_package_path": run.package_path,
                      "production_authorization_request_sha256": request_sha,
                      "production_authorization": request.model_dump(),
                      "generation_performed": False, "paid_approved": False}
            for key in ("plan_sha256", "review_request_sha256", "inheritance_request_sha256", "library_refresh_request_sha256"):
                record.pop(key, None)
            record["plan_sha256"] = digest(record)
            identity, now = new_id("evt"), utc_now()
            db.execute("""UPDATE production_runs SET package_path=?, dry_run=0,
                       status='waiting_for_approval', estimated_budget_credits=?, updated_at=? WHERE id=?""",
                       (str(target), request.confirmed_run_budget_credits, now, run_id))
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (identity, run_id, sequence, "shot_plan_approved", None, None,
                        "Production authorized; per-task price approval still required; no generation performed.", encode(record), now))
        return repo.get_run_event(identity)
