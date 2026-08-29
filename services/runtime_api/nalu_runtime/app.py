from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .database import Database
from .engine import ProductionService
from .models import (
    ApprovalCreate,
    ApprovalRecord,
    Asset,
    AssetCreate,
    ContinuitySnapshot,
    ContinuitySnapshotCreate,
    Episode,
    EpisodeCreate,
    ProductionRun,
    ProductionRunCreate,
    Project,
    ProjectCreate,
    RunActionRequest,
    RunEvent,
    RunResumeRequest,
    ScriptRevision,
    ScriptRevisionCreate,
    Season,
    SeasonCreate,
)
from .repository import ConflictError, NotFoundError, Repository


def create_app(database_path: Path | None = None, data_root: Path | None = None) -> FastAPI:
    repository_root = Path(__file__).resolve().parents[3]
    data_root = data_root or Path(os.environ.get("NALU_DATA_ROOT", repository_root / "data"))
    database_path = database_path or Path(
        os.environ.get("NALU_DATABASE_PATH", data_root / "nalu.sqlite3")
    )
    database = Database(database_path)
    database.initialize()
    repository = Repository(database)
    production = ProductionService(repository, data_root, repository_root)

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

    @app.get("/v1/projects", response_model=list[Project])
    def list_projects() -> list[Project]:
        return repository.list_projects()

    @app.get("/v1/projects/{project_id}", response_model=Project)
    def get_project(project_id: str) -> Project:
        return repository.get_project(project_id)

    @app.post("/v1/projects/{project_id}/seasons", response_model=Season, status_code=201)
    def create_season(project_id: str, request: SeasonCreate) -> Season:
        return repository.create_season(project_id, request)

    @app.get("/v1/projects/{project_id}/seasons", response_model=list[Season])
    def list_seasons(project_id: str) -> list[Season]:
        return repository.list_project_seasons(project_id)

    @app.post("/v1/seasons/{season_id}/episodes", response_model=Episode, status_code=201)
    def create_episode(season_id: str, request: EpisodeCreate) -> Episode:
        return repository.create_episode(season_id, request)

    @app.get("/v1/seasons/{season_id}/episodes", response_model=list[Episode])
    def list_episodes(season_id: str) -> list[Episode]:
        return repository.list_season_episodes(season_id)

    @app.get("/v1/episodes/{episode_id}", response_model=Episode)
    def get_episode(episode_id: str) -> Episode:
        return repository.get_episode(episode_id)

    @app.post(
        "/v1/episodes/{episode_id}/scripts", response_model=ScriptRevision, status_code=201
    )
    def create_script(episode_id: str, request: ScriptRevisionCreate) -> ScriptRevision:
        return repository.create_script(episode_id, request)

    @app.post(
        "/v1/episodes/{episode_id}/scripts/{revision}/approve", response_model=ScriptRevision
    )
    def approve_script(
        episode_id: str, revision: int, approval: ApprovalCreate
    ) -> ScriptRevision:
        episode = repository.get_episode(episode_id)
        season = repository.get_season(episode.season_id)
        project = repository.get_project(season.project_id)
        if project.audience_mode == "child" and not approval.guardian_approval:
            raise HTTPException(status_code=409, detail="child projects require guardian approval")
        return repository.approve_script(episode_id, revision, approval)

    @app.get(
        "/v1/episodes/{episode_id}/script-approvals", response_model=list[ApprovalRecord]
    )
    def list_script_approvals(episode_id: str) -> list[ApprovalRecord]:
        return repository.list_script_approvals(episode_id)

    @app.post("/v1/projects/{project_id}/assets", response_model=Asset, status_code=201)
    def create_asset(project_id: str, request: AssetCreate) -> Asset:
        return repository.create_asset(project_id, request)

    @app.get("/v1/projects/{project_id}/assets", response_model=list[Asset])
    def list_assets(project_id: str, episode_id: str | None = None) -> list[Asset]:
        return repository.list_assets(project_id, episode_id)

    @app.post(
        "/v1/episodes/{episode_id}/continuity-snapshots",
        response_model=ContinuitySnapshot,
        status_code=201,
    )
    def create_continuity(
        episode_id: str, request: ContinuitySnapshotCreate
    ) -> ContinuitySnapshot:
        return repository.create_continuity_snapshot(episode_id, request)

    @app.post(
        "/v1/episodes/{episode_id}/production-runs",
        response_model=ProductionRun,
        status_code=201,
    )
    def start_production(episode_id: str, request: ProductionRunCreate) -> ProductionRun:
        return production.start_run(episode_id, request)

    @app.get("/v1/production-runs/{run_id}", response_model=ProductionRun)
    def get_run(run_id: str) -> ProductionRun:
        return repository.get_run(run_id)

    @app.get("/v1/production-runs/{run_id}/events", response_model=list[RunEvent])
    def get_run_events(run_id: str) -> list[RunEvent]:
        return production.events(run_id)

    @app.post("/v1/production-runs/{run_id}/cancel", response_model=ProductionRun)
    def cancel_run(run_id: str, request: RunActionRequest) -> ProductionRun:
        return production.cancel_run(run_id, request)

    @app.post("/v1/production-runs/{run_id}/resume", response_model=ProductionRun)
    def resume_run(run_id: str, request: RunResumeRequest) -> ProductionRun:
        return production.resume_run(run_id, request)

    return app


app = create_app()
