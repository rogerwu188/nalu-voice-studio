"""Refresh an unstarted run's immutable library snapshot, without another run."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .qingshan_adapter import QingshanAdapterError
from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory
from .shot_planning import ShotPlan, ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest


class LibrarySnapshotRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_id: str = Field(min_length=1, max_length=160)
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_library_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LibrarySnapshotRefreshService:
    def __init__(self, production):
        self.production = production
        self.repository = production.repository

    def preview(self, run_id):
        repo = self.repository
        run = repo.get_run(run_id)
        package = ShotPlanningService(repo)._package(run)
        current = ShotReviewService(repo).current(run_id)
        if current is None or current.event_type != "shot_plan_approved" or current.payload.get("approved") is not True:
            raise ConflictError("confirm the current shot plan first")
        payload = current.payload
        if (payload.get("plan_sha256") != digest({k: v for k, v in payload.items() if k != "plan_sha256"})
                or payload.get("production_package_sha256") != package["package_sha256"]):
            raise ConflictError("current shot plan or package binding changed")
        library = repo.resolved_project_library(run.project_id)
        return {"run_id": run_id, "refresh_required": package.get("resolved_library", []) != library,
                "request": {"source_event_id": current.id, "expected_plan_sha256": payload["plan_sha256"],
                    "expected_package_sha256": package["package_sha256"], "expected_library_sha256": digest(library)}}

    def refresh(self, run_id, request: LibrarySnapshotRefreshRequest):
        repo = self.repository
        request_sha = digest(request.model_dump())
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            planner = ShotPlanningService(repo)
            package = planner._package(run)
            current = ShotReviewService(repo).current(run_id)
            library = repo.resolved_project_library(run.project_id)
            if digest(library) != request.expected_library_sha256:
                raise ConflictError("confirmed library changed; read back the current people first")
            if current is None:
                raise ConflictError("confirm the shot plan before refreshing its library")
            payload = current.payload
            if (payload.get("plan_sha256") != digest({k: v for k, v in payload.items() if k != "plan_sha256"})
                    or payload.get("production_package_sha256") != package["package_sha256"]):
                raise ConflictError("current plan integrity or package binding changed")
            if payload.get("library_refresh_request_sha256") == request_sha:
                return current
            if (current.id != request.source_event_id or current.event_type != "shot_plan_approved"
                    or payload.get("approved") is not True
                    or payload["plan_sha256"] != request.expected_plan_sha256
                    or package["package_sha256"] != request.expected_package_sha256):
                raise ConflictError("refresh requires the exact current approved shot plan and package")
            allowed = {"run_created", "shot_plan_drafted", "shot_plan_revised", "shot_plan_approved",
                       "shot_character_library_prepared"}
            if any(event.event_type not in allowed for event in repo.list_run_events(run_id)):
                raise ConflictError("production preparation already started; do not reset its snapshot")
            if db.execute("SELECT 1 FROM remote_task_bindings WHERE run_id=? LIMIT 1", (run_id,)).fetchone():
                raise ConflictError("provider tasks already bind this snapshot")
            episode = repo.get_episode(run.episode_id)
            script = package.get("approved_script", {})
            if (episode.approved_script_revision != script.get("revision")
                    or payload.get("script_revision") != episode.approved_script_revision
                    or package.get("episode", {}).get("id") != episode.id):
                raise ConflictError("approved episode changed")
            saved_script = repo.get_script(episode.id, episode.approved_script_revision)
            if not saved_script.approved_at or saved_script.content != script.get("content"):
                raise ConflictError("approved script content changed")
            plan = ShotPlan.model_validate(payload["plan"])
            tasks = planner.tasks_for_plan(plan, episode, script, package.get("inherited_assets", []))
            for task in tasks:
                task["state"] = "awaiting_entry_frame"
            if package.get("resolved_library", []) == library:
                return current
            refreshed = {**package, "resolved_library": library}
            refreshed["package_sha256"] = digest({k: v for k, v in refreshed.items() if k != "package_sha256"})
            # Keep the original bytes/workspace. Every retry uses the same path;
            # only a complete, fsynced and preflighted snapshot becomes current.
            root = self.production.data_root / "runs" / run_id
            if root.is_symlink():
                raise ConflictError("unsafe run directory")
            folder = root / ("library-snapshot-" + request_sha)
            if folder.is_symlink():
                raise ConflictError("unsafe snapshot directory")
            secure_directory(folder)
            target = folder / "production-package.json"
            staging = folder / ".production-package.pending"
            encoded = json.dumps(refreshed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            try:
                if target.exists() or target.is_symlink():
                    self._verify_file(target, encoded)
                elif staging.exists() or staging.is_symlink():
                    self._verify_file(staging, encoded)
                    os.replace(staging, target)
                    self.production._sync_directory(folder)
                else:
                    self.production._write_and_promote_package(staging, target, encoded)
                workspace = self.production.adapter.materialize_workspace(target)
                self.production.adapter.preflight(target, workspace)
            except (OSError, ValueError, QingshanAdapterError) as exc:
                raise ConflictError("library snapshot preflight failed; original production context retained") from exc
            record = {**payload, "tasks": tasks, "production_package_sha256": refreshed["package_sha256"],
                      "source_event_id": current.id, "source_plan_sha256": payload["plan_sha256"],
                      "source_package_sha256": package["package_sha256"],
                      "source_package_path": run.package_path,
                      "library_refresh_request_sha256": request_sha,
                      "frames_generated": False, "generation_performed": False, "paid_approved": False}
            record.pop("plan_sha256", None)
            # Previous mutation receipts remain in the source event, not as
            # replay authority for this different current package/plan version.
            record.pop("review_request_sha256", None)
            record.pop("inheritance_request_sha256", None)
            record["plan_sha256"] = digest(record)
            identity, now = new_id("evt"), utc_now()
            db.execute("UPDATE production_runs SET package_path=?, updated_at=? WHERE id=?", (str(target), now, run_id))
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (identity, run_id, sequence, "shot_plan_approved", None, None,
                        "Confirmed library refreshed with original plan preserved; no generation performed.", encode(record), now))
        return repo.get_run_event(identity)

    @staticmethod
    def _verify_file(path: Path, encoded: str):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000 or path.read_text() != encoded:
            raise ValueError("staged snapshot is not the expected immutable content")
