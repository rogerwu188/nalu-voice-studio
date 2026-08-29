from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import (
    AudienceMode,
    EpisodeProductionProgress,
    EpisodeStatus,
    EpisodeTransitionRequest,
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
from .secure_files import harden_tree, secure_directory, secure_file

EPISODE_PROGRESS = {
    EpisodeStatus.PLANNED: ("planning", 0, "等待完善分集规划", "这一集还在规划中。"),
    EpisodeStatus.SCRIPT_DRAFT: ("script", 10, "正在撰写剧本", "剧本正在形成初稿。"),
    EpisodeStatus.SCRIPT_REVIEW: ("script_review", 15, "等待确认剧本", "请检查并确认本集剧本。"),
    EpisodeStatus.SCRIPT_APPROVED: ("ready", 20, "可以进入制作", "本集剧本已确认。"),
    EpisodeStatus.PREPRODUCTION: ("preproduction", 30, "正在准备制作", "素材和生产包正在预检。"),
    EpisodeStatus.GENERATING: ("generation", 60, "正在生成镜头", "专业生产线正在生成本集。"),
    EpisodeStatus.POSTPRODUCTION: ("postproduction", 80, "正在后期制作", "画面、声音和字幕正在合成。"),
    EpisodeStatus.QA_REVIEW: ("qa", 90, "正在质量检查", "本集正在通过发布前检查。"),
    EpisodeStatus.READY_TO_PUBLISH: ("ready_to_publish", 100, "成片待发行", "本集成片已经准备好。"),
    EpisodeStatus.PUBLISHED: ("published", 100, "已经发行", "本集已经完成发行。"),
    EpisodeStatus.BLOCKED: ("blocked", 0, "需要处理问题", "本集已暂停，等待解决阻塞问题。"),
}

RUN_PROGRESS = {
    RunStatus.CREATED: ("package", 25, "正在创建生产包", "正在整理已批准的剧本和素材。"),
    RunStatus.PREFLIGHT: ("preflight", 30, "预检已通过", "生产包已通过本地预检。"),
    RunStatus.WAITING_FOR_APPROVAL: (
        "approval",
        35,
        "等待付费授权",
        "未获得明确授权前不会调用付费服务。",
    ),
    RunStatus.QUEUED: ("queued", 40, "等待生产", "任务已经安全进入生产队列。"),
    RunStatus.RUNNING: ("generation", 60, "正在生成", "专业生产线正在处理本集。"),
    RunStatus.QA_REVIEW: ("qa", 90, "正在质量检查", "正在检查本集成片。"),
    RunStatus.COMPLETED: ("completed", 100, "制作完成", "本集制作已经完成。"),
    RunStatus.FAILED: ("failed", 0, "制作遇到问题", "任务已停止，可查看原因后恢复。"),
    RunStatus.CANCELLED: ("cancelled", 0, "已经取消", "任务已安全取消，可以从检查点恢复。"),
}


class ProductionService:
    def __init__(self, repository: Repository, data_root: Path, repository_root: Path):
        self.repository = repository
        self.data_root = data_root.resolve()
        secure_directory(self.data_root)
        self.repository_root = repository_root
        self.adapter = QingshanAdapter(repository_root)

    def _model_policy(self) -> dict:
        policy_path = self.repository_root / "configs" / "model-policy.json"
        return json.loads(policy_path.read_text(encoding="utf-8"))

    def start_run(
        self,
        episode_id: str,
        request: ProductionRunCreate,
        idempotency_key: str | None = None,
    ) -> ProductionRun:
        episode = self.repository.get_episode(episode_id)
        if episode.approved_script_revision is None:
            raise ConflictError("an approved episode script is required before production")
        if not request.dry_run and not idempotency_key:
            raise ConflictError("paid production requires an Idempotency-Key header")

        season = self.repository.get_season(episode.season_id)
        project = self.repository.get_project(season.project_id)
        if project.production_pipeline != "qingshan-short-drama":
            raise ConflictError(
                "this project has no approved production adapter; choose a supported pipeline"
            )
        script = self.repository.get_script(episode.id, episode.approved_script_revision)
        assets = self.repository.list_assets(project.id, episode.id)
        continuity = self.repository.latest_continuity(season.id, episode.episode_number)
        policy = self._model_policy()

        if request.requested_model not in policy["allowed_video_models"]:
            raise ConflictError(
                f"model {request.requested_model!r} is not allowed by policy {policy['policy_version']}"
            )

        revoked_biometrics = [
            asset.id
            for asset in assets
            if asset.kind in {"character_image", "voice_reference"}
            and not asset.consent_granted
        ]
        if revoked_biometrics:
            raise ConflictError(
                "biometric consent is missing or revoked: " + ", ".join(revoked_biometrics)
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

        run_id = new_id("run")
        operation_scope = f"production-run:{episode_id}"
        if idempotency_key:
            request_payload = json.dumps(
                {"episode_id": episode_id, "request": request.model_dump(mode="json")},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            request_sha = hashlib.sha256(request_payload.encode()).hexdigest()
            run_id, claim_status = self.repository.claim_operation(
                operation_scope, idempotency_key, request_sha, run_id
            )
            if claim_status == "completed":
                return self.repository.get_run(run_id)
            if claim_status == "pending":
                raise ConflictError("the idempotent production request is still in progress")
            if claim_status == "failed":
                raise ConflictError("the prior production request failed; inspect its evidence")

        if episode.status != EpisodeStatus.SCRIPT_APPROVED:
            if idempotency_key:
                self.repository.finish_operation(
                    operation_scope,
                    idempotency_key,
                    "failed",
                    f"episode in {episode.status} cannot start a new production run",
                )
            raise ConflictError(f"episode in {episode.status} cannot start a new production run")

        package = ProductionPackage(
            project=project.model_dump(mode="json"),
            season=season.model_dump(mode="json"),
            episode=episode.model_dump(mode="json"),
            approved_script=script.model_dump(mode="json"),
            inherited_assets=[
                asset.model_dump(
                    mode="json", exclude={"consent_granted_by", "consent_statement"}
                )
                for asset in assets
            ],
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

        now = utc_now()
        run_dir = self.data_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        secure_directory(run_dir)
        package_path = run_dir / "production-package.json"
        package_path.write_text(
            package.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8"
        )
        secure_file(package_path)

        try:
            workspace = self.adapter.materialize_workspace(package_path)
            self.adapter.preflight(package_path, workspace)
        except QingshanAdapterError as exc:
            if idempotency_key:
                self.repository.finish_operation(
                    operation_scope, idempotency_key, "failed", str(exc)
                )
            raise ConflictError(f"Qingshan preflight failed: {exc}") from exc
        finally:
            harden_tree(run_dir)

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
        self.repository.bind_run_assets(run.id, assets)
        self.repository.append_run_event(
            run.id,
            "run_created",
            to_status=run.status,
            message="Immutable production package created and Qingshan preflight passed.",
            payload={"package_path": run.package_path, "dry_run": run.dry_run},
        )
        self.repository.transition_episode(
            episode.id,
            EpisodeTransitionRequest(
                target_status=EpisodeStatus.PREPRODUCTION,
                requested_by="production-service",
                reason=f"production run {run.id} passed preflight",
            ),
        )
        if idempotency_key:
            self.repository.finish_operation(operation_scope, idempotency_key, "completed")
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

    def episode_progress(self, episode_id: str) -> EpisodeProductionProgress:
        episode = self.repository.get_episode(episode_id)
        run = self.repository.latest_run_for_episode(episode_id)
        stage, percent, action, explanation = EPISODE_PROGRESS[episode.status]
        if run is not None:
            stage, percent, action, explanation = RUN_PROGRESS[run.status]
            if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
                percent = EPISODE_PROGRESS[episode.status][1]
        return EpisodeProductionProgress(
            episode_id=episode.id,
            episode_number=episode.episode_number,
            title=episode.title,
            episode_status=episode.status,
            run_id=run.id if run else None,
            run_status=run.status if run else None,
            stage=stage,
            progress_percent=percent,
            current_action=action,
            explanation=run.error if run and run.error else explanation,
            can_cancel=bool(
                run
                and run.status
                in {
                    RunStatus.CREATED,
                    RunStatus.PREFLIGHT,
                    RunStatus.WAITING_FOR_APPROVAL,
                    RunStatus.QUEUED,
                    RunStatus.RUNNING,
                    RunStatus.QA_REVIEW,
                }
            ),
            can_resume=bool(
                run and run.status in {RunStatus.FAILED, RunStatus.CANCELLED}
            ),
            updated_at=run.updated_at if run else episode.updated_at,
        )

    def season_progress(self, season_id: str) -> list[EpisodeProductionProgress]:
        return [
            self.episode_progress(episode.id)
            for episode in self.repository.list_season_episodes(season_id)
        ]
