from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .continuity import audit_continuity
from .media_structure_qa import inspect_mp4, inspect_webvtt
from .models import (
    AudienceMode,
    ContinuityPreflightRequest,
    EpisodeProductionProgress,
    EpisodeStatus,
    EpisodeTransitionRequest,
    FinalQAEvidence,
    MediaStructureQAReport,
    PlatformPublicationApproval,
    PostproductionRepairPlan,
    PostproductionRepairTask,
    ProductionCompletionRequest,
    ProductionCompletionResult,
    ProductionPackage,
    ProductionRun,
    ProductionRunCreate,
    PublicationDryRun,
    PublicationDryRunCreate,
    ReleasePackage,
    ReleasePackageCreate,
    RemoteTaskState,
    RenderedOutputArtifact,
    RenderedOutputIntegrityReport,
    RenderedOutputSeal,
    RenderedOutputSealCreate,
    RunActionRequest,
    RunEvent,
    RunResumeRequest,
    RunStatus,
)
from .publication_adapters import publication_adapter
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

QA_REPAIR_CATALOG = {
    "output_integrity": (
        "sealed outputs",
        "A sealed output or its production snapshot no longer matches its recorded digest.",
        "Restore the exact sealed files or create a new repair run and seal new outputs.",
    ),
    "master_presence": (
        "master video",
        "Exactly one final master video was not sealed.",
        "Export one normalized final MP4 in a repair run, then seal it as master_video.",
    ),
    "captions_presence": (
        "captions",
        "No release captions were sealed.",
        "Generate, time-check and seal the release captions in a repair run.",
    ),
    "qa_report_presence": (
        "final QA report",
        "Exactly one structured final QA report was not sealed.",
        "Perform original-resolution human review and seal one valid QA report.",
    ),
    "qa_report_contract": (
        "final QA report",
        "The sealed final QA report is unreadable or does not match its schema.",
        "Correct the structured review evidence in a repair run and reseal all outputs.",
    ),
    "qa_run_binding": (
        "final QA report",
        "The QA report belongs to another production run.",
        "Review this run's master and create evidence bound to this exact run ID.",
    ),
    "qa_master_binding": (
        "final QA report",
        "The QA report reviewed a different master digest.",
        "Repeat original-resolution review against this exact master and reseal evidence.",
    ),
    "mp4_structure": (
        "master video",
        "The MP4 container, duration metadata or fast-start layout failed structural QA.",
        "Normalize the final MP4 container and duration metadata, then create a new seal.",
    ),
    "caption_timeline": (
        "captions",
        "The WebVTT format, cue order or master-duration boundary failed QA.",
        "Correct caption format and timestamps against the normalized master, then reseal.",
    ),
    "original_resolution_reviewed": (
        "master video",
        "Original-resolution human review was not completed.",
        "Watch the full original-resolution master without interruption and record review.",
    ),
    "picture_passed": (
        "picture track",
        "Picture, identity, wardrobe, space, pose or prop review failed.",
        "Repair the cited shots, regenerate a master and repeat visual QA.",
    ),
    "audio_sync_passed": (
        "audio mix",
        "Dialogue, ambience, foley, music or synchronization review failed.",
        "Repair the mix or synchronization, regenerate a master and repeat audio QA.",
    ),
    "captions_passed": (
        "captions",
        "Caption text, timing or readability review failed.",
        "Correct caption text and timestamps, then repeat caption QA.",
    ),
    "continuity_passed": (
        "continuity",
        "Identity, wardrobe, space, axis, pose, prop, sound or transition continuity failed.",
        "Repair every cited continuity break and repeat cross-shot/cross-episode review.",
    ),
    "safety_passed": (
        "safety and rights",
        "Safety, consent, rights or release review failed.",
        "Resolve the cited safety or rights issue before creating a new release candidate.",
    ),
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

    def _record_postproduction_repair_plan(
        self,
        run: ProductionRun,
        *,
        output_seal_sha256: str,
        codes: list[str],
        master_sha256: str | None = None,
        source_qa_sha256: str | None = None,
    ) -> PostproductionRepairPlan:
        normalized_codes = sorted(set(codes)) or ["qa_report_contract"]
        tasks = [
            PostproductionRepairTask(
                code=code,
                target=QA_REPAIR_CATALOG.get(code, QA_REPAIR_CATALOG["qa_report_contract"])[0],
                issue=QA_REPAIR_CATALOG.get(code, QA_REPAIR_CATALOG["qa_report_contract"])[1],
                required_action=QA_REPAIR_CATALOG.get(
                    code, QA_REPAIR_CATALOG["qa_report_contract"]
                )[2],
            )
            for code in normalized_codes
        ]
        plan_path = self._run_directory(run) / "postproduction-repair-plan.json"
        if plan_path.is_file():
            try:
                existing = PostproductionRepairPlan.model_validate_json(
                    plan_path.read_text(encoding="utf-8")
                )
                if (
                    self._canonical_sha256(
                        existing.model_dump(mode="json", exclude={"plan_sha256"})
                    )
                    == existing.plan_sha256
                    and existing.output_seal_sha256 == output_seal_sha256
                    and existing.master_sha256 == master_sha256
                    and existing.source_qa_sha256 == source_qa_sha256
                    and [task.code for task in existing.repair_tasks] == normalized_codes
                ):
                    return existing
            except (OSError, ValueError):
                pass
        body = {
            "schema_version": "nalu.postproduction-repair-plan/v1",
            "run_id": run.id,
            "output_seal_sha256": output_seal_sha256,
            "master_sha256": master_sha256,
            "source_qa_sha256": source_qa_sha256,
            "repair_tasks": [task.model_dump(mode="json") for task in tasks],
            "created_at": utc_now(),
        }
        plan = PostproductionRepairPlan(
            **body,
            plan_sha256=self._canonical_sha256(body),
        )
        temporary = plan_path.with_name(f".{new_id('repair-plan')}.tmp")
        temporary.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        secure_file(temporary)
        os.replace(temporary, plan_path)
        secure_file(plan_path)
        self.repository.append_run_event(
            run.id,
            "postproduction_repair_required",
            from_status=run.status,
            to_status=run.status,
            message="Release-blocking QA created specific repair tasks.",
            payload={
                "plan_sha256": plan.plan_sha256,
                "repair_codes": normalized_codes,
            },
        )
        return plan

    def postproduction_repair_plan(self, run_id: str) -> PostproductionRepairPlan:
        run = self.repository.get_run(run_id)
        plan_path = self._run_directory(run) / "postproduction-repair-plan.json"
        if not plan_path.is_file() or plan_path.is_symlink():
            raise ConflictError("this production run has no postproduction repair plan")
        try:
            plan = PostproductionRepairPlan.model_validate_json(
                plan_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError("postproduction repair plan is unreadable or invalid") from exc
        body = plan.model_dump(mode="json", exclude={"plan_sha256"})
        if self._canonical_sha256(body) != plan.plan_sha256:
            raise ConflictError("postproduction repair plan digest mismatch")
        if plan.run_id != run.id:
            raise ConflictError("postproduction repair plan belongs to another run")
        return plan

    def media_structure_qa(self, run_id: str) -> MediaStructureQAReport:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            raise ConflictError(
                "rendered output integrity failed before media QA: "
                + "; ".join(integrity.failures)
            )
        run = self.repository.get_run(run_id)
        seal = integrity.seal
        masters = [artifact for artifact in seal.artifacts if artifact.kind == "master_video"]
        captions = [artifact for artifact in seal.artifacts if artifact.kind == "captions"]
        if len(masters) != 1 or len(captions) != 1:
            raise ConflictError("media structure QA requires exactly one master and captions file")
        exports = self._run_directory(run) / "qingshan-workspace" / "exports"
        master_path = exports / masters[0].relative_path
        captions_path = exports / captions[0].relative_path
        mp4_report = inspect_mp4(master_path)
        captions_report = inspect_webvtt(
            captions_path,
            media_duration_seconds=mp4_report.get("duration_seconds"),
        )
        failures = [
            *("mp4:" + value for value in mp4_report.get("failures") or []),
            *("captions:" + value for value in captions_report.get("failures") or []),
        ]
        report_body = {
            "schema_version": "nalu.media-structure-qa/v1",
            "run_id": run.id,
            "output_seal_sha256": seal.manifest_sha256,
            "master_sha256": masters[0].sha256,
            "captions_sha256": captions[0].sha256,
            "mp4": mp4_report,
            "captions": captions_report,
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "created_at": utc_now(),
        }
        report = MediaStructureQAReport(
            **report_body,
            report_sha256=self._canonical_sha256(report_body),
        )
        report_path = self._run_directory(run) / "media-structure-qa.json"
        if report_path.is_file():
            try:
                existing = MediaStructureQAReport.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                )
                if (
                    self._canonical_sha256(
                        existing.model_dump(mode="json", exclude={"report_sha256"})
                    )
                    == existing.report_sha256
                    and existing.output_seal_sha256 == seal.manifest_sha256
                    and existing.master_sha256 == masters[0].sha256
                    and existing.captions_sha256 == captions[0].sha256
                    and existing.status == report.status
                    and existing.failures == report.failures
                ):
                    return existing
            except (OSError, ValueError):
                pass
        temporary = report_path.with_name(f".{new_id('media-qa')}.tmp")
        temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        secure_file(temporary)
        os.replace(temporary, report_path)
        secure_file(report_path)
        self.repository.append_run_event(
            run.id,
            "media_structure_qa_completed",
            from_status=run.status,
            to_status=run.status,
            message="MP4 container and caption timeline checks completed.",
            payload={
                "status": report.status,
                "report_sha256": report.report_sha256,
                "failure_count": len(failures),
            },
        )
        if failures:
            repair_codes = []
            if mp4_report.get("status") != "PASS":
                repair_codes.append("mp4_structure")
            if captions_report.get("status") != "PASS":
                repair_codes.append("caption_timeline")
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256,
                codes=repair_codes,
            )
        return report

    def stored_media_structure_qa(self, run_id: str) -> MediaStructureQAReport:
        run = self.repository.get_run(run_id)
        report_path = self._run_directory(run) / "media-structure-qa.json"
        if not report_path.is_file() or report_path.is_symlink():
            raise ConflictError("media structure QA has not been recorded for this run")
        try:
            report = MediaStructureQAReport.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError("media structure QA report is unreadable or invalid") from exc
        body = report.model_dump(mode="json", exclude={"report_sha256"})
        if self._canonical_sha256(body) != report.report_sha256:
            raise ConflictError("media structure QA report digest mismatch")
        if report.run_id != run.id:
            raise ConflictError("media structure QA report belongs to another run")
        return report

    def create_release_package(
        self, run_id: str, request: ReleasePackageCreate
    ) -> ReleasePackage:
        run = self.repository.get_run(run_id)
        if run.status != RunStatus.COMPLETED:
            raise ConflictError("only a completed production run can create a release package")
        episode = self.repository.get_episode(run.episode_id)
        if episode.status != EpisodeStatus.READY_TO_PUBLISH:
            raise ConflictError("episode is not ready to create a release package")
        integrity = self.rendered_output_integrity(run.id)
        if not integrity.integrity_ok:
            raise ConflictError("sealed output integrity failed before release packaging")
        media_qa = self.stored_media_structure_qa(run.id)
        if media_qa.status != "PASS":
            raise ConflictError("media structure QA must pass before release packaging")
        if media_qa.output_seal_sha256 != integrity.seal.manifest_sha256:
            raise ConflictError("media structure QA reviewed a different output seal")

        artifacts_by_kind: dict[str, list[RenderedOutputArtifact]] = {}
        for artifact in integrity.seal.artifacts:
            artifacts_by_kind.setdefault(str(artifact.kind), []).append(artifact)
        for required in ("master_video", "captions", "cover"):
            if len(artifacts_by_kind.get(required, [])) != 1:
                raise ConflictError(
                    f"release package requires exactly one sealed {required} artifact"
                )

        release_path = self._run_directory(run) / "release-package.json"
        if release_path.is_file():
            try:
                existing = ReleasePackage.model_validate_json(
                    release_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise ConflictError("existing release package is unreadable or invalid") from exc
            existing_body = existing.model_dump(mode="json", exclude={"manifest_sha256"})
            if self._canonical_sha256(existing_body) != existing.manifest_sha256:
                raise ConflictError("existing release package digest mismatch")
            if (
                existing.output_seal_sha256 == integrity.seal.manifest_sha256
                and existing.media_qa_report_sha256 == media_qa.report_sha256
                and existing.title == request.title
                and existing.description == request.description
                and existing.prepared_by == request.prepared_by
            ):
                return existing
            raise ConflictError("release package already exists with different metadata")

        body = {
            "schema_version": "nalu.release-package/v1",
            "run_id": run.id,
            "project_id": run.project_id,
            "episode_id": run.episode_id,
            "output_seal_sha256": integrity.seal.manifest_sha256,
            "media_qa_report_sha256": media_qa.report_sha256,
            "title": request.title,
            "description": request.description,
            "artifacts": [
                artifact.model_dump(mode="json") for artifact in integrity.seal.artifacts
            ],
            "prepared_by": request.prepared_by,
            "prepared_at": utc_now(),
            "publishing_enabled": False,
            "platform_approvals": [],
        }
        package = ReleasePackage(
            **body,
            manifest_sha256=self._canonical_sha256(body),
        )
        temporary = release_path.with_name(f".{new_id('release-package')}.tmp")
        temporary.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
        secure_file(temporary)
        try:
            os.link(temporary, release_path)
        except FileExistsError as exc:
            raise ConflictError("release package was created concurrently") from exc
        finally:
            temporary.unlink(missing_ok=True)
        secure_file(release_path)
        self.repository.append_run_event(
            run.id,
            "release_package_created",
            from_status=run.status,
            to_status=run.status,
            message="Offline release package created; platform publishing remains disabled.",
            payload={
                "manifest_sha256": package.manifest_sha256,
                "publishing_enabled": False,
            },
        )
        return package

    def stored_release_package(self, run_id: str) -> ReleasePackage:
        run = self.repository.get_run(run_id)
        release_path = self._run_directory(run) / "release-package.json"
        if not release_path.is_file() or release_path.is_symlink():
            raise ConflictError("offline release package has not been created")
        try:
            package = ReleasePackage.model_validate_json(
                release_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError("release package is unreadable or invalid") from exc
        body = package.model_dump(mode="json", exclude={"manifest_sha256"})
        if self._canonical_sha256(body) != package.manifest_sha256:
            raise ConflictError("release package digest mismatch")
        if package.run_id != run.id:
            raise ConflictError("release package belongs to another run")
        integrity = self.rendered_output_integrity(run.id)
        if not integrity.integrity_ok:
            raise ConflictError("sealed output integrity failed after release packaging")
        if package.output_seal_sha256 != integrity.seal.manifest_sha256:
            raise ConflictError("release package references a different output seal")
        return package

    def create_publication_dry_run(
        self, run_id: str, request: PublicationDryRunCreate
    ) -> PublicationDryRun:
        run = self.repository.get_run(run_id)
        episode = self.repository.get_episode(run.episode_id)
        if run.status != RunStatus.COMPLETED or episode.status != EpisodeStatus.READY_TO_PUBLISH:
            raise ConflictError("only completed, ready-to-publish episodes can prepare publishing")
        project = self.repository.get_project(run.project_id)
        if project.audience_mode == AudienceMode.CHILD and not request.guardian_approval:
            raise ConflictError("child publication dry-run requires guardian approval")
        package = self.stored_release_package(run.id)
        try:
            adapter = publication_adapter(request.platform)
            compiled_plan = adapter.compile(package, request.channel_reference)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

        dry_run_path = self._run_directory(run) / f"publication-dry-run-{request.platform}.json"
        if dry_run_path.is_file():
            existing = self.stored_publication_dry_run(run.id, request.platform)
            approval = existing.approval
            if (
                approval.channel_reference == request.channel_reference
                and approval.approved_by == request.approved_by
                and approval.spoken_confirmation == request.spoken_confirmation
                and approval.guardian_approval == request.guardian_approval
                and existing.release_manifest_sha256 == package.manifest_sha256
            ):
                return existing
            raise ConflictError(
                "publication dry-run already exists for this platform with different approval"
            )

        approved_at = utc_now()
        approval_body = {
            "platform": request.platform,
            "channel_reference": request.channel_reference,
            "approved_by": request.approved_by,
            "spoken_confirmation": request.spoken_confirmation,
            "guardian_approval": request.guardian_approval,
            "approved_at": approved_at,
        }
        approval = PlatformPublicationApproval(
            **approval_body,
            approval_sha256=self._canonical_sha256(approval_body),
        )
        duplicate_guard = self._canonical_sha256(
            {
                "run_id": run.id,
                "platform": request.platform,
                "channel_reference": request.channel_reference,
                "release_manifest_sha256": package.manifest_sha256,
            }
        )
        body = {
            "schema_version": "nalu.publication-dry-run/v1",
            "id": new_id("publication-dry-run"),
            "run_id": run.id,
            "project_id": run.project_id,
            "episode_id": run.episode_id,
            "release_manifest_sha256": package.manifest_sha256,
            "platform": request.platform,
            "adapter_version": adapter.version,
            "approval": approval.model_dump(mode="json"),
            "duplicate_guard_sha256": duplicate_guard,
            "compiled_plan": compiled_plan,
            "dry_run": True,
            "network_call_performed": False,
            "episode_state_changed": False,
            "created_at": approved_at,
        }
        dry_run = PublicationDryRun(
            **body,
            plan_sha256=self._canonical_sha256(body),
        )
        temporary = dry_run_path.with_name(f".{new_id('publication-dry-run')}.tmp")
        temporary.write_text(dry_run.model_dump_json(indent=2) + "\n", encoding="utf-8")
        secure_file(temporary)
        try:
            os.link(temporary, dry_run_path)
        except FileExistsError as exc:
            raise ConflictError("publication dry-run was created concurrently") from exc
        finally:
            temporary.unlink(missing_ok=True)
        secure_file(dry_run_path)
        self.repository.append_run_event(
            run.id,
            "publication_dry_run_created",
            from_status=run.status,
            to_status=run.status,
            message="Platform-specific dry-run created; network publishing remained disabled.",
            payload={
                "platform": request.platform,
                "plan_sha256": dry_run.plan_sha256,
                "duplicate_guard_sha256": duplicate_guard,
                "network_call_performed": False,
            },
        )
        return dry_run

    def stored_publication_dry_run(
        self, run_id: str, platform: str
    ) -> PublicationDryRun:
        run = self.repository.get_run(run_id)
        try:
            publication_adapter(platform)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        path = self._run_directory(run) / f"publication-dry-run-{platform}.json"
        if not path.is_file() or path.is_symlink():
            raise ConflictError("publication dry-run has not been created")
        try:
            dry_run = PublicationDryRun.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConflictError("publication dry-run is unreadable or invalid") from exc
        body = dry_run.model_dump(mode="json", exclude={"plan_sha256"})
        if self._canonical_sha256(body) != dry_run.plan_sha256:
            raise ConflictError("publication dry-run digest mismatch")
        approval_body = dry_run.approval.model_dump(
            mode="json", exclude={"approval_sha256"}
        )
        if self._canonical_sha256(approval_body) != dry_run.approval.approval_sha256:
            raise ConflictError("publication approval digest mismatch")
        if dry_run.run_id != run.id or dry_run.platform != platform:
            raise ConflictError("publication dry-run binding mismatch")
        package = self.stored_release_package(run.id)
        if dry_run.release_manifest_sha256 != package.manifest_sha256:
            raise ConflictError("publication dry-run references a different release package")
        return dry_run

    def complete_run(
        self, run_id: str, request: ProductionCompletionRequest
    ) -> ProductionCompletionResult:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            run = self.repository.get_run(run_id)
            master = next(
                (
                    artifact
                    for artifact in integrity.seal.artifacts
                    if artifact.kind == "master_video"
                ),
                None,
            )
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=integrity.seal.manifest_sha256,
                master_sha256=master.sha256 if master else None,
                codes=["output_integrity"],
            )
            raise ConflictError(
                "rendered output integrity failed: " + "; ".join(integrity.failures)
            )
        seal = integrity.seal
        if request.output_seal_sha256 != seal.manifest_sha256:
            raise ConflictError("output seal changed after completion review")
        run = self.repository.get_run(run_id)
        project = self.repository.get_project(run.project_id)
        if project.audience_mode == AudienceMode.CHILD and not request.guardian_approval:
            raise ConflictError("child production completion requires guardian approval")

        qa_artifacts = [artifact for artifact in seal.artifacts if artifact.kind == "qa_report"]
        if len(qa_artifacts) != 1:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                codes=["qa_report_presence"],
            )
            raise ConflictError("production completion requires exactly one sealed QA report")
        master_artifacts = [
            artifact for artifact in seal.artifacts if artifact.kind == "master_video"
        ]
        if len(master_artifacts) != 1:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                codes=["master_presence"],
            )
            raise ConflictError("production completion requires exactly one sealed master")
        if not any(artifact.kind == "captions" for artifact in seal.artifacts):
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=master_artifacts[0].sha256,
                codes=["captions_presence"],
            )
            raise ConflictError("production completion requires sealed captions")
        qa_artifact = qa_artifacts[0]
        qa_path = (
            self._run_directory(run)
            / "qingshan-workspace"
            / "exports"
            / qa_artifact.relative_path
        )
        qa_bytes: bytes | None = None
        qa_payload: dict | None = None
        try:
            qa_bytes = qa_path.read_bytes()
            decoded_payload = json.loads(qa_bytes.decode("utf-8"))
            qa_payload = decoded_payload if isinstance(decoded_payload, dict) else None
            evidence = FinalQAEvidence.model_validate(qa_payload)
        except (OSError, UnicodeError, ValueError) as exc:
            source_qa_sha256 = (
                hashlib.sha256(qa_bytes).hexdigest() if qa_bytes is not None else None
            )
            failed_checks = [
                field
                for field in (
                    "original_resolution_reviewed",
                    "picture_passed",
                    "audio_sync_passed",
                    "captions_passed",
                    "continuity_passed",
                    "safety_passed",
                )
                if qa_payload is None or qa_payload.get(field) is not True
            ]
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=master_artifacts[0].sha256,
                source_qa_sha256=source_qa_sha256,
                codes=failed_checks or ["qa_report_contract"],
            )
            raise ConflictError("sealed final QA report is unreadable or invalid") from exc
        if evidence.run_id != run_id:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=master_artifacts[0].sha256,
                source_qa_sha256=qa_artifact.sha256,
                codes=["qa_run_binding"],
            )
            raise ConflictError("final QA report belongs to a different production run")
        if evidence.master_sha256 != master_artifacts[0].sha256:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=master_artifacts[0].sha256,
                source_qa_sha256=qa_artifact.sha256,
                codes=["qa_master_binding"],
            )
            raise ConflictError("final QA report reviewed a different master")

        completed_run, episode = self.repository.complete_run_after_qa(
            run_id,
            output_seal_sha256=seal.manifest_sha256,
            qa_report_sha256=qa_artifact.sha256,
            completed_by=request.completed_by,
        )
        return ProductionCompletionResult(
            run=completed_run,
            episode=episode,
            output_seal_sha256=seal.manifest_sha256,
            qa_report_sha256=qa_artifact.sha256,
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
        remote_states: set[RemoteTaskState] = set()
        if run is not None:
            stage, percent, action, explanation = RUN_PROGRESS[run.status]
            if run.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
                percent = EPISODE_PROGRESS[episode.status][1]
            bindings = self.repository.list_remote_task_bindings(run.id)
            remote_states = {binding.state for binding in bindings}
            if RemoteTaskState.AMBIGUOUS_CHARGE in remote_states:
                stage, percent, action, explanation = (
                    "charge_reconciliation",
                    45,
                    "正在核对是否扣费",
                    "远端结果不明确；Nalu 正在核对任务和账单，绝不会自动重复提交。",
                )
            elif RemoteTaskState.PREPARED in remote_states:
                stage, percent, action, explanation = (
                    "provider_submission_prepared",
                    42,
                    "提交记录已安全保存",
                    "付费任务意图已保存在本机，正在等待远端接单证据。",
                )
            elif RemoteTaskState.SUBMITTED in remote_states:
                stage, percent, action, explanation = (
                    "remote_generation",
                    55,
                    "远端已接单，正在制作",
                    "远端任务编号已经安全记录；重新打开应用也不会重复提交。",
                )
            elif remote_states and remote_states == {RemoteTaskState.ZERO_CHARGE_FAILED}:
                stage, percent, action, explanation = (
                    "safe_retry_review",
                    45,
                    "已确认没有扣费",
                    "本次失败已核对为零扣费；再次提交前仍需重新确认。",
                )
            elif remote_states and remote_states <= {
                RemoteTaskState.COMPLETED,
                RemoteTaskState.CANCELLED,
            } and RemoteTaskState.COMPLETED in remote_states:
                stage, percent, action, explanation = (
                    "remote_results_received",
                    72,
                    "远端结果已返回",
                    "生成结果和扣费凭证已经保存，正在进入后期制作。",
                )
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
                and RemoteTaskState.AMBIGUOUS_CHARGE not in remote_states
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
