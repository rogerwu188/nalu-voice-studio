from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import (
    AudienceMode,
    ProductionPackage,
    ProductionRun,
    ProductionRunCreate,
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
            self.adapter.preflight(package_path)
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
        return run
