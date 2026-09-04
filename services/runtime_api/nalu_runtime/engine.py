from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .continuity import audit_continuity
from .decoded_media_qa import inspect_decoded_media
from .local_visual_analyzer import (
    AppleVisionAnalyzer,
    LocalVisualAnalyzerError,
    VisualAnalyzerRunner,
    execute_local_visual_analysis,
)
from .media_structure_qa import inspect_mp4, inspect_webvtt
from .models import (
    AudienceMode,
    ContinuityPreflightRequest,
    DecodedMediaQAReport,
    EpisodeProductionProgress,
    EpisodeStatus,
    FinalQAEvidence,
    LocalVisualAnalysisResult,
    MediaStructureQAReport,
    PlatformPublicationApproval,
    PostproductionLineageQAReport,
    PostproductionMaterializationCreate,
    PostproductionMaterializationResult,
    PostproductionRepairPlan,
    PostproductionRepairTask,
    ProductionCompletionRequest,
    ProductionCompletionResult,
    ProductionPackage,
    ProductionRun,
    ProductionRunCreate,
    PublicationDryRun,
    PublicationDryRunCreate,
    PublicationMetricsLearningResult,
    PublicationMetricsSyncCreate,
    PublicationReconciliationCreate,
    PublicationReconciliationRecord,
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
    SemanticMediaQAReport,
    SemanticMediaQARequest,
    VisualContinuityQAReport,
)
from .postproduction_lineage_qa import audio_energy_fingerprint, inspect_postproduction_lineage
from .postproduction_materializer import (
    PostproductionMaterializationError,
    materialize_postproduction,
)
from .publication_adapters import publication_adapter
from .publication_learning import PublicationLearningVerifier
from .qingshan_adapter import QingshanAdapter, QingshanAdapterError
from .remote_submitter import DurableRemoteTaskSubmitter
from .repository import ConflictError, NotFoundError, Repository, new_id, utc_now
from .secure_files import (
    harden_tree,
    publish_exclusive_text,
    replace_text_durably,
    secure_directory,
    secure_file,
)
from .semantic_media_qa import inspect_semantic_asr, inspect_shot_boundaries
from .semantic_recognizer import (
    AppleSpeechRecognizer,
    DisabledLocalSemanticRecognizer,
    LocalSemanticRecognizer,
    SemanticRecognizerError,
)
from .visual_continuity_qa import inspect_visual_continuity

