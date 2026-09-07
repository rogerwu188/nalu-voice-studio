from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Body, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse

from .accepted_episode import AcceptedEpisodeService, EpisodeEditRequest
from .asset_service import AssetService
from .continuity import audit_continuity
from .database import Database
from .development_handoff import (
    DevelopmentHandoffPolicy,
    DevelopmentHandoffReconciliationVerifier,
    DevelopmentHandoffTransport,
    DisabledDevelopmentHandoffReconciliationVerifier,
    DisabledDevelopmentHandoffTransport,
)
from .development_result import (
    DevelopmentResultVerifier,
    DisabledDevelopmentResultVerifier,
)
from .director_refresh import DirectorRefreshRequest, DirectorRefreshService
from .engine import ProductionService
from .episode_audio import EpisodeAudioService, EpisodeAudioTakeRequest
from .episode_audio_review import EpisodeAudioReviewRequest, EpisodeAudioReviewService
from .episode_edit_review import EpisodeEditReviewRequest, EpisodeEditReviewService
from .episode_preview import EpisodePreviewRequest, EpisodePreviewService
from .episode_sound_plan import EpisodeSoundPlanRequest, EpisodeSoundPlanService
from .feedback_export import (
    DisabledIssueTrackerReconciliationVerifier,
    DisabledIssueTrackerTransport,
    FeedbackExportPolicy,
    IssueTrackerReconciliationVerifier,
    IssueTrackerTransport,
)
from .giggle_task_query import GiggleTaskQuery, GiggleTaskQueryError
from .image_budget import ImageBudgetApproval, ImageBudgetService
from .image_download import ImageDownloadError
from .image_materialization import ImageMaterializationService
from .image_observation import ImageObservationService
from .image_preparation import (
    ImagePreparationRequest,
    ImagePreparationService,
    ReviewedReferenceRequest,
    ReviewedShotFrameRequest,
)
from .image_progress import ImageProgressResult, ImageProgressService
from .image_review import ImageReviewRequest, ImageReviewService
from .interactive_story import InteractiveStory, StoryAnswer, StoryInput
from .interactive_writer_service import InteractiveWriterService, WriterGenerationRequest
from .library_snapshot_refresh import LibrarySnapshotRefreshRequest, LibrarySnapshotRefreshService
from .models import (
    ApprovalCreate,
    ApprovalRecord,
    ApprovalRevocationCreate,
    Asset,
    AssetConsentRecord,
    AssetConsentRevocationCreate,
    AssetCreate,
    AssetDependencyReport,
    AssetKind,
    ConsentScope,
    ContinuityExtractionConfirmation,
    ContinuityExtractionConfirmationResult,
    ContinuityExtractionProposal,
    ContinuityPreflightRequest,
    ContinuityPreflightResult,
    ContinuitySnapshot,
    ContinuitySnapshotCreate,
    DecodedMediaQAReport,
    DirectorStrategyRevision,
    DocumentaryReadinessReport,
    Episode,
    EpisodeCreate,
    EpisodeEvent,
    EpisodePlanUpdate,
    EpisodeProductionProgress,
    EpisodeTransitionRequest,
    FeedbackCreate,
    FeedbackDevelopmentHandoffCreate,
    FeedbackDevelopmentHandoffReceipt,
    FeedbackDevelopmentHandoffReconciliationCreate,
    FeedbackDevelopmentHandoffReconciliationRecord,
    FeedbackDevelopmentResultCreate,
    FeedbackDevelopmentResultRecord,
    FeedbackDevelopmentWorkOrder,
    FeedbackDevelopmentWorkOrderCreate,
    FeedbackExternalExportCreate,
    FeedbackExternalExportReceipt,
    FeedbackExternalReconciliationCreate,
    FeedbackExternalReconciliationRecord,
    FeedbackGovernedReleaseReadiness,
    FeedbackItem,
    FeedbackReleaseEvidenceReconciliationCreate,
    FeedbackReleaseEvidenceReconciliationRecord,
    FeedbackReleaseLinkage,
    FeedbackReleaseLinkageCreate,
    FeedbackReviewBundle,
    FeedbackReviewBundleCreate,
    FeedbackTriageCreate,
    FeedbackTriageRecord,
    InheritedContinuityResult,
    LibraryEntity,
    LibraryEntityConfirmation,
    LibraryEntityConfirmationRecord,
    LibraryEntityCreate,
    LibraryEntityResolution,
    LibraryEntityRevision,
    LibraryEntityRevisionCreate,
    LocalVisualAnalysisResult,
    MediaStructureQAReport,
    MemoryCard,
    MemoryCardConfirmation,
    MemoryCardConfirmationRecord,
    MemoryCardCreate,
    MemoryCardRevision,
    MemoryCardUpdate,
    MemoryGraphConflictReport,
    PostproductionLineageQAReport,
    PostproductionMaterializationCreate,
    PostproductionMaterializationResult,
    PostproductionRepairPlan,
    ProductionCompletionRequest,
    ProductionCompletionResult,
    ProductionRouteDecision,
    ProductionRun,
    ProductionRunCreate,
    Project,
    ProjectArchiveRequest,
    ProjectCreate,
    ProjectDeletionPreview,
    ProjectDeletionRequest,
    ProjectDeletionResult,
    ProjectExport,
    ProjectPlan,
    ProjectPlanCreate,
    ProjectRename,
    PublicationDryRun,
    PublicationDryRunCreate,
    PublicationMetricsLearningResult,
    PublicationMetricsSnapshot,
    PublicationMetricsSyncCreate,
    PublicationReconciliationCreate,
    PublicationReconciliationRecord,
    ReleasePackage,
    ReleasePackageCreate,
    RemoteTaskBinding,
    RenderedOutputIntegrityReport,
    RenderedOutputSeal,
    RenderedOutputSealCreate,
    RunActionRequest,
    RunEvent,
    RunResumeRequest,
    ScriptRevision,
    ScriptRevisionCreate,
    Season,
    SeasonCreate,
    SeasonPlanApproval,
    SeasonPlanApprovalCreate,
    SeasonPlanRevision,
    SeasonPlanUpdate,
    SemanticMediaQAReport,
    SemanticMediaQARequest,
    StorageDiagnostics,
    VisualContinuityQAReport,
    WriterProviderReconciliationCreate,
    WriterProviderReconciliationRecord,
    WriterReceiptReconciliation,
)
from .postproduction_materializer import PostproductionMaterializationError
from .privacy_service import ProjectPrivacyService
from .production_authorization import ProductionAuthorizationRequest, ProductionAuthorizationService
from .publication_learning import (
    DisabledPublicationLearningVerifier,
    PublicationLearningVerifier,
)
from .reference_assets import ReferenceAssetConfirmation, ReferenceAssetService
from .release_evidence import (
    DisabledReleaseEvidenceVerifier,
    ReleaseEvidenceVerifier,
)
from .remote_submitter import DurableRemoteTaskSubmitter
from .repository import ConflictError, NotFoundError, Repository
from .reviewed_video import (
    ContinuationPreparationRequest,
    ReviewedVideoRequest,
    ReviewedVideoService,
)
from .semantic_recognizer import LocalSemanticRecognizer
from .shot_character_library import ShotCharacterLibraryRequest, ShotCharacterLibraryService
from .shot_plan_inheritance import ShotPlanInheritanceRequest, ShotPlanInheritanceService
from .shot_planning import ShotPlanningRequest, ShotPlanningService, validate_plan
from .shot_review import ShotReviewRequest, ShotReviewService
from .source_reader import read_public_source, source_failure_code
from .storage_diagnostics import inspect_storage
from .task_observation_service import TaskObservationService
from .video_budget import VideoBudgetApproval, VideoBudgetService
from .video_dispatch import VideoDispatchService
from .video_download import VideoDownloadError
from .video_materialization import VideoMaterializationService
from .video_preparation import VideoPreparationRequest, VideoPreparationService
from .video_pricing import VideoPricingService
from .video_review import VideoReviewRequest, VideoReviewService
from .video_tail import VideoTailService
from .writer_provider import (
    DisabledWriterProviderVerifier,
    WriterProviderVerifier,
)
from .writer_transport import HopsWriterTransport, WriterTransportError


