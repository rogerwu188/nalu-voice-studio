from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse

from .asset_service import AssetService
from .continuity import audit_continuity
from .database import Database
from .engine import ProductionService
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
    DocumentaryReadinessReport,
    Episode,
    EpisodeCreate,
    EpisodeEvent,
    EpisodePlanUpdate,
    EpisodeProductionProgress,
    EpisodeTransitionRequest,
    FeedbackCreate,
    FeedbackItem,
    InheritedContinuityResult,
    LibraryEntity,
    LibraryEntityConfirmation,
    LibraryEntityConfirmationRecord,
    LibraryEntityCreate,
    LibraryEntityResolution,
    LibraryEntityRevision,
    LibraryEntityRevisionCreate,
    MemoryCard,
    MemoryCardConfirmation,
    MemoryCardConfirmationRecord,
    MemoryCardCreate,
    MemoryCardRevision,
    MemoryCardUpdate,
    MemoryGraphConflictReport,
    ProductionCompletionRequest,
    ProductionCompletionResult,
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
)
from .privacy_service import ProjectPrivacyService
from .repository import ConflictError, NotFoundError, Repository


def create_app(database_path: Path | None = None, data_root: Path | None = None) -> FastAPI:
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
    production = ProductionService(repository, data_root, repository_root)
    asset_service = AssetService(repository, data_root)
    privacy_service = ProjectPrivacyService(repository, asset_service, data_root)

    app = FastAPI(
        title="Nalu Voice Studio Runtime API",
        version="0.1.0",
        description="Local project, episode, asset and Qingshan production runtime.",
    )
    app.state.repository = repository
    app.state.production = production

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

    @app.post("/v1/projects", response_model=Project, status_code=201)
    def create_project(request: ProjectCreate) -> Project:
        return repository.create_project(request)

    @app.post("/v1/project-plans", response_model=ProjectPlan, status_code=201)
    def create_project_plan(
        request: ProjectPlanCreate,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ProjectPlan:
        return repository.create_project_plan(request, idempotency_key)

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
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ProductionRun:
        return production.start_run(episode_id, request, idempotency_key)

    @app.get("/v1/production-runs/{run_id}", response_model=ProductionRun)
    def get_run(run_id: str) -> ProductionRun:
        return repository.get_run(run_id)

    @app.get("/v1/production-runs/{run_id}/events", response_model=list[RunEvent])
    def get_run_events(run_id: str) -> list[RunEvent]:
        return production.events(run_id)

    @app.post(
        "/v1/production-runs/{run_id}/rendered-output-seal",
        response_model=RenderedOutputSeal,
        status_code=201,
    )
    def seal_rendered_outputs(
        run_id: str, request: RenderedOutputSealCreate
    ) -> RenderedOutputSeal:
        return production.seal_rendered_outputs(run_id, request)

    @app.get(
        "/v1/production-runs/{run_id}/rendered-output-integrity",
        response_model=RenderedOutputIntegrityReport,
    )
    def rendered_output_integrity(run_id: str) -> RenderedOutputIntegrityReport:
        return production.rendered_output_integrity(run_id)

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