EPISODE_PROGRESS = {
    EpisodeStatus.PLANNED: ("planning", 0, "等待完善分集规划", "这一集还在规划中。"),
    EpisodeStatus.SCRIPT_DRAFT: ("script", 10, "正在撰写剧本", "剧本正在形成初稿。"),
    EpisodeStatus.SCRIPT_REVIEW: ("script_review", 15, "等待确认剧本", "请检查并确认本集剧本。"),
    EpisodeStatus.SCRIPT_APPROVED: ("ready", 20, "可以进入制作", "本集剧本已确认。"),
    EpisodeStatus.PREPRODUCTION: ("preproduction", 30, "正在准备制作", "素材和生产包正在预检。"),
    EpisodeStatus.GENERATING: ("generation", 60, "正在生成镜头", "专业生产线正在生成本集。"),
    EpisodeStatus.POSTPRODUCTION: (
        "postproduction",
        80,
        "正在后期制作",
        "画面、声音和字幕正在合成。",
    ),
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
    "media_structure_qa_presence": (
        "container and caption structure QA",
        "No immutable MP4/WebVTT structure report is bound to this output seal.",
        "Run the local container and caption timeline gate before completion.",
    ),
    "decoded_media_qa_presence": (
        "decoded media QA",
        "No immutable decoded-media QA report is bound to this output seal.",
        "Decode the sealed master, run picture/audio/caption alignment gates and record the report.",
    ),
    "semantic_media_qa_presence": (
        "semantic media QA",
        "No immutable local semantic-ASR and authored-boundary report is bound to this seal.",
        "Run local final-master recognition and decoded authored-boundary QA before completion.",
    ),
    "postproduction_lineage_qa_presence": (
        "postproduction lineage QA",
        "No immutable shot-selection, normalization and audio-mix report is bound to this seal.",
        "Validate the sealed postproduction manifest and every referenced media file.",
    ),
    "visual_continuity_qa_presence": (
        "visual continuity QA",
        "No immutable identity, wardrobe, space/axis, pose and prop report is bound to this seal.",
        "Run decoded visual-continuity QA against the exact sealed master before completion.",
    ),
    "visual_continuity_manifest": (
        "visual continuity manifest",
        "The production-bound visual evidence manifest is missing, invalid or not bound to this master.",
        "Regenerate local visual evidence from the exact sealed master and package authority.",
    ),
    "visual_identity": (
        "character identity",
        "A character identity observation is missing, stale, low-confidence or mismatched.",
        "Repair the cited character shot and rerun identity analysis against the confirmed character revision.",
    ),
    "visual_wardrobe": (
        "character wardrobe",
        "A wardrobe observation is missing, stale, low-confidence or mismatched.",
        "Restore the confirmed costume for the cited shot and rerun wardrobe analysis.",
    ),
    "visual_space_axis": (
        "space and screen axis",
        "A location, screen-side or axis observation is missing, low-confidence or mismatched.",
        "Repair blocking, camera direction or the declared axis contract and rerun visual analysis.",
    ),
    "visual_pose": (
        "character pose",
        "A pose observation is missing, low-confidence or inconsistent with the shot contract.",
        "Repair the cited pose or update the approved shot contract, then rerun analysis.",
    ),
    "visual_prop": (
        "props",
        "A prop presence, ownership or state observation is missing, low-confidence or mismatched.",
        "Repair the cited prop continuity and rerun analysis against the confirmed prop authority.",
    ),
    "postproduction_manifest": (
        "postproduction manifest",
        "The postproduction manifest is missing, unreadable or bound to another package/master.",
        "Rebuild the package-bound postproduction manifest and seal it with the repaired master.",
    ),
    "shot_selection": (
        "selected shot timeline",
        "A selected shot lacks admission, provider receipt, source digest or a contiguous edit range.",
        "Select only admitted source shots, restore task/receipt evidence and rebuild the timeline.",
    ),
    "media_normalization": (
        "normalized shot media",
        "A normalized segment failed decode, format, duration or zero-based timestamp checks.",
        "Normalize the cited segment to the declared picture contract and 48 kHz stereo audio.",
    ),
    "audio_stems": (
        "dialogue, ambience, foley, music and SFX stems",
        "An audio lane is missing, silent, undecodable or lacks cue provenance.",
        "Repair the cited stem or record a specific creative omission, then rebuild the mix.",
    ),
    "published_mix": (
        "published audio mix",
        "The published mix is missing, malformed or does not match the final master's audio energy.",
        "Re-export the 48 kHz stereo published mix and assemble the final master from that exact mix.",
    ),
    "subtitle_lineage": (
        "subtitle lineage",
        "The postproduction timeline does not bind the exact sealed captions and source contract.",
        "Rebuild subtitle lineage against the exact captions file and source contract digest.",
    ),
    "decoded_video": (
        "decoded picture track",
        "The picture track could not be decoded or failed frame/timeline normalization.",
        "Repair or normalize the picture track, create a new seal and rerun decoded-media QA.",
    ),
    "frame_repeat": (
        "decoded picture track",
        "The decoded master contains an excessive identical-frame or black-frame run.",
        "Repair frozen or black shots, create a new master and rerun decoded-media QA.",
    ),
    "audio_vad": (
        "decoded audio track",
        "The audio track could not be decoded or has insufficient voice activity or excessive silence/clipping.",
        "Repair and normalize the final mix, then rerun decoded-media QA.",
    ),
    "caption_speech_alignment": (
        "captions and dialogue",
        "Too many caption cues do not overlap a decoded voiced-audio interval.",
        "Retimestamp captions or repair dialogue audio, then rerun decoded-media QA.",
    ),
    "semantic_asr": (
        "final dialogue transcript",
        "The exact sealed master failed local semantic speech-to-caption comparison.",
        "Repair dialogue or captions, rerun local recognition and bind a new report to the new seal.",
    ),
    "shot_boundary": (
        "authored shot boundaries",
        "The sealed shot manifest or decoded frames around an authored cut failed boundary QA.",
        "Repair the shot assembly or transition contract, reseal and rerun boundary QA.",
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
    def __init__(
        self,
        repository: Repository,
        data_root: Path,
        repository_root: Path,
        remote_task_submitter: DurableRemoteTaskSubmitter,
        visual_analyzer: VisualAnalyzerRunner | None = None,
        semantic_recognizer: LocalSemanticRecognizer | None = None,
    ):
        self.repository = repository
        self.remote_task_submitter = remote_task_submitter
        self.data_root = data_root.resolve()
        secure_directory(self.data_root)
        self.repository_root = repository_root
        self.adapter = QingshanAdapter(repository_root)
        configured_analyzer = os.environ.get("NALU_VISUAL_ANALYZER_BINARY")
        self.visual_analyzer = visual_analyzer or AppleVisionAnalyzer(
            Path(configured_analyzer) if configured_analyzer else None
        )
        configured_recognizer = os.environ.get("NALU_SEMANTIC_RECOGNIZER_BINARY")
        self.semantic_recognizer = semantic_recognizer or (
            AppleSpeechRecognizer(Path(configured_recognizer))
            if configured_recognizer
            else DisabledLocalSemanticRecognizer()
        )

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
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(
            character in "0123456789abcdef" for character in value
        )

    @staticmethod
    def _sync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _write_and_promote_package(
        cls, staging_path: Path, package_path: Path, encoded_package: str
    ) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(staging_path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                descriptor = -1
                target.write(encoded_package)
                target.flush()
                os.fsync(target.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        secure_file(staging_path)
        os.replace(staging_path, package_path)
        secure_file(package_path)
        cls._sync_directory(package_path.parent)

    def _run_directory(self, run: ProductionRun) -> Path:
        run_directory = Path(run.package_path).resolve().parent
        runs_root = (self.data_root / "runs").resolve()
        if not run_directory.is_relative_to(runs_root):
            raise ConflictError("production run package is outside the managed data root")
        return run_directory

    def materialize_postproduction(
        self, run_id: str, request: PostproductionMaterializationCreate
    ) -> PostproductionMaterializationResult:
        run = self.repository.get_run(run_id)
        if run.status not in {RunStatus.RUNNING, RunStatus.QA_REVIEW}:
            raise ConflictError(
                "local postproduction materialization requires a running run or exact QA replay"
            )
        run_directory = self._run_directory(run)
        if (run_directory / "rendered-output-seal.json").exists():
            raise ConflictError("sealed outputs cannot be rematerialized")
        package_path = Path(run.package_path)
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConflictError("production package is unreadable before materialization") from exc
        package_sha256 = str(package.get("package_sha256") or "")
        package_body = {key: value for key, value in package.items() if key != "package_sha256"}
        if not package_sha256 or self._canonical_sha256(package_body) != package_sha256:
            raise ConflictError("production package integrity check failed before materialization")
        workspace = run_directory / "qingshan-workspace"
        exports_root = workspace / "exports"
        workspace_manifest = workspace / "workspace-manifest.json"
        if not exports_root.is_dir() or not workspace_manifest.is_file():
            raise ConflictError("Qingshan workspace is incomplete before materialization")
        last_cancel_check = 0.0
        cancelled = False

        def cancellation_requested() -> bool:
            nonlocal last_cancel_check, cancelled
            if cancelled:
                return True
            now = time.monotonic()
            if now - last_cancel_check >= 0.25:
                cancelled = self.repository.get_run(run.id).status == RunStatus.CANCELLED
                last_cancel_check = now
            return cancelled

        try:
            result = materialize_postproduction(
                run_id=run.id,
                project_id=run.project_id,
                episode_id=run.episode_id,
                episode_number=int(package["episode"]["episode_number"]),
                production_package_sha256=package_sha256,
                workspace_manifest_sha256=self._sha256_file(workspace_manifest),
                exports_root=exports_root,
                request=request,
                created_at=utc_now(),
                should_cancel=cancellation_requested,
            )
        except (KeyError, TypeError, ValueError, PostproductionMaterializationError) as exc:
            raise ConflictError(str(exc)) from exc
        self.repository.mark_postproduction_materialized(
            run.id,
            plan_sha256=result.plan_sha256,
            result_sha256=result.result_sha256,
            requested_by=request.requested_by,
        )
        return result

    def run_local_visual_analysis(self, run_id: str) -> LocalVisualAnalysisResult:
        run = self.repository.get_run(run_id)
        if run.status != RunStatus.QA_REVIEW:
            raise ConflictError("local visual analysis requires a materialized QA-review run")
        run_directory = self._run_directory(run)
        if (run_directory / "rendered-output-seal.json").exists():
            raise ConflictError("sealed outputs cannot be replaced by a new visual analysis")
        result_path = run_directory / "local-visual-analysis-result.json"
        if result_path.is_file() and not result_path.is_symlink():
            try:
                existing = LocalVisualAnalysisResult.model_validate_json(
                    result_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError) as exc:
                raise ConflictError("stored local visual analysis is unreadable") from exc
            body = existing.model_dump(mode="json", exclude={"result_sha256"})
            if self._canonical_sha256(body) != existing.result_sha256:
                raise ConflictError("stored local visual analysis digest mismatch")
            workspace = run_directory / "qingshan-workspace"
            exports = workspace / "exports"
            materialization_paths = list(
                (exports / "materialized").glob("*/materialization-result.json")
            )
            try:
                if len(materialization_paths) != 1:
                    raise ValueError("materialization result is missing or ambiguous")
                materialization = PostproductionMaterializationResult.model_validate_json(
                    materialization_paths[0].read_text(encoding="utf-8")
                )
                materialization_body = materialization.model_dump(
                    mode="json", exclude={"result_sha256"}
                )
                if self._canonical_sha256(materialization_body) != materialization.result_sha256:
                    raise ValueError("materialization result digest changed")
                resolved_exports = exports.resolve(strict=True)
                master_candidate = exports / materialization.master["relative_path"]
                manifest_candidate = exports / str(existing.manifest.get("relative_path") or "")
                if master_candidate.is_symlink() or manifest_candidate.is_symlink():
                    raise ValueError("stored visual evidence uses a symbolic link")
                master = master_candidate.resolve(strict=True)
                manifest = manifest_candidate.resolve(strict=True)
                if (
                    not master.is_relative_to(resolved_exports)
                    or not manifest.is_relative_to(resolved_exports)
                ):
                    raise ValueError("stored visual evidence escaped exports")
                task_path = next((workspace / "workflow" / "tasks").glob("*_PRODUCTION_TASK.json"))
                task = json.loads(task_path.read_text(encoding="utf-8"))
                inputs_path = workspace / task["local_visual_analysis"]["inputs_path"]
                inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
                inputs_body = {
                    key: value for key, value in inputs.items() if key != "inputs_sha256"
                }
                if self._canonical_sha256(inputs_body) != inputs.get("inputs_sha256"):
                    raise ValueError("visual analyzer input digest changed")
                analyzer_model_sha256 = self.visual_analyzer.model_sha256
            except (
                StopIteration,
                OSError,
                KeyError,
                TypeError,
                ValueError,
                LocalVisualAnalyzerError,
            ) as exc:
                raise ConflictError("stored local visual analysis inputs are unreadable") from exc
            if (
                existing.run_id != run.id
                or existing.master_sha256 != materialization.master.get("sha256")
                or not master.is_file()
                or self._sha256_file(master) != existing.master_sha256
                or inputs.get("inputs_sha256") != existing.inputs_sha256
                or analyzer_model_sha256 != existing.analyzer_model_sha256
                or not manifest.is_file()
                or self._sha256_file(manifest) != existing.manifest.get("sha256")
            ):
                raise ConflictError("stored local visual analysis evidence changed")
            self.repository.record_local_visual_analysis(
                run.id,
                result_sha256=existing.result_sha256,
                manifest_sha256=existing.manifest["sha256"],
                status=existing.status,
                failure_count=len(existing.failures),
            )
            return existing
        try:
            result = execute_local_visual_analysis(
                run_id=run.id,
                project_id=run.project_id,
                episode_id=run.episode_id,
                data_root=self.data_root,
                run_directory=run_directory,
                analyzer=self.visual_analyzer,
            )
        except (KeyError, TypeError, ValueError, LocalVisualAnalyzerError) as exc:
            raise ConflictError(str(exc)) from exc
        try:
            publish_exclusive_text(result_path, result.model_dump_json(indent=2) + "\n")
        except FileExistsError as exc:
            raise ConflictError("local visual analysis was recorded concurrently") from exc
        self.repository.record_local_visual_analysis(
            run.id,
            result_sha256=result.result_sha256,
            manifest_sha256=result.manifest["sha256"],
            status=result.status,
            failure_count=len(result.failures),
        )
        return result

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
            "resolved_library_sha256": self._canonical_sha256(package.get("resolved_library", [])),
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
        try:
            publish_exclusive_text(seal_path, seal.model_dump_json(indent=2) + "\n")
        except FileExistsError as exc:
            try:
                existing = RenderedOutputSeal.model_validate_json(
                    seal_path.read_text(encoding="utf-8")
                )
                existing_body = existing.model_dump(mode="json", exclude={"manifest_sha256"})
                exact_recovery = (
                    self._canonical_sha256(existing_body) == existing.manifest_sha256
                    and existing.run_id == run.id
                    and existing.project_id == run.project_id
                    and existing.episode_id == run.episode_id
                    and existing.production_package_sha256 == package_hash
                    and existing.resolved_library_sha256
                    == self._canonical_sha256(package.get("resolved_library", []))
                    and existing.workspace_manifest_sha256
                    == self._sha256_file(workspace_manifest)
                    and existing.artifacts == artifacts
                    and existing.sealed_by == request.sealed_by
                )
            except (OSError, ValueError):
                exact_recovery = False
            if not exact_recovery:
                raise ConflictError("rendered outputs are already sealed for this run") from exc
            self.repository.recover_rendered_output_seal_event(
                run.id,
                manifest_path=str(seal_path),
                manifest_sha256=existing.manifest_sha256,
                artifact_count=len(existing.artifacts),
            )
            return existing
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
            seal = RenderedOutputSeal.model_validate_json(seal_path.read_text(encoding="utf-8"))
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
            package_body = {key: value for key, value in package.items() if key != "package_sha256"}
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
        replace_text_durably(plan_path, plan.model_dump_json(indent=2) + "\n")
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
                "rendered output integrity failed before media QA: " + "; ".join(integrity.failures)
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
        replace_text_durably(report_path, report.model_dump_json(indent=2) + "\n")
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

    def decoded_media_qa(self, run_id: str) -> DecodedMediaQAReport:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            raise ConflictError(
                "rendered output integrity failed before decoded media QA: "
                + "; ".join(integrity.failures)
            )
        run = self.repository.get_run(run_id)
        seal = integrity.seal
        masters = [artifact for artifact in seal.artifacts if artifact.kind == "master_video"]
        captions = [artifact for artifact in seal.artifacts if artifact.kind == "captions"]
        if len(masters) != 1 or len(captions) != 1:
            raise ConflictError("decoded media QA requires exactly one master and captions file")
        exports = self._run_directory(run) / "qingshan-workspace" / "exports"
        decoded = inspect_decoded_media(
            exports / masters[0].relative_path,
            exports / captions[0].relative_path,
        )
        report_body = {
            "schema_version": "nalu.decoded-media-qa/v1",
            "run_id": run.id,
            "output_seal_sha256": seal.manifest_sha256,
            "master_sha256": masters[0].sha256,
            "captions_sha256": captions[0].sha256,
            "video": decoded["video"],
            "audio": decoded["audio"],
            "caption_speech_alignment": decoded["caption_speech_alignment"],
            "status": decoded["status"],
            "failures": decoded["failures"],
            "created_at": utc_now(),
        }
        report = DecodedMediaQAReport(
            **report_body,
            report_sha256=self._canonical_sha256(report_body),
        )
        report_path = self._run_directory(run) / "decoded-media-qa.json"
        if report_path.is_file():
            try:
                existing = DecodedMediaQAReport.model_validate_json(
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
        replace_text_durably(report_path, report.model_dump_json(indent=2) + "\n")
        self.repository.append_run_event(
            run.id,
            "decoded_media_qa_completed",
            from_status=run.status,
            to_status=run.status,
            message="Decoded picture, audio/VAD and caption-speech alignment gates completed.",
            payload={
                "status": report.status,
                "report_sha256": report.report_sha256,
                "failure_count": len(report.failures),
                "semantic_asr_verified": False,
            },
        )
        if report.failures:
            repair_codes: list[str] = []
            video_failures = report.video.get("failures") or []
            if video_failures:
                repair_codes.append("decoded_video")
            if any(
                "REPEAT" in failure or "IDENTICAL" in failure or "BLACK" in failure
                for failure in video_failures
            ):
                repair_codes.append("frame_repeat")
            if report.audio.get("status") != "PASS":
                repair_codes.append("audio_vad")
            if report.caption_speech_alignment.get("status") != "PASS":
                repair_codes.append("caption_speech_alignment")
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256,
                codes=repair_codes or ["decoded_video"],
            )
        return report

    def stored_decoded_media_qa(self, run_id: str) -> DecodedMediaQAReport:
        run = self.repository.get_run(run_id)
        report_path = self._run_directory(run) / "decoded-media-qa.json"
        if not report_path.is_file() or report_path.is_symlink():
            raise ConflictError("decoded media QA has not been recorded for this run")
        try:
            report = DecodedMediaQAReport.model_validate_json(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError("decoded media QA report is unreadable or invalid") from exc
        body = report.model_dump(mode="json", exclude={"report_sha256"})
        if self._canonical_sha256(body) != report.report_sha256:
            raise ConflictError("decoded media QA report digest mismatch")
        if report.run_id != run.id:
            raise ConflictError("decoded media QA report belongs to another run")
        return report

    def postproduction_lineage_qa(self, run_id: str) -> PostproductionLineageQAReport:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            raise ConflictError("sealed output integrity failed before postproduction lineage QA")
        run = self.repository.get_run(run_id)
        seal = integrity.seal
        masters = [artifact for artifact in seal.artifacts if artifact.kind == "master_video"]
        captions = [artifact for artifact in seal.artifacts if artifact.kind == "captions"]
        manifests = [
            artifact for artifact in seal.artifacts if artifact.kind == "postproduction_manifest"
        ]
        if len(masters) != 1 or len(captions) != 1 or len(manifests) != 1:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256 if len(masters) == 1 else None,
                codes=["postproduction_lineage_qa_presence"],
            )
            raise ConflictError(
                "postproduction lineage QA requires exactly one master, captions and manifest"
            )
        exports = self._run_directory(run) / "qingshan-workspace" / "exports"
        inspected = inspect_postproduction_lineage(
            exports / manifests[0].relative_path,
            exports_root=exports,
            production_package_sha256=seal.production_package_sha256,
            master_path=exports / masters[0].relative_path,
            master_sha256=masters[0].sha256,
            captions_path=exports / captions[0].relative_path,
            captions_sha256=captions[0].sha256,
        )
        body = {
            "schema_version": "nalu.postproduction-lineage-qa/v1",
            "run_id": run.id,
            "output_seal_sha256": seal.manifest_sha256,
            "master_sha256": masters[0].sha256,
            "captions_sha256": captions[0].sha256,
            "postproduction_manifest_sha256": manifests[0].sha256,
            "master_media": inspected["master_media"],
            "shot_selection": inspected["shot_selection"],
            "audio_mix": inspected["audio_mix"],
            "subtitles": inspected["subtitles"],
            "status": inspected["status"],
            "failures": inspected["failures"],
            "created_at": utc_now(),
        }
        report = PostproductionLineageQAReport(
            **body,
            report_sha256=self._canonical_sha256(body),
        )
        report_path = self._run_directory(run) / "postproduction-lineage-qa.json"
        if report_path.is_file():
            try:
                existing = PostproductionLineageQAReport.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                )
                if (
                    self._canonical_sha256(
                        existing.model_dump(mode="json", exclude={"report_sha256"})
                    )
                    == existing.report_sha256
                    and existing.output_seal_sha256 == report.output_seal_sha256
                    and existing.postproduction_manifest_sha256
                    == report.postproduction_manifest_sha256
                    and existing.status == report.status
                    and existing.failures == report.failures
                ):
                    return existing
            except (OSError, ValueError):
                pass
            raise ConflictError("postproduction lineage QA already exists with different evidence")
        try:
            publish_exclusive_text(report_path, report.model_dump_json(indent=2) + "\n")
        except FileExistsError as exc:
            raise ConflictError("postproduction lineage QA was recorded concurrently") from exc
        self.repository.append_run_event(
            run.id,
            "postproduction_lineage_qa_completed",
            from_status=run.status,
            to_status=run.status,
            message=(
                "Selected shots, normalized segments, audio stems, published mix and "
                "subtitle lineage were checked against decoded files."
            ),
            payload={
                "status": report.status,
                "report_sha256": report.report_sha256,
                "failure_count": len(report.failures),
            },
        )
        if report.failures:
            repair_codes: list[str] = []
            if any(failure.startswith("MANIFEST_") for failure in report.failures):
                repair_codes.append("postproduction_manifest")
            if any(failure.startswith(("SHOT_", "TIMELINE_")) for failure in report.failures):
                repair_codes.append("shot_selection")
            if any(
                failure.startswith(("NORMALIZED_", "AUDIO_CONTRACT_"))
                for failure in report.failures
            ):
                repair_codes.append("media_normalization")
            if any(failure.startswith("STEM_") for failure in report.failures):
                repair_codes.append("audio_stems")
            if any(
                failure.startswith(("PUBLISHED_MIX_", "FINAL_MASTER_AUDIO_"))
                for failure in report.failures
            ):
                repair_codes.append("published_mix")
            if any(failure.startswith("SUBTITLE_") for failure in report.failures):
                repair_codes.append("subtitle_lineage")
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256,
                source_qa_sha256=manifests[0].sha256,
                codes=repair_codes or ["postproduction_manifest"],
            )
        return report

    def stored_postproduction_lineage_qa(self, run_id: str) -> PostproductionLineageQAReport:
        run = self.repository.get_run(run_id)
        path = self._run_directory(run) / "postproduction-lineage-qa.json"
        if not path.is_file() or path.is_symlink():
            raise ConflictError("postproduction lineage QA has not been recorded for this run")
        try:
            report = PostproductionLineageQAReport.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError(
                "postproduction lineage QA report is unreadable or invalid"
            ) from exc
        body = report.model_dump(mode="json", exclude={"report_sha256"})
        if self._canonical_sha256(body) != report.report_sha256:
            raise ConflictError("postproduction lineage QA report digest mismatch")
        if report.run_id != run.id:
            raise ConflictError("postproduction lineage QA report belongs to another run")
        return report

    def visual_continuity_qa(self, run_id: str) -> VisualContinuityQAReport:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            raise ConflictError("sealed output integrity failed before visual continuity QA")
        run = self.repository.get_run(run_id)
        seal = integrity.seal
        masters = [artifact for artifact in seal.artifacts if artifact.kind == "master_video"]
        manifests = [
            artifact
            for artifact in seal.artifacts
            if artifact.kind == "visual_continuity_manifest"
        ]
        if len(masters) != 1 or len(manifests) != 1:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256 if len(masters) == 1 else None,
                codes=["visual_continuity_qa_presence"],
            )
            raise ConflictError(
                "visual continuity QA requires exactly one master and evidence manifest"
            )
        try:
            package = json.loads(Path(run.package_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConflictError("production package is unreadable before visual QA") from exc
        resolved_library = package.get("resolved_library") or []
        exports = self._run_directory(run) / "qingshan-workspace" / "exports"
        inspected = inspect_visual_continuity(
            exports / manifests[0].relative_path,
            production_package_sha256=seal.production_package_sha256,
            master_path=exports / masters[0].relative_path,
            master_sha256=masters[0].sha256,
            resolved_library=resolved_library,
            resolved_library_sha256=seal.resolved_library_sha256,
        )
        body = {
            "schema_version": "nalu.visual-continuity-qa/v1",
            "run_id": run.id,
            "output_seal_sha256": seal.manifest_sha256,
            "master_sha256": masters[0].sha256,
            "resolved_library_sha256": seal.resolved_library_sha256,
            "visual_continuity_manifest_sha256": manifests[0].sha256,
            "analyzer": inspected["analyzer"],
            "decoded_frame_count": inspected["decoded_frame_count"],
            "shot_count": inspected["shot_count"],
            "passed_shot_count": inspected["passed_shot_count"],
            "domain_results": inspected["domain_results"],
            "shots": inspected["shots"],
            "status": inspected["status"],
            "failures": inspected["failures"],
            "created_at": utc_now(),
        }
        report = VisualContinuityQAReport(
            **body,
            report_sha256=self._canonical_sha256(body),
        )
        report_path = self._run_directory(run) / "visual-continuity-qa.json"
        if report_path.is_file():
            try:
                existing = self.stored_visual_continuity_qa(run_id)
                if (
                    existing.output_seal_sha256 == report.output_seal_sha256
                    and existing.visual_continuity_manifest_sha256
                    == report.visual_continuity_manifest_sha256
                    and existing.status == report.status
                    and existing.failures == report.failures
                ):
                    return existing
            except ConflictError:
                pass
            raise ConflictError("visual continuity QA already exists with different evidence")
        try:
            publish_exclusive_text(report_path, report.model_dump_json(indent=2) + "\n")
        except FileExistsError as exc:
            raise ConflictError("visual continuity QA was recorded concurrently") from exc
        self.repository.append_run_event(
            run.id,
            "visual_continuity_qa_completed",
            from_status=run.status,
            to_status=run.status,
            message=(
                "Decoded identity, wardrobe, space/axis, pose and prop evidence "
                "was checked against the sealed master and confirmed library."
            ),
            payload={
                "status": report.status,
                "report_sha256": report.report_sha256,
                "failure_count": len(report.failures),
                "human_review_replaced": False,
            },
        )
        if report.failures:
            repair_codes: list[str] = []
            if any(
                failure.startswith(("MANIFEST_", "PACKAGE_", "ANALYZER_", "FRAME_", "SHOT_"))
                for failure in report.failures
            ):
                repair_codes.append("visual_continuity_manifest")
            domain_codes = {
                "IDENTITY_": "visual_identity",
                "WARDROBE_": "visual_wardrobe",
                "SPACE_AXIS_": "visual_space_axis",
                "POSE_": "visual_pose",
                "PROP_": "visual_prop",
            }
            for prefix, code in domain_codes.items():
                if any(failure.startswith(prefix) for failure in report.failures):
                    repair_codes.append(code)
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256,
                source_qa_sha256=manifests[0].sha256,
                codes=repair_codes or ["visual_continuity_manifest"],
            )
        return report

    def stored_visual_continuity_qa(self, run_id: str) -> VisualContinuityQAReport:
        run = self.repository.get_run(run_id)
        path = self._run_directory(run) / "visual-continuity-qa.json"
        if not path.is_file() or path.is_symlink():
            raise ConflictError("visual continuity QA has not been recorded for this run")
        try:
            report = VisualContinuityQAReport.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ConflictError("visual continuity QA report is unreadable or invalid") from exc
        body = report.model_dump(mode="json", exclude={"report_sha256"})
        if self._canonical_sha256(body) != report.report_sha256:
            raise ConflictError("visual continuity QA report digest mismatch")
        if report.run_id != run.id:
            raise ConflictError("visual continuity QA report belongs to another run")
        return report

    def sealed_master_path(self, run_id: str) -> tuple[Path, RenderedOutputArtifact]:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            raise ConflictError("sealed output integrity failed before master access")
        masters = [
            artifact for artifact in integrity.seal.artifacts if artifact.kind == "master_video"
        ]
        if len(masters) != 1:
            raise ConflictError("exactly one sealed master is required")
        run = self.repository.get_run(run_id)
        path = (
            self._run_directory(run) / "qingshan-workspace" / "exports" / masters[0].relative_path
        )
        return path, masters[0]

    def semantic_media_qa(
        self, run_id: str, request: SemanticMediaQARequest
    ) -> SemanticMediaQAReport:
        integrity = self.rendered_output_integrity(run_id)
        if not integrity.integrity_ok:
            raise ConflictError("sealed output integrity failed before semantic media QA")
        run = self.repository.get_run(run_id)
        seal = integrity.seal
        masters = [artifact for artifact in seal.artifacts if artifact.kind == "master_video"]
        captions = [artifact for artifact in seal.artifacts if artifact.kind == "captions"]
        shot_manifests = [
            artifact for artifact in seal.artifacts if artifact.kind == "shot_manifest"
        ]
        if len(masters) != 1 or len(captions) != 1 or len(shot_manifests) != 1:
            raise ConflictError(
                "semantic media QA requires exactly one sealed master, captions and shot manifest"
            )
        if request.source_master_sha256 != masters[0].sha256:
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256,
                codes=["semantic_asr"],
            )
            raise ConflictError("speech recognition belongs to a different master")
        structure_qa = self.stored_media_structure_qa(run_id)
        decoded_qa = self.stored_decoded_media_qa(run_id)
        if structure_qa.status != "PASS" or decoded_qa.status != "PASS":
            raise ConflictError("structure and decoded media QA must pass first")
        if (
            structure_qa.output_seal_sha256 != seal.manifest_sha256
            or decoded_qa.output_seal_sha256 != seal.manifest_sha256
        ):
            raise ConflictError("prior media QA belongs to a different output seal")
        exports = self._run_directory(run) / "qingshan-workspace" / "exports"
        master_path = exports / masters[0].relative_path
        try:
            recognition = self.semantic_recognizer.recognize(
                master_path,
                source_master_sha256=masters[0].sha256,
            )
        except SemanticRecognizerError as exc:
            raise ConflictError(str(exc)) from exc
        decoded_audio_fingerprint = audio_energy_fingerprint(master_path)
        if recognition.source_master_sha256 != masters[0].sha256:
            raise ConflictError("local recognizer output belongs to a different master")
        if recognition.decoded_audio_fingerprint != decoded_audio_fingerprint:
            raise ConflictError("local recognizer output belongs to different decoded audio")
        executable_sha256 = recognition.recognizer_executable_sha256
        if len(executable_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in executable_sha256
        ):
            raise ConflictError("local recognizer executable digest is invalid")
        if recognition.local_recognition is not True or recognition.network_used is not False:
            raise ConflictError("semantic QA requires local-only recognition execution")
        recognition_output = {
            "transcript": recognition.transcript,
            "segments": recognition.segments,
            "recognizer_id": recognition.recognizer_id,
            "recognizer_version": recognition.recognizer_version,
            "locale": recognition.locale,
            "generated_at": recognition.generated_at,
        }
        recognizer_execution_body = {
            "schema_version": "nalu.local-semantic-recognizer-evidence/v1",
            "source_master_sha256": masters[0].sha256,
            "decoded_audio_fingerprint": decoded_audio_fingerprint,
            "recognizer_executable_sha256": executable_sha256,
            "recognizer_output": recognition_output,
            "recognizer_output_sha256": self._canonical_sha256(recognition_output),
            "local_recognition": True,
            "network_used": False,
        }
        recognizer_execution = {
            **recognizer_execution_body,
            "evidence_sha256": self._canonical_sha256(recognizer_execution_body),
        }
        duration = float(structure_qa.mp4.get("duration_seconds") or 0)
        semantic_asr = inspect_semantic_asr(
            exports / captions[0].relative_path,
            transcript=recognition.transcript,
            segments=recognition.segments,
            recognizer_id=recognition.recognizer_id,
            locale=recognition.locale,
            local_recognition=recognition.local_recognition,
            media_duration_seconds=duration,
        )
        shot_boundaries = inspect_shot_boundaries(
            exports / masters[0].relative_path,
            exports / shot_manifests[0].relative_path,
            production_package_sha256=seal.production_package_sha256,
            media_duration_seconds=duration,
        )
        failures = [
            *("asr:" + value for value in semantic_asr["failures"]),
            *("boundary:" + value for value in shot_boundaries["failures"]),
        ]
        body = {
            "schema_version": "nalu.semantic-media-qa/v1",
            "run_id": run.id,
            "output_seal_sha256": seal.manifest_sha256,
            "master_sha256": masters[0].sha256,
            "captions_sha256": captions[0].sha256,
            "shot_manifest_sha256": shot_manifests[0].sha256,
            "recognizer_version": recognition.recognizer_version,
            "recognition_generated_at": recognition.generated_at,
            "recognizer_execution": recognizer_execution,
            "semantic_asr": semantic_asr,
            "shot_boundaries": shot_boundaries,
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "created_at": utc_now(),
        }
        report = SemanticMediaQAReport(
            **body,
            report_sha256=self._canonical_sha256(body),
        )
        report_path = self._run_directory(run) / "semantic-media-qa.json"
        if report_path.is_file():
            existing = self.stored_semantic_media_qa(run_id)
            if (
                existing.output_seal_sha256 == report.output_seal_sha256
                and existing.master_sha256 == report.master_sha256
                and existing.recognizer_version == report.recognizer_version
                and existing.recognition_generated_at == report.recognition_generated_at
                and existing.recognizer_execution == report.recognizer_execution
                and existing.semantic_asr == report.semantic_asr
                and existing.shot_boundaries == report.shot_boundaries
            ):
                return existing
            raise ConflictError("semantic media QA already exists with different evidence")
        try:
            publish_exclusive_text(report_path, report.model_dump_json(indent=2) + "\n")
        except FileExistsError as exc:
            raise ConflictError("semantic media QA was created concurrently") from exc
        self.repository.append_run_event(
            run.id,
            "semantic_media_qa_completed",
            from_status=run.status,
            to_status=run.status,
            message="Local semantic ASR and authored decoded-boundary QA completed.",
            payload={
                "status": report.status,
                "report_sha256": report.report_sha256,
                "failure_count": len(report.failures),
                "local_recognition": recognition.local_recognition,
            },
        )
        if failures:
            codes: list[str] = []
            if semantic_asr["status"] != "PASS":
                codes.append("semantic_asr")
            if shot_boundaries["status"] != "PASS":
                codes.append("shot_boundary")
            self._record_postproduction_repair_plan(
                run,
                output_seal_sha256=seal.manifest_sha256,
                master_sha256=masters[0].sha256,
                codes=codes,
            )
        return report

    def stored_semantic_media_qa(self, run_id: str) -> SemanticMediaQAReport:
        run = self.repository.get_run(run_id)
        path = self._run_directory(run) / "semantic-media-qa.json"
        if not path.is_file() or path.is_symlink():
            raise ConflictError("semantic media QA has not been recorded for this run")
        try:
            report = SemanticMediaQAReport.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConflictError("semantic media QA report is unreadable or invalid") from exc
        body = report.model_dump(mode="json", exclude={"report_sha256"})
        if self._canonical_sha256(body) != report.report_sha256:
            raise ConflictError("semantic media QA report digest mismatch")
        if report.run_id != run.id:
            raise ConflictError("semantic media QA report belongs to another run")
        execution = report.recognizer_execution
        if not isinstance(execution, dict):
            raise ConflictError("semantic recognizer execution evidence is missing")
        if execution.get("schema_version") != "nalu.local-semantic-recognizer-evidence/v1":
            raise ConflictError("semantic recognizer execution schema is invalid")
        evidence_sha256 = execution.get("evidence_sha256")
        evidence_body = {
            key: value for key, value in execution.items() if key != "evidence_sha256"
        }
        if not self._is_sha256(evidence_sha256) or (
            self._canonical_sha256(evidence_body) != evidence_sha256
        ):
            raise ConflictError("semantic recognizer execution evidence digest mismatch")
        if execution.get("source_master_sha256") != report.master_sha256:
            raise ConflictError("semantic recognizer execution belongs to another master")
        if execution.get("local_recognition") is not True or (
            execution.get("network_used") is not False
        ):
            raise ConflictError("semantic recognizer execution is not proven local-only")
        executable_sha256 = execution.get("recognizer_executable_sha256")
        decoded_audio_fingerprint = execution.get("decoded_audio_fingerprint")
        recognizer_output_sha256 = execution.get("recognizer_output_sha256")
        if not all(
            self._is_sha256(value)
            for value in (
                executable_sha256,
                decoded_audio_fingerprint,
                recognizer_output_sha256,
            )
        ):
            raise ConflictError("semantic recognizer execution digest is invalid")
        recognizer_output = execution.get("recognizer_output")
        if not isinstance(recognizer_output, dict) or (
            self._canonical_sha256(recognizer_output) != recognizer_output_sha256
        ):
            raise ConflictError("semantic recognizer output digest mismatch")
        if (
            recognizer_output.get("transcript") != report.semantic_asr.get("transcript")
            or recognizer_output.get("recognizer_id")
            != report.semantic_asr.get("recognizer_id")
            or recognizer_output.get("locale") != report.semantic_asr.get("locale")
            or recognizer_output.get("generated_at") != report.recognition_generated_at
            or recognizer_output.get("recognizer_version") != report.recognizer_version
        ):
            raise ConflictError("semantic recognizer output does not match QA report")
        master_path, master = self.sealed_master_path(run_id)
        if master.sha256 != report.master_sha256:
            raise ConflictError("semantic media QA belongs to a different sealed master")
        try:
            observed_audio_fingerprint = audio_energy_fingerprint(master_path)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ConflictError(
                "sealed master audio cannot be decoded for semantic evidence verification"
            ) from exc
        if observed_audio_fingerprint != decoded_audio_fingerprint:
            raise ConflictError("semantic recognizer decoded audio fingerprint mismatch")
        return report

    def create_release_package(self, run_id: str, request: ReleasePackageCreate) -> ReleasePackage:
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
        decoded_qa = self.stored_decoded_media_qa(run.id)
        if decoded_qa.status != "PASS":
            raise ConflictError("decoded media QA must pass before release packaging")
        if decoded_qa.output_seal_sha256 != integrity.seal.manifest_sha256:
            raise ConflictError("decoded media QA reviewed a different output seal")
        semantic_qa = self.stored_semantic_media_qa(run.id)
        if semantic_qa.status != "PASS":
            raise ConflictError("semantic media QA must pass before release packaging")
        if semantic_qa.output_seal_sha256 != integrity.seal.manifest_sha256:
            raise ConflictError("semantic media QA reviewed a different output seal")
        lineage_qa = self.stored_postproduction_lineage_qa(run.id)
        if lineage_qa.status != "PASS":
            raise ConflictError("postproduction lineage QA must pass before release packaging")
        if lineage_qa.output_seal_sha256 != integrity.seal.manifest_sha256:
            raise ConflictError("postproduction lineage QA reviewed a different output seal")
        visual_qa = self.stored_visual_continuity_qa(run.id)
        if visual_qa.status != "PASS":
            raise ConflictError("visual continuity QA must pass before release packaging")
        if visual_qa.output_seal_sha256 != integrity.seal.manifest_sha256:
            raise ConflictError("visual continuity QA reviewed a different output seal")

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
                and existing.decoded_media_qa_report_sha256 == decoded_qa.report_sha256
                and existing.semantic_media_qa_report_sha256 == semantic_qa.report_sha256
                and existing.postproduction_lineage_qa_report_sha256 == lineage_qa.report_sha256
                and existing.visual_continuity_qa_report_sha256 == visual_qa.report_sha256
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
            "decoded_media_qa_report_sha256": decoded_qa.report_sha256,
            "semantic_media_qa_report_sha256": semantic_qa.report_sha256,
            "postproduction_lineage_qa_report_sha256": lineage_qa.report_sha256,
            "visual_continuity_qa_report_sha256": visual_qa.report_sha256,
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
            package = ReleasePackage.model_validate_json(release_path.read_text(encoding="utf-8"))
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
        if run.status != RunStatus.COMPLETED or episode.status not in {
            EpisodeStatus.READY_TO_PUBLISH,
            EpisodeStatus.PUBLISHED,
        }:
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

    def stored_publication_dry_run(self, run_id: str, platform: str) -> PublicationDryRun:
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
        approval_body = dry_run.approval.model_dump(mode="json", exclude={"approval_sha256"})
        if self._canonical_sha256(approval_body) != dry_run.approval.approval_sha256:
            raise ConflictError("publication approval digest mismatch")
        if dry_run.run_id != run.id or dry_run.platform != platform:
            raise ConflictError("publication dry-run binding mismatch")
        package = self.stored_release_package(run.id)
        if dry_run.release_manifest_sha256 != package.manifest_sha256:
            raise ConflictError("publication dry-run references a different release package")
        return dry_run

    def reconcile_publication(
        self,
        run_id: str,
        request: PublicationReconciliationCreate,
        idempotency_key: str | None,
        verifier: PublicationLearningVerifier,
    ) -> PublicationReconciliationRecord:
        package = self.stored_release_package(run_id)
        dry_run = self.stored_publication_dry_run(run_id, request.platform)
        return self.repository.reconcile_publication(
            run_id,
            request,
            idempotency_key,
            verifier,
            local_release_manifest_sha256=package.manifest_sha256,
            publication_dry_run_sha256=dry_run.plan_sha256,
            channel_reference=dry_run.approval.channel_reference,
        )

    def sync_publication_metrics(
        self,
        run_id: str,
        request: PublicationMetricsSyncCreate,
        idempotency_key: str | None,
        verifier: PublicationLearningVerifier,
    ) -> PublicationMetricsLearningResult:
        return self.repository.sync_publication_metrics(
            run_id, request, idempotency_key, verifier
        )

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
            self._run_directory(run) / "qingshan-workspace" / "exports" / qa_artifact.relative_path
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

        required_media_qa = (
            (self.stored_media_structure_qa, "media_structure_qa_presence"),
            (self.stored_decoded_media_qa, "decoded_media_qa_presence"),
            (self.stored_semantic_media_qa, "semantic_media_qa_presence"),
            (
                self.stored_postproduction_lineage_qa,
                "postproduction_lineage_qa_presence",
            ),
            (
                self.stored_visual_continuity_qa,
                "visual_continuity_qa_presence",
            ),
        )
        reports: list[
            MediaStructureQAReport
            | DecodedMediaQAReport
            | SemanticMediaQAReport
            | PostproductionLineageQAReport
            | VisualContinuityQAReport
        ] = []
        for loader, repair_code in required_media_qa:
            try:
                reports.append(loader(run_id))
            except ConflictError as exc:
                self._record_postproduction_repair_plan(
                    run,
                    output_seal_sha256=seal.manifest_sha256,
                    master_sha256=master_artifacts[0].sha256,
                    codes=[repair_code],
                )
                raise ConflictError(
                    "production completion requires structure, decoded, semantic, "
                    "postproduction lineage and visual continuity QA"
                ) from exc
        structure_qa, decoded_qa, semantic_qa, lineage_qa, visual_qa = reports
        if (
            structure_qa.status != "PASS"
            or decoded_qa.status != "PASS"
            or semantic_qa.status != "PASS"
            or lineage_qa.status != "PASS"
            or visual_qa.status != "PASS"
        ):
            raise ConflictError("production completion requires all automated media QA to pass")
        if (
            structure_qa.output_seal_sha256 != seal.manifest_sha256
            or decoded_qa.output_seal_sha256 != seal.manifest_sha256
            or semantic_qa.output_seal_sha256 != seal.manifest_sha256
            or lineage_qa.output_seal_sha256 != seal.manifest_sha256
            or visual_qa.output_seal_sha256 != seal.manifest_sha256
        ):
            raise ConflictError("automated media QA reviewed a different output seal")

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
        lock_identity = f"production-run:{episode_id}"
        with self._production_start_lock(lock_identity):
            return self._start_run_locked(episode_id, request, idempotency_key)

    @contextmanager
    def _production_start_lock(self, identity: str) -> Iterator[None]:
        lock_root = self.data_root / "operation-locks"
        secure_directory(lock_root)
        lock_path = lock_root / f"{hashlib.sha256(identity.encode()).hexdigest()}.lock"
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        try:
            secure_file(lock_path)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ConflictError("production request is already in progress") from exc
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _start_run_locked(
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
        try:
            writer_receipt_reconciliation = (
                self.repository.get_writer_receipt_reconciliation(
                    episode.id, episode.approved_script_revision
                )
            )
        except NotFoundError:
            writer_receipt_reconciliation = None
        try:
            writer_provider_reconciliation = (
                self.repository.get_writer_provider_reconciliation(
                    episode.id, episode.approved_script_revision
                )
            )
        except NotFoundError:
            writer_provider_reconciliation = None
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
                    conflict.path
                    for conflict in continuity_preflight.conflicts
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
            if asset.kind in {"character_image", "voice_reference"} and not asset.consent_granted
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

        operation_scope = f"production-run:{episode_id}"
        request_payload = json.dumps(
            {"episode_id": episode_id, "request": request.model_dump(mode="json")},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_sha = hashlib.sha256(request_payload.encode()).hexdigest()
        # Dry-run callers are allowed to omit the public header, but filesystem
        # materialization still needs a durable identity across process crashes.
        # Paid starts were rejected above unless the caller supplied its own key.
        effective_idempotency_key = (
            idempotency_key or f"nalu-internal-dry-run:{request_sha}"
        )
        run_id = new_id("run")
        recovering_pending = False
        run_id, claim_status = self.repository.claim_operation(
            operation_scope, effective_idempotency_key, request_sha, run_id
        )
        if claim_status == "completed":
            return self.repository.get_run(run_id)
        if claim_status == "pending":
            recovering_pending = True
        if claim_status == "failed":
            raise ConflictError("the prior production request failed; inspect its evidence")

        if episode.status != EpisodeStatus.SCRIPT_APPROVED:
            self.repository.finish_operation(
                operation_scope,
                effective_idempotency_key,
                "failed",
                f"episode in {episode.status} cannot start a new production run",
            )
            raise ConflictError(f"episode in {episode.status} cannot start a new production run")

        package = ProductionPackage(
            project=project.model_dump(mode="json"),
            season=season.model_dump(mode="json"),
            episode=episode.model_dump(mode="json"),
            approved_script=script.model_dump(mode="json"),
            writer_receipt_reconciliation=(
                writer_receipt_reconciliation.model_dump(mode="json")
                if writer_receipt_reconciliation is not None
                else None
            ),
            writer_provider_reconciliation=(
                writer_provider_reconciliation.model_dump(mode="json")
                if writer_provider_reconciliation is not None
                else None
            ),
            inherited_assets=[
                asset.model_dump(mode="json", exclude={"consent_granted_by", "consent_statement"})
                for asset in assets
            ],
            resolved_library=resolved_library,
            continuity=continuity.model_dump(mode="json") if continuity else None,
            continuity_preflight=(
                continuity_preflight.model_dump(mode="json") if continuity_preflight else None
            ),
            production_policy={
                "model_policy": policy,
                "requested_model": request.requested_model,
                "dry_run": request.dry_run,
                "paid_generation_approved": request.paid_generation_approved,
                "approved_by": request.approved_by,
                "estimated_budget_credits": request.estimated_budget_credits,
                "paid_submitter_required": True,
                "paid_submitter_authority": self.remote_task_submitter.authority_name,
                "release_fail_closed": True,
            },
        )
        canonical = package.model_dump(mode="json", exclude={"package_sha256"})
        encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        package.package_sha256 = hashlib.sha256(encoded.encode()).hexdigest()

        now = utc_now()
        run_dir = self.data_root / "runs" / run_id
        if recovering_pending:
            if run_dir.is_symlink():
                self.repository.finish_operation(
                    operation_scope,
                    effective_idempotency_key,
                    "failed",
                    "pending production directory is an unsafe symbolic link",
                )
                raise ConflictError("pending production directory is unsafe")
            run_dir.mkdir(parents=True, exist_ok=True)
        else:
            run_dir.mkdir(parents=True, exist_ok=False)
        secure_directory(run_dir)
        package_path = run_dir / "production-package.json"
        staging_path = run_dir / ".production-package.json.pending"
        encoded_package = package.model_dump_json(indent=2) + "\n"
        if recovering_pending and package_path.exists():
            try:
                if package_path.is_symlink() or not package_path.is_file():
                    raise ValueError("package path is not a regular file")
                recovered_package = ProductionPackage.model_validate_json(
                    package_path.read_text(encoding="utf-8")
                )
                if recovered_package.model_dump(mode="json") != package.model_dump(mode="json"):
                    raise ValueError("package content changed")
                unexpected = {
                    path.name
                    for path in run_dir.iterdir()
                    if path.name
                    not in {
                        "production-package.json",
                        "qingshan-workspace",
                        "qingshan-preflight-report.json",
                    }
                }
                if unexpected:
                    raise ValueError("run directory contains unexpected files")
            except (OSError, ValueError) as exc:
                self.repository.finish_operation(
                    operation_scope,
                    effective_idempotency_key,
                    "failed",
                    f"pending production package could not be recovered: {exc}",
                )
                raise ConflictError("pending production package failed recovery verification") from exc
        else:
            if recovering_pending and staging_path.exists():
                try:
                    if staging_path.is_symlink() or not staging_path.is_file():
                        raise ValueError("staged package path is not a regular file")
                    staged_package = ProductionPackage.model_validate_json(
                        staging_path.read_text(encoding="utf-8")
                    )
                    if staged_package.model_dump(mode="json") != package.model_dump(mode="json"):
                        raise ValueError("staged package content changed")
                    if {path.name for path in run_dir.iterdir()} != {staging_path.name}:
                        raise ValueError("staged package directory contains unexpected files")
                    os.replace(staging_path, package_path)
                    secure_file(package_path)
                    self._sync_directory(run_dir)
                except (OSError, ValueError) as exc:
                    self.repository.finish_operation(
                        operation_scope,
                        effective_idempotency_key,
                        "failed",
                        f"staged production package could not be recovered: {exc}",
                    )
                    raise ConflictError(
                        "staged production package failed recovery verification"
                    ) from exc
            else:
                if recovering_pending and any(run_dir.iterdir()):
                    self.repository.finish_operation(
                        operation_scope,
                        effective_idempotency_key,
                        "failed",
                        "pending production directory has content but no immutable package",
                    )
                    raise ConflictError("pending production package is missing")
                self._write_and_promote_package(staging_path, package_path, encoded_package)

        try:
            workspace = self.adapter.materialize_workspace(package_path)
            self.adapter.preflight(package_path, workspace)
        except QingshanAdapterError as exc:
            self.repository.finish_operation(
                operation_scope, effective_idempotency_key, "failed", str(exc)
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
        return self.repository.commit_preflight_run(
            run,
            assets,
            approved_script_revision=episode.approved_script_revision,
            operation_scope=operation_scope,
            idempotency_key=effective_idempotency_key,
        )

    def cancel_run(self, run_id: str, request: RunActionRequest) -> ProductionRun:
        run = self.repository.get_run(run_id)
        if run.status in {RunStatus.COMPLETED, RunStatus.CANCELLED}:
            raise ConflictError(f"run in {run.status} cannot be cancelled")
        return self.repository.transition_run_status_with_event(
            run_id,
            expected_status=run.status,
            target_status=RunStatus.CANCELLED,
            event_type="run_cancelled",
            requested_by=request.requested_by,
            reason=request.reason,
        )

    def resume_run(self, run_id: str, request: RunResumeRequest) -> ProductionRun:
        run = self.repository.get_run(run_id)
        if run.status not in {RunStatus.FAILED, RunStatus.CANCELLED}:
            raise ConflictError("only failed or cancelled runs may be resumed")
        target = RunStatus.PREFLIGHT if request.resume_from_preflight else RunStatus.QUEUED
        if target == RunStatus.QUEUED and not run.dry_run:
            raise ConflictError("paid runs must resume through preflight")
        package_path = Path(run.package_path)
        workspace = package_path.parent / "qingshan-workspace"
        if not workspace.is_dir():
            workspace = self.adapter.materialize_workspace(package_path)
        self.adapter.preflight(package_path, workspace)
        return self.repository.transition_run_status_with_event(
            run_id,
            expected_status=run.status,
            target_status=target,
            event_type="run_resumed",
            requested_by=request.requested_by,
            reason=request.reason,
            error=None,
        )

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
            elif (
                remote_states
                and remote_states
                <= {
                    RemoteTaskState.COMPLETED,
                    RemoteTaskState.CANCELLED,
                }
                and RemoteTaskState.COMPLETED in remote_states
            ):
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
            can_resume=bool(run and run.status in {RunStatus.FAILED, RunStatus.CANCELLED}),
            updated_at=run.updated_at if run else episode.updated_at,
        )

    def season_progress(self, season_id: str) -> list[EpisodeProductionProgress]:
        return [
            self.episode_progress(episode.id)
            for episode in self.repository.list_season_episodes(season_id)
        ]