def create_app(
    database_path: Path | None = None,
    data_root: Path | None = None,
    feedback_export_policy: FeedbackExportPolicy | None = None,
    issue_tracker_transport: IssueTrackerTransport | None = None,
    issue_tracker_reconciliation_verifier: IssueTrackerReconciliationVerifier | None = None,
    development_handoff_policy: DevelopmentHandoffPolicy | None = None,
    development_handoff_transport: DevelopmentHandoffTransport | None = None,
    development_handoff_reconciliation_verifier: (
        DevelopmentHandoffReconciliationVerifier | None
    ) = None,
    development_result_verifier: DevelopmentResultVerifier | None = None,
    release_evidence_verifier: ReleaseEvidenceVerifier | None = None,
    publication_learning_verifier: PublicationLearningVerifier | None = None,
    semantic_recognizer: LocalSemanticRecognizer | None = None,
    writer_provider_verifier: WriterProviderVerifier | None = None,
    writer_http_transport: httpx.BaseTransport | None = None,
    task_query_http_transport: httpx.BaseTransport | None = None,
    pricing_http_transport: httpx.BaseTransport | None = None,
    video_http_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    repository_root = Path(
        os.environ.get("NALU_REPOSITORY_ROOT", Path(__file__).resolve().parents[3])
    )
    data_root = data_root or Path(os.environ.get("NALU_DATA_ROOT", repository_root / "data"))
    database_path = database_path or Path(
        os.environ.get("NALU_DATABASE_PATH", data_root / "nalu.sqlite3")
    )
    database = Database(database_path)
    database.initialize()
    repository = Repository(database)
    interactive_story = InteractiveStory(database)
    remote_task_submitter = DurableRemoteTaskSubmitter(repository)
    production = ProductionService(
        repository,
        data_root,
        repository_root,
        remote_task_submitter,
        semantic_recognizer=semantic_recognizer,
    )
    asset_service = AssetService(repository, data_root)
    privacy_service = ProjectPrivacyService(repository, asset_service, data_root)
    if feedback_export_policy is None:
        configured_policy = os.environ.get("NALU_FEEDBACK_EXPORT_POLICY")
        policy_path = (
            Path(configured_policy)
            if configured_policy
            else repository_root / "configs" / "feedback-export.json"
        )
        feedback_export_policy = (
            FeedbackExportPolicy.load(policy_path)
            if policy_path.exists()
            else FeedbackExportPolicy()
        )
    issue_tracker_transport = issue_tracker_transport or DisabledIssueTrackerTransport()
    issue_tracker_reconciliation_verifier = (
        issue_tracker_reconciliation_verifier
        or DisabledIssueTrackerReconciliationVerifier()
    )
    if development_handoff_policy is None:
        configured_handoff_policy = os.environ.get("NALU_DEVELOPMENT_HANDOFF_POLICY")
        handoff_policy_path = (
            Path(configured_handoff_policy)
            if configured_handoff_policy
            else repository_root / "configs" / "development-handoff.json"
        )
        development_handoff_policy = (
            DevelopmentHandoffPolicy.load(handoff_policy_path)
            if handoff_policy_path.exists()
            else DevelopmentHandoffPolicy()
        )
    development_handoff_transport = (
        development_handoff_transport or DisabledDevelopmentHandoffTransport()
    )
    development_handoff_reconciliation_verifier = (
        development_handoff_reconciliation_verifier
        or DisabledDevelopmentHandoffReconciliationVerifier()
    )
    development_result_verifier = (
        development_result_verifier or DisabledDevelopmentResultVerifier()
    )
    release_evidence_verifier = release_evidence_verifier or DisabledReleaseEvidenceVerifier()
    publication_learning_verifier = (
        publication_learning_verifier or DisabledPublicationLearningVerifier()
    )
    writer_provider_verifier = writer_provider_verifier or DisabledWriterProviderVerifier()

    app = FastAPI(
        title="Nalu Voice Studio Runtime API",
        version="0.1.0",
        description="Local project, episode, asset and Qingshan production runtime.",
    )
    app.state.repository = repository
    app.state.production = production
    app.state.remote_task_submitter = remote_task_submitter
    app.state.feedback_export_policy = feedback_export_policy
    app.state.issue_tracker_transport = issue_tracker_transport
    app.state.issue_tracker_reconciliation_verifier = issue_tracker_reconciliation_verifier
    app.state.development_handoff_policy = development_handoff_policy
    app.state.development_handoff_transport = development_handoff_transport
    app.state.development_handoff_reconciliation_verifier = (
        development_handoff_reconciliation_verifier
    )
    app.state.development_result_verifier = development_result_verifier
    app.state.release_evidence_verifier = release_evidence_verifier
    app.state.publication_learning_verifier = publication_learning_verifier
    app.state.writer_provider_verifier = writer_provider_verifier

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(_request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "nalu-runtime",
            "version": "0.1.0",
            "schema_version": str(database.schema_version()),
        }

    @app.get("/v1/diagnostics/storage", response_model=StorageDiagnostics)
    def storage_diagnostics() -> StorageDiagnostics:
        return inspect_storage(data_root, database_path)

    @app.post("/v1/projects", response_model=Project, status_code=201)
    def create_project(request: ProjectCreate) -> Project:
        route_decision = production.adapter_registry.decision(
            request.creative_format.value, request.production_pipeline
        )
        request = request.model_copy(
            update={"production_pipeline": route_decision["resolved_pipeline"]}
        )
        return repository.create_project(request, route_decision)

    @app.get("/v1/projects/{project_id}/interactive-story")
    def get_interactive_story(project_id: str) -> dict:
        return interactive_story.read(project_id)

    @app.get("/v1/projects/{project_id}/source-text")
    def read_source_text(project_id: str, url: str = Query(max_length=4000)) -> dict:
        interactive_story.read(project_id)
        try:
            return read_public_source(url)
        except (ValueError, OSError, LookupError) as exc:
            raise HTTPException(status_code=422, detail={
                "code": source_failure_code(exc),
                "message": "无法读取公开文字来源；请提供可访问的 HTTPS 网页或直接提供文字。",
            }) from exc

    @app.post("/v1/projects/{project_id}/interactive-story/turns")
    def append_story_input(project_id: str, request: StoryInput) -> dict:
        return interactive_story.append(project_id, request)

    @app.post("/v1/projects/{project_id}/interactive-story/turns/{turn_id}/answer")
    def save_story_answer(project_id: str, turn_id: str, request: StoryAnswer) -> dict:
        return interactive_story.answer(project_id, turn_id, request)

    @app.post("/v1/projects/{project_id}/interactive-story/turns/{turn_id}/generate")
    def generate_story_answer(
        project_id: str, turn_id: str, request: WriterGenerationRequest,
        writer_key: str | None = Header(default=None, alias="X-Nalu-Writer-Key"),
        origin: str | None = Header(default=None),
    ) -> dict:
        # Native caller supplies its own Keychain credential transiently. Never
        # read ambient credentials or accept a client-selected destination/body.
        if origin is not None or not writer_key or len(writer_key) > 1024:
            raise HTTPException(403, "native writer credential required")
        try:
            return InteractiveWriterService(database).generate(
                project_id, turn_id, request.expected_revision, model=request.model,
                transport=HopsWriterTransport(lambda: writer_key, transport=writer_http_transport),
            )
        except WriterTransportError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/project-plans", response_model=ProjectPlan, status_code=201)
    def create_project_plan(
        request: ProjectPlanCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ProjectPlan:
        route_decision = production.adapter_registry.decision(
            request.project.creative_format.value,
            request.project.production_pipeline,
        )
        project = request.project.model_copy(
            update={"production_pipeline": route_decision["resolved_pipeline"]}
        )
        request = request.model_copy(update={"project": project})
        return repository.create_project_plan(request, idempotency_key, route_decision)

    @app.get(
        "/v1/projects/{project_id}/production-route",
        response_model=ProductionRouteDecision,
    )
    def get_production_route(project_id: str) -> ProductionRouteDecision:
        decision = repository.get_production_route_decision(project_id)
        if decision is None:
            raise NotFoundError("production route decision not found")
        return decision

    @app.get("/v1/projects", response_model=list[Project])
    def list_projects(include_archived: bool = False) -> list[Project]:
        return repository.list_projects(include_archived)

    @app.post("/v1/feedback", response_model=FeedbackItem, status_code=201)
    def create_feedback(request: FeedbackCreate) -> FeedbackItem:
        return repository.create_feedback(request)

    @app.get("/v1/feedback", response_model=list[FeedbackItem])
    def list_feedback(project_id: str | None = None) -> list[FeedbackItem]:
        return repository.list_feedback(project_id)

    @app.post(
        "/v1/feedback/{feedback_id}/review-bundle",
        response_model=FeedbackReviewBundle,
        status_code=201,
    )
    def create_feedback_review_bundle(
        feedback_id: str, request: FeedbackReviewBundleCreate
    ) -> FeedbackReviewBundle:
        return repository.create_feedback_review_bundle(feedback_id, request)

    @app.get(
        "/v1/feedback/{feedback_id}/review-bundle",
        response_model=FeedbackReviewBundle,
    )
    def get_feedback_review_bundle(feedback_id: str) -> FeedbackReviewBundle:
        return repository.get_feedback_review_bundle(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/triage",
        response_model=FeedbackTriageRecord,
        status_code=201,
    )
    def create_feedback_triage_record(
        feedback_id: str,
        request: FeedbackTriageCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackTriageRecord:
        return repository.create_feedback_triage_record(
            feedback_id, request, idempotency_key
        )

    @app.get(
        "/v1/feedback/{feedback_id}/triage",
        response_model=FeedbackTriageRecord,
    )
    def get_feedback_triage_record(feedback_id: str) -> FeedbackTriageRecord:
        return repository.get_feedback_triage_record(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/external-export",
        response_model=FeedbackExternalExportReceipt,
        status_code=201,
    )
    def export_feedback_to_issue_tracker(
        feedback_id: str,
        request: FeedbackExternalExportCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackExternalExportReceipt:
        return repository.export_feedback_to_issue_tracker(
            feedback_id,
            request,
            idempotency_key,
            feedback_export_policy,
            issue_tracker_transport,
        )

    @app.get(
        "/v1/feedback/{feedback_id}/external-export",
        response_model=FeedbackExternalExportReceipt,
    )
    def get_feedback_external_export(feedback_id: str) -> FeedbackExternalExportReceipt:
        return repository.get_feedback_external_export(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/external-export/reconciliation",
        response_model=FeedbackExternalReconciliationRecord,
        status_code=201,
    )
    def reconcile_feedback_external_export(
        feedback_id: str,
        request: FeedbackExternalReconciliationCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackExternalReconciliationRecord:
        return repository.reconcile_feedback_external_export(
            feedback_id,
            request,
            idempotency_key,
            feedback_export_policy,
            issue_tracker_reconciliation_verifier,
        )

    @app.get(
        "/v1/feedback/{feedback_id}/external-export/reconciliation",
        response_model=FeedbackExternalReconciliationRecord,
    )
    def get_feedback_external_reconciliation(
        feedback_id: str,
    ) -> FeedbackExternalReconciliationRecord:
        return repository.get_feedback_external_reconciliation(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/development-work-order",
        response_model=FeedbackDevelopmentWorkOrder,
        status_code=201,
    )
    def create_feedback_development_work_order(
        feedback_id: str,
        request: FeedbackDevelopmentWorkOrderCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackDevelopmentWorkOrder:
        return repository.create_feedback_development_work_order(
            feedback_id, request, idempotency_key
        )

    @app.get(
        "/v1/feedback/{feedback_id}/development-work-order",
        response_model=FeedbackDevelopmentWorkOrder,
    )
    def get_feedback_development_work_order(
        feedback_id: str,
    ) -> FeedbackDevelopmentWorkOrder:
        return repository.get_feedback_development_work_order(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/development-handoff",
        response_model=FeedbackDevelopmentHandoffReceipt,
        status_code=201,
    )
    def handoff_feedback_to_development(
        feedback_id: str,
        request: FeedbackDevelopmentHandoffCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackDevelopmentHandoffReceipt:
        return repository.handoff_feedback_to_development(
            feedback_id,
            request,
            idempotency_key,
            development_handoff_policy,
            development_handoff_transport,
        )

    @app.get(
        "/v1/feedback/{feedback_id}/development-handoff",
        response_model=FeedbackDevelopmentHandoffReceipt,
    )
    def get_feedback_development_handoff(
        feedback_id: str,
    ) -> FeedbackDevelopmentHandoffReceipt:
        return repository.get_feedback_development_handoff(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/development-handoff/reconciliation",
        response_model=FeedbackDevelopmentHandoffReconciliationRecord,
        status_code=201,
    )
    def reconcile_feedback_development_handoff(
        feedback_id: str,
        request: FeedbackDevelopmentHandoffReconciliationCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackDevelopmentHandoffReconciliationRecord:
        return repository.reconcile_feedback_development_handoff(
            feedback_id,
            request,
            idempotency_key,
            development_handoff_policy,
            development_handoff_reconciliation_verifier,
        )

    @app.get(
        "/v1/feedback/{feedback_id}/development-handoff/reconciliation",
        response_model=FeedbackDevelopmentHandoffReconciliationRecord,
    )
    def get_feedback_development_handoff_reconciliation(
        feedback_id: str,
    ) -> FeedbackDevelopmentHandoffReconciliationRecord:
        return repository.get_feedback_development_handoff_reconciliation(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/development-result",
        response_model=FeedbackDevelopmentResultRecord,
        status_code=201,
    )
    def verify_feedback_development_result(
        feedback_id: str,
        request: FeedbackDevelopmentResultCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackDevelopmentResultRecord:
        return repository.verify_feedback_development_result(
            feedback_id,
            request,
            idempotency_key,
            development_handoff_policy,
            development_result_verifier,
        )

    @app.get(
        "/v1/feedback/{feedback_id}/development-result",
        response_model=FeedbackDevelopmentResultRecord,
    )
    def get_feedback_development_result(
        feedback_id: str,
    ) -> FeedbackDevelopmentResultRecord:
        return repository.get_feedback_development_result(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/release-linkage",
        response_model=FeedbackReleaseLinkage,
        status_code=201,
    )
    def create_feedback_release_linkage(
        feedback_id: str,
        request: FeedbackReleaseLinkageCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackReleaseLinkage:
        return repository.create_feedback_release_linkage(
            feedback_id, request, idempotency_key
        )

    @app.get(
        "/v1/feedback/{feedback_id}/release-linkage",
        response_model=FeedbackReleaseLinkage,
    )
    def get_feedback_release_linkage(feedback_id: str) -> FeedbackReleaseLinkage:
        return repository.get_feedback_release_linkage(feedback_id)

    @app.post(
        "/v1/feedback/{feedback_id}/release-evidence/reconciliation",
        response_model=FeedbackReleaseEvidenceReconciliationRecord,
        status_code=201,
    )
    def reconcile_feedback_release_evidence(
        feedback_id: str,
        request: FeedbackReleaseEvidenceReconciliationCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> FeedbackReleaseEvidenceReconciliationRecord:
        return repository.reconcile_feedback_release_evidence(
            feedback_id,
            request,
            idempotency_key,
            release_evidence_verifier,
        )

    @app.get(
        "/v1/feedback/{feedback_id}/release-evidence/reconciliation",
        response_model=FeedbackReleaseEvidenceReconciliationRecord,
    )
    def get_feedback_release_evidence_reconciliation(
        feedback_id: str,
    ) -> FeedbackReleaseEvidenceReconciliationRecord:
        return repository.get_feedback_release_evidence_reconciliation(feedback_id)

    @app.get(
        "/v1/feedback/{feedback_id}/release-readiness",
        response_model=FeedbackGovernedReleaseReadiness,
    )
    def get_feedback_release_readiness(
        feedback_id: str,
    ) -> FeedbackGovernedReleaseReadiness:
        return repository.feedback_governed_release_readiness(feedback_id)

    @app.post(
        "/v1/projects/{project_id}/memory-cards",
        response_model=MemoryCard,
        status_code=201,
    )
    def create_memory_card(project_id: str, request: MemoryCardCreate) -> MemoryCard:
        return repository.create_memory_card(project_id, request)

    @app.get("/v1/projects/{project_id}/memory-cards", response_model=list[MemoryCard])
    def list_memory_cards(project_id: str, confirmed_only: bool = False) -> list[MemoryCard]:
        return repository.list_memory_cards(project_id, confirmed_only)

    @app.get(
        "/v1/memory-cards/{memory_id}/conflicts",
        response_model=MemoryGraphConflictReport,
    )
    def memory_graph_conflicts(memory_id: str) -> MemoryGraphConflictReport:
        return repository.memory_graph_conflicts(memory_id)

    @app.get(
        "/v1/projects/{project_id}/documentary-readiness",
        response_model=DocumentaryReadinessReport,
    )
    def documentary_readiness(project_id: str) -> DocumentaryReadinessReport:
        return repository.documentary_readiness(project_id)

    @app.patch("/v1/memory-cards/{memory_id}", response_model=MemoryCard)
    def update_memory_card(memory_id: str, request: MemoryCardUpdate) -> MemoryCard:
        return repository.update_memory_card(memory_id, request)

    @app.get(
        "/v1/memory-cards/{memory_id}/revisions",
        response_model=list[MemoryCardRevision],
    )
    def list_memory_card_revisions(memory_id: str) -> list[MemoryCardRevision]:
        return repository.list_memory_card_revisions(memory_id)

    @app.post("/v1/memory-cards/{memory_id}/confirm", response_model=MemoryCard)
    def confirm_memory_card(memory_id: str, request: MemoryCardConfirmation) -> MemoryCard:
        return repository.confirm_memory_card(memory_id, request)

    @app.get(
        "/v1/memory-cards/{memory_id}/confirmations",
        response_model=list[MemoryCardConfirmationRecord],
    )
    def list_memory_card_confirmations(
        memory_id: str,
    ) -> list[MemoryCardConfirmationRecord]:
        return repository.list_memory_card_confirmations(memory_id)

    @app.get("/v1/projects/{project_id}", response_model=Project)
    def get_project(project_id: str) -> Project:
        return repository.get_project(project_id)

    @app.patch("/v1/projects/{project_id}", response_model=Project)
    def rename_project(project_id: str, request: ProjectRename) -> Project:
        return repository.rename_project(project_id, request)

    @app.post("/v1/projects/{project_id}/archive", response_model=Project)
    def archive_project(project_id: str, request: ProjectArchiveRequest) -> Project:
        return repository.archive_project(project_id, request)

    @app.get("/v1/projects/{project_id}/export", response_model=ProjectExport)
    def export_project(project_id: str) -> ProjectExport:
        return repository.export_project(project_id)

    @app.post("/v1/project-imports", response_model=Project, status_code=201)
    def restore_project(backup: ProjectExport) -> Project:
        return repository.restore_project(backup)

    @app.get(
        "/v1/projects/{project_id}/privacy-export",
        response_class=FileResponse,
    )
    def privacy_export(project_id: str) -> FileResponse:
        path = privacy_service.create_privacy_export(project_id)
        return FileResponse(
            path,
            media_type="application/zip",
            filename=f"Nalu-{project_id}-privacy-export.zip",
        )

    @app.get(
        "/v1/projects/{project_id}/deletion-preview",
        response_model=ProjectDeletionPreview,
    )
    def project_deletion_preview(project_id: str) -> ProjectDeletionPreview:
        return repository.project_deletion_preview(project_id)

    @app.delete("/v1/projects/{project_id}", response_model=ProjectDeletionResult)
    def delete_project(project_id: str, request: ProjectDeletionRequest) -> ProjectDeletionResult:
        return privacy_service.delete_project(project_id, request)

    @app.post("/v1/projects/{project_id}/seasons", response_model=Season, status_code=201)
    def create_season(project_id: str, request: SeasonCreate) -> Season:
        return repository.create_season(project_id, request)

    @app.get("/v1/projects/{project_id}/seasons", response_model=list[Season])
    def list_seasons(project_id: str) -> list[Season]:
        return repository.list_project_seasons(project_id)

    @app.patch("/v1/seasons/{season_id}", response_model=Season)
    def update_season_plan(season_id: str, request: SeasonPlanUpdate) -> Season:
        return repository.update_season_plan(season_id, request)

    @app.get(
        "/v1/seasons/{season_id}/plan-revisions",
        response_model=list[SeasonPlanRevision],
    )
    def list_season_plan_revisions(season_id: str) -> list[SeasonPlanRevision]:
        return repository.list_season_plan_revisions(season_id)

    @app.post(
        "/v1/seasons/{season_id}/plan-approvals",
        response_model=SeasonPlanApproval,
        status_code=201,
    )
    def approve_season_plan(
        season_id: str, request: SeasonPlanApprovalCreate
    ) -> SeasonPlanApproval:
        season = repository.get_season(season_id)
        project = repository.get_project(season.project_id)
        if project.audience_mode == "child" and not request.guardian_approval:
            raise HTTPException(status_code=409, detail="child projects require guardian approval")
        return repository.approve_season_plan(season_id, request)

    @app.get(
        "/v1/seasons/{season_id}/plan-approvals",
        response_model=list[SeasonPlanApproval],
    )
    def list_season_plan_approvals(season_id: str) -> list[SeasonPlanApproval]:
        return repository.list_season_plan_approvals(season_id)

    @app.post("/v1/seasons/{season_id}/episodes", response_model=Episode, status_code=201)
    def create_episode(season_id: str, request: EpisodeCreate) -> Episode:
        return repository.create_episode(season_id, request)

    @app.get("/v1/seasons/{season_id}/episodes", response_model=list[Episode])
    def list_episodes(season_id: str) -> list[Episode]:
        return repository.list_season_episodes(season_id)

    @app.get("/v1/episodes/{episode_id}", response_model=Episode)
    def get_episode(episode_id: str) -> Episode:
        return repository.get_episode(episode_id)

    @app.patch("/v1/episodes/{episode_id}", response_model=Episode)
    def update_episode_plan(episode_id: str, request: EpisodePlanUpdate) -> Episode:
        return repository.update_episode_plan(episode_id, request)

    @app.get(
        "/v1/episodes/{episode_id}/production-progress",
        response_model=EpisodeProductionProgress,
    )
    def get_episode_production_progress(episode_id: str) -> EpisodeProductionProgress:
        return production.episode_progress(episode_id)

    @app.get(
        "/v1/seasons/{season_id}/production-progress",
        response_model=list[EpisodeProductionProgress],
    )
    def get_season_production_progress(
        season_id: str,
    ) -> list[EpisodeProductionProgress]:
        return production.season_progress(season_id)

    @app.post("/v1/episodes/{episode_id}/transition", response_model=Episode)
    def transition_episode(episode_id: str, request: EpisodeTransitionRequest) -> Episode:
        return repository.transition_episode(episode_id, request)

    @app.get("/v1/episodes/{episode_id}/events", response_model=list[EpisodeEvent])
    def list_episode_events(episode_id: str) -> list[EpisodeEvent]:
        return repository.list_episode_events(episode_id)

    @app.post("/v1/episodes/{episode_id}/scripts", response_model=ScriptRevision, status_code=201)
    def create_script(episode_id: str, request: ScriptRevisionCreate) -> ScriptRevision:
        return repository.create_script(episode_id, request)

    @app.get("/v1/episodes/{episode_id}/scripts", response_model=list[ScriptRevision])
    def list_scripts(episode_id: str) -> list[ScriptRevision]:
        return repository.list_scripts(episode_id)

    @app.post(
        "/v1/episodes/{episode_id}/scripts/{revision}/writer-receipt-reconciliations",
        response_model=WriterReceiptReconciliation,
        status_code=201,
    )
    def reconcile_writer_receipt(
        episode_id: str,
        revision: int,
        content: Annotated[bytes, Body(media_type="application/octet-stream")],
        reconciled_by: Annotated[str, Query(min_length=1, max_length=160)],
    ) -> WriterReceiptReconciliation:
        return repository.reconcile_writer_receipt(
            episode_id, revision, content, reconciled_by
        )

    @app.get(
        "/v1/episodes/{episode_id}/scripts/{revision}/writer-receipt-reconciliation",
        response_model=WriterReceiptReconciliation,
    )
    def get_writer_receipt_reconciliation(
        episode_id: str, revision: int
    ) -> WriterReceiptReconciliation:
        return repository.get_writer_receipt_reconciliation(episode_id, revision)

    @app.post(
        "/v1/episodes/{episode_id}/scripts/{revision}/writer-provider-reconciliation",
        response_model=WriterProviderReconciliationRecord,
        status_code=201,
    )
    def reconcile_writer_provider(
        episode_id: str,
        revision: int,
        request: WriterProviderReconciliationCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> WriterProviderReconciliationRecord:
        return repository.reconcile_writer_provider(
            episode_id,
            revision,
            request,
            idempotency_key,
            writer_provider_verifier,
        )

    @app.get(
        "/v1/episodes/{episode_id}/scripts/{revision}/writer-provider-reconciliation",
        response_model=WriterProviderReconciliationRecord,
    )
    def get_writer_provider_reconciliation(
        episode_id: str, revision: int
    ) -> WriterProviderReconciliationRecord:
        return repository.get_writer_provider_reconciliation(episode_id, revision)

    @app.post("/v1/episodes/{episode_id}/scripts/{revision}/approve", response_model=ScriptRevision)
    def approve_script(episode_id: str, revision: int, approval: ApprovalCreate) -> ScriptRevision:
        episode = repository.get_episode(episode_id)
        season = repository.get_season(episode.season_id)
        project = repository.get_project(season.project_id)
        if project.audience_mode == "child" and not approval.guardian_approval:
            raise HTTPException(status_code=409, detail="child projects require guardian approval")
        return repository.approve_script(episode_id, revision, approval)

    @app.post(
        "/v1/episodes/{episode_id}/scripts/{revision}/revoke",
        response_model=ScriptRevision,
    )
    def revoke_script_approval(
        episode_id: str, revision: int, request: ApprovalRevocationCreate
    ) -> ScriptRevision:
        return repository.revoke_script_approval(episode_id, revision, request)

    @app.get("/v1/episodes/{episode_id}/script-approvals", response_model=list[ApprovalRecord])
    def list_script_approvals(episode_id: str) -> list[ApprovalRecord]:
        return repository.list_script_approvals(episode_id)

    @app.post("/v1/projects/{project_id}/assets", response_model=Asset, status_code=201)
    def create_asset(project_id: str, request: AssetCreate) -> Asset:
        return asset_service.register_existing(project_id, request)

    @app.post("/v1/projects/{project_id}/asset-imports", response_model=Asset, status_code=201)
    def import_asset(
        project_id: str,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
        kind: AssetKind,
        name: Annotated[str, Query(min_length=1, max_length=160)],
        content: Annotated[bytes, Body(media_type="application/octet-stream")],
        content_type: Annotated[str, Header(alias="Content-Type")],
        subject_name: Annotated[str, Query(max_length=160)] = "",
        season_id: str | None = None,
        episode_id: str | None = None,
        consent_granted: bool = False,
        consent_scope: ConsentScope = ConsentScope.PROJECT_ONLY,
        guardian_approved: bool = False,
        consent_granted_by: Annotated[str, Query(max_length=160)] = "",
        consent_statement: Annotated[str, Query(max_length=1000)] = "",
    ) -> Asset:
        return asset_service.import_bytes(
            project_id,
            content=content,
            filename=filename,
            content_type=content_type,
            kind=kind,
            name=name,
            subject_name=subject_name,
            season_id=season_id,
            episode_id=episode_id,
            consent_granted=consent_granted,
            consent_scope=consent_scope,
            guardian_approved=guardian_approved,
            consent_granted_by=consent_granted_by,
            consent_statement=consent_statement,
        )

    @app.get("/v1/projects/{project_id}/assets", response_model=list[Asset])
    def list_assets(
        project_id: str,
        episode_id: str | None = None,
        season_id: str | None = None,
    ) -> list[Asset]:
        return repository.list_assets(project_id, episode_id, season_id)

    @app.get(
        "/v1/assets/{asset_id}/consent-records",
        response_model=list[AssetConsentRecord],
    )
    def list_asset_consent_records(asset_id: str) -> list[AssetConsentRecord]:
        return repository.list_asset_consent_records(asset_id)

    @app.post(
        "/v1/assets/{asset_id}/consent-revocations",
        response_model=AssetConsentRecord,
        status_code=201,
    )
    def revoke_asset_consent(
        asset_id: str, request: AssetConsentRevocationCreate
    ) -> AssetConsentRecord:
        return repository.revoke_asset_consent(asset_id, request)

    @app.get("/v1/assets/{asset_id}/dependencies", response_model=AssetDependencyReport)
    def asset_dependencies(asset_id: str) -> AssetDependencyReport:
        return repository.asset_dependency_report(asset_id)

    @app.delete("/v1/assets/{asset_id}", status_code=204)
    def delete_asset(asset_id: str) -> Response:
        asset_service.delete_asset(asset_id)
        return Response(status_code=204)

    @app.post(
        "/v1/projects/{project_id}/library-entities",
        response_model=LibraryEntity,
        status_code=201,
    )
    def create_library_entity(project_id: str, request: LibraryEntityCreate) -> LibraryEntity:
        return repository.create_library_entity(project_id, request)

    @app.get(
        "/v1/projects/{project_id}/library-entities",
        response_model=list[LibraryEntity],
    )
    def list_library_entities(project_id: str) -> list[LibraryEntity]:
        return repository.list_library_entities(project_id)

    @app.get(
        "/v1/projects/{project_id}/library-entity-resolution",
        response_model=LibraryEntityResolution,
    )
    def resolve_library_entity(
        project_id: str,
        kind: str = Query(..., pattern="^(character|scene|prop|voice|style)$"),
        mention: str = Query(..., min_length=1, max_length=160),
    ) -> LibraryEntityResolution:
        return repository.resolve_library_entity(project_id, kind, mention)

    @app.get(
        "/v1/library-entities/{entity_id}/revisions",
        response_model=list[LibraryEntityRevision],
    )
    def list_library_revisions(entity_id: str) -> list[LibraryEntityRevision]:
        return repository.list_library_revisions(entity_id)

    @app.post(
        "/v1/library-entities/{entity_id}/revisions",
        response_model=LibraryEntity,
        status_code=201,
    )
    def create_library_revision(
        entity_id: str, request: LibraryEntityRevisionCreate
    ) -> LibraryEntity:
        return repository.create_library_revision(entity_id, request)

    @app.post(
        "/v1/library-entities/{entity_id}/confirmations",
        response_model=LibraryEntityConfirmationRecord,
        status_code=201,
    )
    def confirm_library_entity(
        entity_id: str, request: LibraryEntityConfirmation
    ) -> LibraryEntityConfirmationRecord:
        return repository.confirm_library_entity(entity_id, request)

    @app.post(
        "/v1/episodes/{episode_id}/continuity-snapshots",
        response_model=ContinuitySnapshot,
        status_code=201,
    )
    def create_continuity(episode_id: str, request: ContinuitySnapshotCreate) -> ContinuitySnapshot:
        return repository.create_continuity_snapshot(episode_id, request)

    @app.get(
        "/v1/episodes/{episode_id}/continuity-extraction-proposal",
        response_model=ContinuityExtractionProposal,
    )
    def continuity_extraction_proposal(episode_id: str) -> ContinuityExtractionProposal:
        return repository.continuity_extraction_proposal(episode_id)

    @app.post(
        "/v1/episodes/{episode_id}/continuity-extraction-confirmations",
        response_model=ContinuityExtractionConfirmationResult,
        status_code=201,
    )
    def confirm_continuity_extraction(
        episode_id: str, request: ContinuityExtractionConfirmation
    ) -> ContinuityExtractionConfirmationResult:
        episode = repository.get_episode(episode_id)
        season = repository.get_season(episode.season_id)
        project = repository.get_project(season.project_id)
        if project.audience_mode == "child" and not request.guardian_approval:
            raise HTTPException(
                status_code=409,
                detail="child continuity confirmation requires guardian approval",
            )
        return repository.confirm_continuity_extraction(episode_id, request)

    @app.get(
        "/v1/episodes/{episode_id}/continuity-snapshots",
        response_model=list[ContinuitySnapshot],
    )
    def list_continuity(episode_id: str) -> list[ContinuitySnapshot]:
        return repository.list_continuity_snapshots(episode_id)

    @app.get(
        "/v1/episodes/{episode_id}/inherited-continuity",
        response_model=InheritedContinuityResult,
    )
    def inherited_continuity(episode_id: str) -> InheritedContinuityResult:
        episode = repository.get_episode(episode_id)
        season = repository.get_season(episode.season_id)
        return InheritedContinuityResult(
            snapshot=repository.latest_continuity(season.id, episode.episode_number)
        )

    @app.post(
        "/v1/episodes/{episode_id}/continuity-preflight",
        response_model=ContinuityPreflightResult,
    )
    def continuity_preflight(
        episode_id: str, request: ContinuityPreflightRequest
    ) -> ContinuityPreflightResult:
        episode = repository.get_episode(episode_id)
        season = repository.get_season(episode.season_id)
        project = repository.get_project(season.project_id)
        if (
            project.audience_mode == "child"
            and request.hook_review is not None
            and not request.hook_review.guardian_approval
        ):
            raise HTTPException(
                status_code=409,
                detail="child hook review requires guardian approval",
            )
        inherited = repository.latest_continuity(season.id, episode.episode_number)
        return audit_continuity(inherited, request)

    @app.post(
        "/v1/episodes/{episode_id}/production-runs",
        response_model=ProductionRun,
        status_code=201,
    )
    def start_production(
        episode_id: str,
        request: ProductionRunCreate,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
            description=(
                "Required for paid production. Keyless dry runs receive a stable "
                "server-side recovery identity."
            ),
        ),
    ) -> ProductionRun:
        return production.start_run(episode_id, request, idempotency_key)

    @app.get("/v1/production-runs/{run_id}", response_model=ProductionRun)
    def get_run(run_id: str) -> ProductionRun:
        return repository.get_run(run_id)

    @app.get("/v1/production-runs/{run_id}/events", response_model=list[RunEvent])
    def get_run_events(run_id: str) -> list[RunEvent]:
        return production.events(run_id)

    @app.post("/v1/production-runs/{run_id}/video-task-preparations", response_model=RunEvent)
    def prepare_video_task(run_id: str, request: VideoPreparationRequest) -> RunEvent:
        return VideoPreparationService(repository, data_root).prepare(run_id, request)

    @app.post("/v1/production-runs/{run_id}/shot-plans/{plan_id}/continuation-preparations", response_model=RunEvent)
    def prepare_continuation_video(run_id: str, plan_id: str, request: ContinuationPreparationRequest,
                                   origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native continuation preparation required")
        return ReviewedVideoService(repository, data_root).prepare_continuation(run_id, plan_id, request)

    @app.post("/v1/production-runs/{run_id}/shot-plans/{plan_id}/video-preparations", response_model=RunEvent)
    def prepare_reviewed_video(run_id: str, plan_id: str, request: ReviewedVideoRequest,
                               origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native reviewed-shot selection required")
        return ReviewedVideoService(repository, data_root).prepare(run_id, plan_id, request)

    @app.post("/v1/production-runs/{run_id}/image-task-preparations", response_model=RunEvent)
    def prepare_image_task(run_id: str, request: ImagePreparationRequest) -> RunEvent:
        return ImagePreparationService(repository, asset_service).prepare(run_id, request)

    @app.post("/v1/production-runs/{run_id}/shot-plans/{plan_id}/opening-frame-preparations", response_model=RunEvent)
    def prepare_reviewed_shot_frame(run_id: str, plan_id: str, request: ReviewedShotFrameRequest,
                                    origin: str | None = Header(default=None)) -> RunEvent:
        if origin is not None:
            raise HTTPException(403, "native confirmed-shot selection required")
        return ImagePreparationService(repository, asset_service).prepare_reviewed_shot(run_id, plan_id, request.shot_index)

    @app.post("/v1/production-runs/{run_id}/shot-plans/{plan_id}/reference-image-preparations", response_model=RunEvent)
    def prepare_reviewed_reference(run_id: str, plan_id: str, request: ReviewedReferenceRequest,
                                   origin: str | None = Header(default=None)) -> RunEvent:
        if origin is not None:
            raise HTTPException(403, "native reference selection required")
        return ImagePreparationService(repository, asset_service).prepare_reviewed_reference(run_id, plan_id, request.visual_asset_key)

    @app.post("/v1/production-runs/{run_id}/image-task-preparations/{preparation_id}/estimate-approvals", response_model=RunEvent)
    def approve_image_estimate(run_id: str, preparation_id: str, request: ImageBudgetApproval,
                               origin: str | None = Header(default=None)) -> RunEvent:
        if origin is not None:
            raise HTTPException(403, "native image cost confirmation required")
        return ImageBudgetService(repository, asset_service).reserve(run_id, preparation_id, request)

    @app.get("/v1/production-runs/{run_id}/shot-plans/current", response_model=RunEvent | None)
    def current_shot_plan(run_id: str):
        return ShotReviewService(repository).current(run_id)

    @app.post("/v1/production-runs/{run_id}/shot-plan-inheritance", response_model=RunEvent)
    def inherit_reviewed_shot_plan(run_id: str, request: ShotPlanInheritanceRequest,
                                  origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native snapshot reconciliation required")
        return ShotPlanInheritanceService(repository).inherit(run_id, request)

    @app.post("/v1/production-runs/{run_id}/library-snapshot-refresh", response_model=RunEvent)
    def refresh_confirmed_library(run_id: str, request: LibrarySnapshotRefreshRequest,
                                  origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native confirmed-library refresh required")
        return LibrarySnapshotRefreshService(production).refresh(run_id, request)

    @app.get("/v1/production-runs/{run_id}/library-snapshot-refresh")
    def preview_confirmed_library_refresh(run_id: str):
        return LibrarySnapshotRefreshService(production).preview(run_id)

    @app.post("/v1/production-runs/{run_id}/production-authorization", response_model=RunEvent)
    def authorize_preflight_production(run_id: str, request: ProductionAuthorizationRequest,
                                      origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native explicit production authorization required")
        return ProductionAuthorizationService(production).authorize(run_id, request)

    @app.post("/v1/production-runs/{run_id}/shot-plans/{source_id}/character-cards", response_model=RunEvent)
    def prepare_shot_character_cards(run_id: str, source_id: str, request: ShotCharacterLibraryRequest):
        return ShotCharacterLibraryService(repository).prepare(run_id, source_id, request)

    @app.post("/v1/production-runs/{run_id}/shot-plans/{source_id}/review", response_model=RunEvent)
    def review_shot_plan(run_id: str, source_id: str, request: ShotReviewRequest):
        return ShotReviewService(repository).review(run_id, source_id, request)

    @app.post("/v1/production-runs/{run_id}/shot-plans", response_model=RunEvent)
    def generate_shot_plan(run_id: str, request: ShotPlanningRequest,
                           writer_key: str | None = Header(default=None, alias="X-Nalu-Writer-Key"),
                           origin: str | None = Header(default=None)) -> RunEvent:
        if origin is not None or not writer_key or len(writer_key) > 1024:
            raise HTTPException(403, "native writer credential required")
        try:
            return ShotPlanningService(repository).generate(run_id, model=request.model,
                transport=HopsWriterTransport(lambda: writer_key, transport=writer_http_transport,
                                               response_validator=validate_plan))
        except WriterTransportError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/shot-plans/{source_id}/director-refresh", response_model=RunEvent)
    def refresh_director(run_id: str, source_id: str, request: DirectorRefreshRequest,
                         writer_key: str | None = Header(default=None, alias="X-Nalu-Writer-Key"),
                         origin: str | None = Header(default=None)):
        if origin is not None or not writer_key or len(writer_key) > 1024:
            raise HTTPException(403, "native writer credential required")
        try:
            return DirectorRefreshService(repository).refresh(run_id, source_id, request,
                transport=HopsWriterTransport(lambda: writer_key, transport=writer_http_transport,
                                             response_validator=validate_plan))
        except WriterTransportError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/video-task-preparations/{preparation_id}/estimate-approvals", response_model=RunEvent)
    def approve_video_estimate(run_id: str, preparation_id: str, request: VideoBudgetApproval,
                               origin: str | None = Header(default=None)) -> RunEvent:
        if origin is not None:
            raise HTTPException(403, "native explicit video cost approval required")
        return VideoBudgetService(repository).reserve(run_id, preparation_id, request)

    @app.get("/v1/production-runs/{run_id}/video-reservations/{reservation_id}/submission", response_model=RemoteTaskBinding | None)
    def observe_reserved_video(run_id: str, reservation_id: str):
        return VideoDispatchService(repository, remote_task_submitter).observation(run_id, reservation_id)

    @app.post("/v1/production-runs/{run_id}/video-task-preparations/{preparation_id}/price-observations", response_model=RunEvent)
    def observe_video_price(run_id: str, preparation_id: str) -> RunEvent:
        return VideoPricingService(repository, pricing_http_transport).quote(run_id, preparation_id)

    @app.post("/v1/production-runs/{run_id}/video-reservations/{reservation_id}/submit", response_model=RemoteTaskBinding)
    def submit_reserved_video(run_id: str, reservation_id: str,
                             provider_key: str | None = Header(default=None, alias="X-Nalu-Provider-Key"),
                             origin: str | None = Header(default=None)):
        if (origin is not None or not provider_key or not provider_key.strip() or len(provider_key) > 1024
                or "\r" in provider_key or "\n" in provider_key):
            raise HTTPException(403, "native provider credential required")
        return VideoDispatchService(repository, remote_task_submitter, video_http_transport, data_root=data_root).dispatch(
            run_id, reservation_id, provider_key)

    @app.get("/v1/production-runs/{run_id}/image-results/{materialization_id}/content", response_class=Response,
             responses={200: {"content": {"image/png": {}, "image/jpeg": {}}}})
    def preview_saved_image(run_id: str, materialization_id: str, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native image preview required")
        event, content = ImageMaterializationService(repository, data_root).read_saved(run_id, materialization_id)
        media_type = "image/png" if event.payload["image"]["extension"] == "png" else "image/jpeg"
        return Response(content=content, media_type=media_type,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/v1/production-runs/{run_id}/image-results/{materialization_id}/review", response_model=RunEvent)
    def review_saved_image(run_id: str, materialization_id: str, request: ImageReviewRequest,
                           origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native frame review required")
        return ImageReviewService(repository, asset_service, data_root).review(run_id, materialization_id, request)

    @app.post("/v1/production-runs/{run_id}/reference-reviews/{review_id}/asset", response_model=Asset)
    def register_reference_asset(run_id: str, review_id: str, request: ReferenceAssetConfirmation,
                                 origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native reference permission confirmation required")
        return ReferenceAssetService(repository, asset_service, data_root).register(run_id, review_id, request)

    @app.post("/v1/production-runs/{run_id}/image-observations/{observation_id}/materialize", response_model=RunEvent)
    def materialize_image_result(run_id: str, observation_id: str, result_index: int = Query(default=0, ge=0, le=3),
                                 origin: str | None = Header(default=None)) -> RunEvent:
        if origin is not None:
            raise HTTPException(403, "native image download required")
        try:
            return ImageMaterializationService(repository, data_root).materialize(run_id, observation_id, result_index)
        except ImageDownloadError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/image-tasks/{submission_id}/advance", response_model=ImageProgressResult)
    def advance_saved_image_task(
        run_id: str, submission_id: str,
        provider_key: str | None = Header(default=None, alias="X-Nalu-Provider-Key"),
        origin: str | None = Header(default=None),
    ) -> ImageProgressResult:
        if (origin is not None or not provider_key or not provider_key.strip() or len(provider_key) > 1024
                or "\r" in provider_key or "\n" in provider_key):
            raise HTTPException(403, "native provider credential required")
        try:
            return ImageProgressService(repository, data_root).advance(run_id, submission_id,
                GiggleTaskQuery(lambda: provider_key, transport=task_query_http_transport))
        except (GiggleTaskQueryError, ImageDownloadError) as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/image-tasks/{submission_id}/refresh", response_model=RunEvent)
    def refresh_saved_image_task(
        run_id: str, submission_id: str,
        provider_key: str | None = Header(default=None, alias="X-Nalu-Provider-Key"),
        origin: str | None = Header(default=None),
    ) -> RunEvent:
        if (origin is not None or not provider_key or not provider_key.strip() or len(provider_key) > 1024
                or "\r" in provider_key or "\n" in provider_key):
            raise HTTPException(403, "native provider credential required")
        try:
            return ImageObservationService(repository).refresh(run_id, submission_id,
                GiggleTaskQuery(lambda: provider_key, transport=task_query_http_transport))
        except GiggleTaskQueryError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/tasks/{binding_id}/refresh", response_model=RunEvent)
    def refresh_saved_task(
        run_id: str, binding_id: str,
        provider_key: str | None = Header(default=None, alias="X-Nalu-Provider-Key"),
        origin: str | None = Header(default=None),
    ) -> RunEvent:
        if origin is not None or not provider_key or len(provider_key) > 1024:
            raise HTTPException(403, "native provider credential required")
        try:
            return TaskObservationService(repository).refresh(run_id, binding_id,
                GiggleTaskQuery(lambda: provider_key, transport=task_query_http_transport))
        except GiggleTaskQueryError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/video-observations/{observation_id}/materialize", response_model=RunEvent)
    def materialize_video_result(run_id: str, observation_id: str, result_index: int = Query(default=0, ge=0, le=3),
                                 origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native video retrieval required")
        try:
            return VideoMaterializationService(repository, data_root).materialize(run_id, observation_id, result_index)
        except VideoDownloadError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.post("/v1/production-runs/{run_id}/video-reviews/{review_id}/tail-frame", response_model=RunEvent)
    def extract_video_tail(run_id: str, review_id: str, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native tail extraction required")
        return VideoTailService(repository, data_root).extract(run_id, review_id)

    @app.get("/v1/production-runs/{run_id}/video-tails/{tail_id}/content", response_class=Response,
             responses={200: {"content": {"image/png": {}}}})
    def preview_video_tail(run_id: str, tail_id: str, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native tail preview required")
        _, raw = VideoTailService(repository, data_root).read_saved(run_id, tail_id)
        return Response(content=raw, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/v1/production-runs/{run_id}/video-results/{materialization_id}/reviews", response_model=RunEvent)
    def review_saved_video(run_id: str, materialization_id: str, request: VideoReviewRequest,
                           origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native video review required")
        return VideoReviewService(repository, data_root).review(run_id, materialization_id, request)

    @app.get("/v1/production-runs/{run_id}/video-results/{materialization_id}/content", response_class=Response,
             responses={200: {"content": {"video/mp4": {}}}})
    def preview_saved_video(run_id: str, materialization_id: str, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native video preview required")
        _, raw = VideoMaterializationService(repository, data_root).read_saved(run_id, materialization_id)
        return Response(content=raw, media_type="video/mp4", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    @app.post("/v1/production-runs/{run_id}/sound-plan-drafts", response_model=RunEvent)
    def prepare_episode_sound_plan(run_id: str, request: EpisodeSoundPlanRequest,
                                   origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native sound planning required")
        return EpisodeSoundPlanService(repository, data_root).prepare(run_id, request.expected_plan_sha256,
            edit_id=request.edit_id, expected_edit_sha256=request.expected_edit_sha256,
            expected_edit_review_id=request.expected_edit_review_id)

    @app.post("/v1/production-runs/{run_id}/audio-takes", response_model=RunEvent)
    def attach_episode_audio(run_id: str, request: EpisodeAudioTakeRequest, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native recording attachment required")
        return EpisodeAudioService(repository, data_root).attach(run_id, request)

    @app.get("/v1/production-runs/{run_id}/audio-takes", response_model=list[RunEvent])
    def recover_episode_audio(run_id: str, sound_plan_id: str,
                              expected_sound_plan_sha256: str):
        return EpisodeAudioService(repository, data_root).recover(run_id, sound_plan_id, expected_sound_plan_sha256)

    @app.post("/v1/production-runs/{run_id}/audio-takes/{take_id}/reviews", response_model=RunEvent)
    def review_episode_audio(run_id: str, take_id: str, request: EpisodeAudioReviewRequest,
                             origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native listening confirmation required")
        return EpisodeAudioReviewService(repository, data_root).review(run_id, take_id, request)

    @app.post("/v1/production-runs/{run_id}/episode-edit-drafts/{edit_id}/picture-preview", response_class=Response,
              responses={200: {"content": {"video/mp4": {}}}})
    def preview_episode_edit(run_id: str, edit_id: str, request: EpisodePreviewRequest,
                             origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native picture preview required")
        try:
            raw, sha, receipt_id = EpisodePreviewService(repository, data_root).render(run_id, edit_id, request.expected_edit_sha256)
        except PostproductionMaterializationError as exc:
            raise HTTPException(409, "picture preview could not read or render the current edited sources") from exc
        return Response(content=raw, media_type="video/mp4", headers={"Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff", "X-Nalu-Edit-SHA256": request.expected_edit_sha256,
            "X-Nalu-Preview-SHA256": sha, "X-Nalu-Preview-Receipt-ID": receipt_id,
            "X-Nalu-Preview-Audio": "none", "X-Nalu-Master-Accepted": "false"})

    @app.post("/v1/production-runs/{run_id}/episode-edit-drafts/{edit_id}/reviews", response_model=RunEvent)
    def review_episode_edit(run_id: str, edit_id: str, request: EpisodeEditReviewRequest,
                             origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native edit review required")
        try:
            return EpisodeEditReviewService(repository, data_root).review(run_id, edit_id, request)
        except PostproductionMaterializationError as exc:
            raise HTTPException(409, "edited source changed; reload before confirming") from exc

    @app.post("/v1/production-runs/{run_id}/episode-edit-drafts", response_model=RunEvent)
    def draft_episode_edit(run_id: str, request: EpisodeEditRequest, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native episode editing required")
        return AcceptedEpisodeService(repository, data_root).stage(run_id, request)

    @app.post("/v1/production-runs/{run_id}/accepted-episode-inputs", response_model=RunEvent)
    def stage_accepted_episode(run_id: str, origin: str | None = Header(default=None)):
        if origin is not None:
            raise HTTPException(403, "native episode staging required")
        return AcceptedEpisodeService(repository, data_root).stage(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/postproduction-materializations",
        response_model=PostproductionMaterializationResult,
        status_code=201,
    )
    def materialize_postproduction(
        run_id: str, request: PostproductionMaterializationCreate
    ) -> PostproductionMaterializationResult:
        return production.materialize_postproduction(run_id, request)

    @app.post(
        "/v1/production-runs/{run_id}/local-visual-analysis",
        response_model=LocalVisualAnalysisResult,
        status_code=201,
    )
    def run_local_visual_analysis(run_id: str) -> LocalVisualAnalysisResult:
        return production.run_local_visual_analysis(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/rendered-output-seal",
        response_model=RenderedOutputSeal,
        status_code=201,
    )
    def seal_rendered_outputs(run_id: str, request: RenderedOutputSealCreate) -> RenderedOutputSeal:
        return production.seal_rendered_outputs(run_id, request)

    @app.get(
        "/v1/production-runs/{run_id}/rendered-output-integrity",
        response_model=RenderedOutputIntegrityReport,
    )
    def rendered_output_integrity(run_id: str) -> RenderedOutputIntegrityReport:
        return production.rendered_output_integrity(run_id)

    @app.get(
        "/v1/production-runs/{run_id}/postproduction-repair-plan",
        response_model=PostproductionRepairPlan,
    )
    def postproduction_repair_plan(run_id: str) -> PostproductionRepairPlan:
        return production.postproduction_repair_plan(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/media-structure-qa",
        response_model=MediaStructureQAReport,
    )
    def media_structure_qa(run_id: str) -> MediaStructureQAReport:
        return production.media_structure_qa(run_id)

    @app.get(
        "/v1/production-runs/{run_id}/media-structure-qa",
        response_model=MediaStructureQAReport,
    )
    def stored_media_structure_qa(run_id: str) -> MediaStructureQAReport:
        return production.stored_media_structure_qa(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/decoded-media-qa",
        response_model=DecodedMediaQAReport,
    )
    def decoded_media_qa(run_id: str) -> DecodedMediaQAReport:
        return production.decoded_media_qa(run_id)

    @app.get(
        "/v1/production-runs/{run_id}/decoded-media-qa",
        response_model=DecodedMediaQAReport,
    )
    def stored_decoded_media_qa(run_id: str) -> DecodedMediaQAReport:
        return production.stored_decoded_media_qa(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/postproduction-lineage-qa",
        response_model=PostproductionLineageQAReport,
    )
    def postproduction_lineage_qa(run_id: str) -> PostproductionLineageQAReport:
        return production.postproduction_lineage_qa(run_id)

    @app.get(
        "/v1/production-runs/{run_id}/postproduction-lineage-qa",
        response_model=PostproductionLineageQAReport,
    )
    def stored_postproduction_lineage_qa(
        run_id: str,
    ) -> PostproductionLineageQAReport:
        return production.stored_postproduction_lineage_qa(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/visual-continuity-qa",
        response_model=VisualContinuityQAReport,
    )
    def visual_continuity_qa(run_id: str) -> VisualContinuityQAReport:
        return production.visual_continuity_qa(run_id)

    @app.get(
        "/v1/production-runs/{run_id}/visual-continuity-qa",
        response_model=VisualContinuityQAReport,
    )
    def stored_visual_continuity_qa(run_id: str) -> VisualContinuityQAReport:
        return production.stored_visual_continuity_qa(run_id)

    @app.get(
        "/v1/production-runs/{run_id}/sealed-master",
        response_class=FileResponse,
    )
    def sealed_master(run_id: str) -> FileResponse:
        path, artifact = production.sealed_master_path(run_id)
        return FileResponse(
            path,
            media_type=artifact.media_type,
            filename=Path(artifact.relative_path).name,
            headers={"X-Nalu-Master-SHA256": artifact.sha256},
        )

    @app.post(
        "/v1/production-runs/{run_id}/semantic-media-qa",
        response_model=SemanticMediaQAReport,
    )
    def semantic_media_qa(run_id: str, request: SemanticMediaQARequest) -> SemanticMediaQAReport:
        return production.semantic_media_qa(run_id, request)

    @app.get(
        "/v1/production-runs/{run_id}/semantic-media-qa",
        response_model=SemanticMediaQAReport,
    )
    def stored_semantic_media_qa(run_id: str) -> SemanticMediaQAReport:
        return production.stored_semantic_media_qa(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/release-package",
        response_model=ReleasePackage,
        status_code=201,
    )
    def create_release_package(run_id: str, request: ReleasePackageCreate) -> ReleasePackage:
        return production.create_release_package(run_id, request)

    @app.post(
        "/v1/production-runs/{run_id}/publication-dry-runs",
        response_model=PublicationDryRun,
        status_code=201,
    )
    def create_publication_dry_run(
        run_id: str, request: PublicationDryRunCreate
    ) -> PublicationDryRun:
        return production.create_publication_dry_run(run_id, request)

    @app.get(
        "/v1/production-runs/{run_id}/publication-dry-runs/{platform}",
        response_model=PublicationDryRun,
    )
    def get_publication_dry_run(run_id: str, platform: str) -> PublicationDryRun:
        return production.stored_publication_dry_run(run_id, platform)

    @app.post(
        "/v1/production-runs/{run_id}/publication-reconciliation",
        response_model=PublicationReconciliationRecord,
        status_code=201,
    )
    def reconcile_publication(
        run_id: str,
        request: PublicationReconciliationCreate,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> PublicationReconciliationRecord:
        return production.reconcile_publication(
            run_id, request, idempotency_key, publication_learning_verifier
        )

    @app.get(
        "/v1/production-runs/{run_id}/publication-reconciliation/{platform}",
        response_model=PublicationReconciliationRecord,
    )
    def get_publication_reconciliation(
        run_id: str, platform: str
    ) -> PublicationReconciliationRecord:
        return production.publication_reconciliation(
            run_id,
            platform,
            allow_imported_history_without_local_release=True,
        )

    @app.post(
        "/v1/production-runs/{run_id}/publication-metrics",
        response_model=PublicationMetricsLearningResult,
        status_code=201,
    )
    def sync_publication_metrics(
        run_id: str,
        request: PublicationMetricsSyncCreate,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> PublicationMetricsLearningResult:
        return production.sync_publication_metrics(
            run_id, request, idempotency_key, publication_learning_verifier
        )

    @app.get(
        "/v1/publication-metrics/{metrics_id}",
        response_model=PublicationMetricsSnapshot,
    )
    def get_publication_metrics(metrics_id: str) -> PublicationMetricsSnapshot:
        return repository.get_publication_metrics_snapshot(metrics_id)

    @app.get(
        "/v1/projects/{project_id}/director-strategies",
        response_model=list[DirectorStrategyRevision],
    )
    def list_director_strategies(project_id: str) -> list[DirectorStrategyRevision]:
        return repository.list_director_strategies(project_id)

    @app.post(
        "/v1/production-runs/{run_id}/complete",
        response_model=ProductionCompletionResult,
    )
    def complete_production(
        run_id: str, request: ProductionCompletionRequest
    ) -> ProductionCompletionResult:
        return production.complete_run(run_id, request)

    @app.post("/v1/production-runs/{run_id}/cancel", response_model=ProductionRun)
    def cancel_run(run_id: str, request: RunActionRequest) -> ProductionRun:
        return production.cancel_run(run_id, request)

    @app.post("/v1/production-runs/{run_id}/resume", response_model=ProductionRun)
    def resume_run(run_id: str, request: RunResumeRequest) -> ProductionRun:
        return production.resume_run(run_id, request)

    return app


app = create_app()
