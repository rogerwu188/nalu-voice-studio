from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import (
    AudienceMode,
    ProductionPackage,
    ProductionRun,
    ProductionRunCreate,
    RunActionRequest,
    RunEvent,
    RunResumeRequest,
    RunStatus,
)
from .qingshan_adapter import QingshanAdapter, QingshanAdapterError
from .repository import ConflictError, Repository, new_id, utc_now


class ProductionService:
    def __init__(self, repository: Repository, data_root: Path, repository_root: Path):
        self.repository = repository
        self.data_root = data_root
        self.repository_root = repository_root
        self.adapter = QingshanAdapter(repository_root)

    def _model_policy(self) -> dict:
        policy_path = self.repository_root / "configs" / "model-policy.json"
        return json.loads(policy_path.read_text(encoding="utf-8"))

    def start_run(self, episode_id: str, request: ProductionRunCreate) -> ProductionRun:
        episode = self.repository.get_episode(episode_id)
        if episode.approved_script_revision is None:
            raise ConflictError("an approved episode script is required before production")

        season = self.repository.get_season(episode.season_id)
        project = self.repository.get_project(season.project_id)
        script = self.repository.get_script(episode.id, episode.approved_script_revision)
        assets = self.repository.list_assets(project.id, episode.id)
        continuity = self.repository.latest_continuity(season.id, episode.episode_number)
        policy = self._model_policy()

        if request.requested_model not in policy["allowed_video_models"]:
            raise ConflictError(
                f"model {request.requested_model!r} is not allowed by policy {policy['policy_version']}"
            )

        if project.audience_mode == AudienceMode.CHILD:
            missing_guardian = [
                asset.id
                for asset in assets
                if asset.kind in {"character_image", "voice_reference"}
                and not asset.guardian_approved
            ]
            if missing_guardian:
                raise ConflictError(
                    "child projects require guardian approval for biometric assets: "
                    + ", ".join(missing_guardian)
                )

        package = ProductionPackage(
            project=project.model_dump(mode="json"),
            season=season.model_dump(mode="json"),
            episode=episode.model_dump(mode="json"),
            approved_script=script.model_dump(mode="json"),
            inherited_assets=[asset.model_dump(mode="json") for asset in assets],
            continuity=continuity.model_dump(mode="json") if continuity else None,
            production_policy={
                "model_policy": policy,
                "requested_model": request.requested_model,
                "dry_run": request.dry_run,
                "paid_generation_approved": request.paid_generation_approved,
                "approved_by": request.approved_by,
                "estimated_budget_credits": request.estimated_budget_credits,
                "paid_submitter_required": True,
                "release_fail_closed": True,
            },
        )
        canonical = package.model_dump(mode="json", exclude={"package_sha256"})
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        package.package_sha256 = hashlib.sha256(encoded.encode()).hexdigest()

        run_id, now = new_id("run"), utc_now()
        run_dir = self.data_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        package_path = run_dir / "production-package.json"
        package_path.write_text(
            package.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )

        try:
            workspace = self.adapter.materialize_workspace(package_path)
            self.adapter.preflight(package_path, workspace)
        except QingshanAdapterError as exc:
            raise ConflictError(f"Qingshan preflight failed: {exc}") from exc

        # Paid execution remains deliberately disabled until the imported durable
        # submitter is bound to this versioned package contract.
        status = RunStatus.PREFLIGHT if request.dry_run else RunStatus.WAITING_FOR_APPROVAL
        run = ProductionRun(
            id=run_id,
            project_id=project.id,
            season_id=season.id,
            episode_id=episode.id,
            status=status,
            dry_run=request.dry_run,
            requested_model=request.requested_model,
            estimated_budget_credits=request.estimated_budget_credits,
            package_path=str(package_path),
            created_at=now,
            updated_at=now,
        )
        self.repository.save_run(run)
        self.repository.append_run_event(
            run.id,
            "run_created",
            to_status=run.status,
            message="Immutable production package created and Qingshan preflight passed.",
            payload={"package_path": run.package_path, "dry_run": run.dry_run},
        )
        return run

    def cancel_run(self, run_id: str, request: RunActionRequest) -> ProductionRun:
        run = self.repository.get_run(run_id)
        if run.status in {RunStatus.COMPLETED, RunStatus.CANCELLED}:
            raise ConflictError(f"run in {run.status} cannot be cancelled")
        updated = self.repository.update_run_status(run_id, RunStatus.CANCELLED)
        self.repository.append_run_event(
            run_id,
            "run_cancelled",
            from_status=run.status,
            to_status=RunStatus.CANCELLED,
            message=request.reason,
            payload={"requested_by": request.requested_by},
        )
        return updated

    def resume_run(self, run_id: str, request: RunResumeRequest) -> ProductionRun:
        run = self.repository.get_run(run_id)
        if run.status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ConflictError("only failed or cancelled runs may be resumed")
        target = RunStatus.PREFLIGHT if request.resume_from_preflight else RunStatus.QUEUED
        if target == RunStatus.QUEUED and not run.dry_run:
            raise ConflictError("paid runs must resume through preflight")
        package_path = Path(run.package_path)
        workspace = self.adapter.materialize_workspace(package_path)
        self.adapter.preflight(package_path, workspace)
        updated = self.repository.update_run_status(run_id, target, error=None)
        self.repository.append_run_event(
            run_id,
            "run_resumed",
            from_status=run.status,
            to_status=target,
            message=request.reason,
            payload={"requested_by": request.requested_by},
        )
        return updated

    def events(self, run_id: str) -> list[RunEvent]:
        return self.repository.list_run_events(run_id)
