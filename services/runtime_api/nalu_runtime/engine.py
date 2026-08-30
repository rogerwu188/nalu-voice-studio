from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .continuity import audit_continuity
from .models import (
    AudienceMode,
    ContinuityPreflightRequest,
    EpisodeProductionProgress,
    EpisodeStatus,
    EpisodeTransitionRequest,
    ProductionPackage,
    ProductionRun,
    ProductionRunCreate,
    RenderedOutputArtifact,
    RenderedOutputIntegrityReport,
    RenderedOutputSeal,
    RenderedOutputSealCreate,
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

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _canonical_sha256(value: dict | list) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _run_directory(self, run: ProductionRun) -> Path:
        run_directory = Path(run.package_path).resolve().parent
        runs_root = (self.data_root / "runs").resolve()
        if not run_directory.is_relative_to(runs_root):
            raise ConflictError("production run package is outside the managed data root")
        return run_directory

    def seal_rendered_outputs(
        self, run_id: str, request: RenderedOutputSealCreate
    ) -> RenderedOutputSeal:
        run = self.repository.get_run(run_id)
        if run.status != RunStatus.QA_REVIEW:
            raise ConflictError("rendered outputs can only be sealed during QA review")
        run_directory = self._run_directory(run)
        package_path = Path(run.package_path)
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConflictError("production package is unreadable before output seal") from exc
        package_hash = package.get("package_sha256", "")
        package_body = {key: value for key, value in package.items() if key != "package_sha256"}
        if not package_hash or self._canonical_sha256(package_body) != package_hash:
            raise ConflictError("production package integrity check failed before output seal")

        workspace = run_directory / "qingshan-workspace"
        exports_root = (workspace / "exports").resolve()
        workspace_manifest = workspace / "workspace-manifest.json"
        if not workspace_manifest.is_file():
            raise ConflictError("Qingshan workspace manifest is missing")

        artifacts: list[RenderedOutputArtifact] = []
        for candidate in request.artifacts:
            unresolved_path = exports_root / candidate.relative_path
            artifact_path = unresolved_path.resolve()
            if (
                not artifact_path.is_relative_to(exports_root)
                or not artifact_path.is_file()
                or unresolved_path.is_symlink()
            ):
                raise ConflictError(
                    "rendered output must be a regular file inside Qingshan exports: "
                    + candidate.relative_path
                )
            byte_size = artifact_path.stat().st_size
            if byte_size < 1:
                raise ConflictError("rendered output is empty: " + candidate.relative_path)
            artifacts.append(
                RenderedOutputArtifact(
                    **candidate.model_dump(),
                    sha256=self._sha256_file(artifact_path),
                    byte_size=byte_size,
                )
            )
        artifacts.sort(key=lambda artifact: artifact.relative_path)

        seal_without_hash = {
            "schema_version": "nalu.rendered-output-seal/v1",
            "run_id": run.id,
            "project_id": run.project_id,
            "episode_id": run.episode_id,
            "production_package_sha256": package_hash,
            "resolved_library_sha256": self._canonical_sha256(
                package.get("resolved_library", [])
            ),
            "workspace_manifest_sha256": self._sha256_file(workspace_manifest),
            "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
            "sealed_by": request.sealed_by,
            "sealed_at": utc_now(),
        }
        seal = RenderedOutputSeal(
            **seal_without_hash,
            manifest_sha256=self._canonical_sha256(seal_without_hash),
        )
        seal_path = run_directory / "rendered-output-seal.json"
        temporary_path = run_directory / f".{new_id('output-seal')}.tmp"
        temporary_path.write_text(seal.model_dump_json(indent=2) + "\n", encoding="utf-8")
        secure_file(temporary_path)
        try:
            os.link(temporary_path, seal_path)
        except FileExistsError as exc:
            raise ConflictError("rendered outputs are already sealed for this run") from exc
        finally:
            temporary_path.unlink(missing_ok=True)
        secure_file(seal_path)
        for artifact in artifacts:
            secure_file(exports_root / artifact.relative_path)
        self.repository.append_run_event(
            run.id,
            "rendered_outputs_sealed",
            from_status=run.status,
            to_status=run.status,
            message="Rendered outputs were sealed for release-blocking QA.",
            payload={
                "manifest_path": str(seal_path),
                "manifest_sha256": seal.manifest_sha256,
                "artifact_count": len(artifacts),
            },
        )
        return seal

    def rendered_output_integrity(self, run_id: str) -> RenderedOutputIntegrityReport:
        run = self.repository.get_run(run_id)
        run_directory = self._run_directory(run)
        seal_path = run_directory / "rendered-output-seal.json"
        if not seal_path.is_file():
            raise ConflictError("rendered outputs have not been sealed for this run")
        try:
            seal = RenderedOutputSeal.model_validate_json(
                seal_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError("rendered output seal is unreadable or invalid") from exc
        failures: list[str] = []
        seal_body = seal.model_dump(mode="json", exclude={"manifest_sha256"})
        if self._canonical_sha256(seal_body) != seal.manifest_sha256:
            failures.append("output seal manifest digest mismatch")

        package_path = Path(run.package_path)
        if not package_path.is_file():
            failures.append("production package is missing")
        else:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package_body = {
                key: value for key, value in package.items() if key != "package_sha256"
            }
            if (
                package.get("package_sha256") != seal.production_package_sha256
                or self._canonical_sha256(package_body) != seal.production_package_sha256
            ):
                failures.append("production package digest mismatch")
            if (
                self._canonical_sha256(package.get("resolved_library", []))
                != seal.resolved_library_sha256
            ):
                failures.append("resolved library snapshot digest mismatch")

        workspace = run_directory / "qingshan-workspace"
        workspace_manifest = workspace / "workspace-manifest.json"
        if (
            not workspace_manifest.is_file()
            or self._sha256_file(workspace_manifest) != seal.workspace_manifest_sha256
        ):
            failures.append("workspace manifest digest mismatch")
        exports_root = (workspace / "exports").resolve()
        for artifact in seal.artifacts:
            unresolved_path = exports_root / artifact.relative_path
            artifact_path = unresolved_path.resolve()
            if (
                not artifact_path.is_relative_to(exports_root)
                or not artifact_path.is_file()
                or unresolved_path.is_symlink()
            ):
                failures.append("rendered output is missing: " + artifact.relative_path)
            elif (
                artifact_path.stat().st_size != artifact.byte_size
                or self._sha256_file(artifact_path) != artifact.sha256
            ):
                failures.append("rendered output digest mismatch: " + artifact.relative_path)
        return RenderedOutputIntegrityReport(
            seal=seal,
            integrity_ok=not failures,
            failures=failures,
        )

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
        resolved_library = self.repository.resolved_project_library(project.id)
        continuity = self.repository.latest_continuity(season.id, episode.episode_number)
        policy = self._model_policy()

        continuity_preflight = None
        if continuity is not None:
            metadata = script.narrative_metadata
            if "opening_continuity" not in metadata:
                raise ConflictError(
                    "an opening_continuity declaration is required when an earlier "
                    "episode has an end-state snapshot"
                )
            try:
                preflight_request = ContinuityPreflightRequest.model_validate(
                    {
                        "opening_state": metadata["opening_continuity"],
                        "transition_explanations": metadata.get(
                            "continuity_transition_explanations", {}
                        ),
                        "override": metadata.get("continuity_override"),
                        "hook_review": metadata.get("continuity_hook_review"),
                    }
                )
            except ValueError as exc:
                raise ConflictError(f"invalid continuity metadata: {exc}") from exc
            if (
                project.audience_mode == AudienceMode.CHILD
                and preflight_request.hook_review is not None
                and not preflight_request.hook_review.guardian_approval
            ):
                raise ConflictError("child hook review requires guardian approval")
            continuity_preflight = audit_continuity(continuity, preflight_request)
            if not continuity_preflight.can_proceed:
                paths = ", ".join(
                    conflict.path for conflict in continuity_preflight.conflicts
                    if not conflict.explanation and not conflict.overridden
                )
                detail = paths or continuity_preflight.explanation
                raise ConflictError("continuity preflight blocked: " + detail)

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
            resolved_library=resolved_library,
            continuity=continuity.model_dump(mode="json") if continuity else None,
            continuity_preflight=(
                continuity_preflight.model_dump(mode="json")
                if continuity_preflight else None
            ),
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
            package.model_dump_json(indent=2) + "\n", encoding="utf-8"
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
