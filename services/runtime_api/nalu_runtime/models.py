from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class AudienceMode(StrEnum):
    GENERAL = "general"
    OLDER_ADULT = "older_adult"
    CHILD = "child"
    FAMILY = "family"


class EpisodeStatus(StrEnum):
    PLANNED = "planned"
    SCRIPT_DRAFT = "script_draft"
    SCRIPT_REVIEW = "script_review"
    SCRIPT_APPROVED = "script_approved"
    PREPRODUCTION = "preproduction"
    GENERATING = "generating"
    POSTPRODUCTION = "postproduction"
    QA_REVIEW = "qa_review"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    BLOCKED = "blocked"


class RunStatus(StrEnum):
    CREATED = "created"
    PREFLIGHT = "preflight"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    QUEUED = "queued"
    RUNNING = "running"
    QA_REVIEW = "qa_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AssetKind(StrEnum):
    CHARACTER_IMAGE = "character_image"
    VOICE_REFERENCE = "voice_reference"
    SCENE_REFERENCE = "scene_reference"
    PROP_REFERENCE = "prop_reference"
    STYLE_REFERENCE = "style_reference"
    SOURCE_DOCUMENT = "source_document"


class ConsentScope(StrEnum):
    PROJECT_ONLY = "project_only"
    SERIES = "series"
    UNRESTRICTED = "unrestricted"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    audience_mode: AudienceMode = AudienceMode.GENERAL
    visual_style: str = "warm cinematic realism"
    aspect_ratio: str = Field(default="9:16", pattern=r"^\d+:\d+$")
    planned_episode_count: int = Field(default=1, ge=1, le=500)
    target_episode_seconds: int = Field(default=150, ge=15, le=3600)
    project_bible: dict[str, Any] = Field(default_factory=dict)


class Project(ProjectCreate):
    id: str
    archived_at: str | None = None
    created_at: str
    updated_at: str


class ProjectRename(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class ProjectArchiveRequest(BaseModel):
    archived: bool = True


class ProjectExport(BaseModel):
    schema_version: Literal[
        "nalu.project-export/v1",
        "nalu.project-export/v2",
        "nalu.project-export/v3",
        "nalu.project-export/v4",
    ] = (
        "nalu.project-export/v4"
    )
    exported_at: str
    payload: dict[str, Any]
    payload_sha256: str


class ProjectDeletionPreview(BaseModel):
    project_id: str
    project_title: str
    asset_count: int
    production_run_count: int
    requires_snapshot_deletion_confirmation: bool
    explanation: str


class ProjectDeletionRequest(BaseModel):
    confirmation_title: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    delete_production_snapshots: bool = False


class ProjectDeletionResult(BaseModel):
    project_id: str
    deleted: bool
    removed_asset_count: int
    removed_production_run_count: int
    verified_absent: bool


class SeasonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    season_number: int = Field(ge=1)
    planned_episode_count: int = Field(default=1, ge=1, le=500)
    season_arc: dict[str, Any] = Field(default_factory=dict)


class Season(SeasonCreate):
    id: str
    project_id: str
    plan_revision: int = 0
    approved_plan_revision: int | None = None
    created_at: str
    updated_at: str


class SeasonPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    season_arc: dict[str, Any] | None = None
    source_transcript: str = ""

    @model_validator(mode="after")
    def require_change(self) -> SeasonPlanUpdate:
        if self.title is None and self.season_arc is None:
            raise ValueError("season plan update requires a title or season arc")
        return self


class EpisodePlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    logline: str | None = None
    outline: dict[str, Any] | None = None
    target_seconds: int | None = Field(default=None, ge=15, le=3600)
    source_transcript: str = ""

    @model_validator(mode="after")
    def require_change(self) -> EpisodePlanUpdate:
        if all(
            value is None
            for value in (self.title, self.logline, self.outline, self.target_seconds)
        ):
            raise ValueError("episode plan update requires at least one changed field")
        return self


class SeasonPlanRevision(BaseModel):
    season_id: str
    revision: int
    plan: dict[str, Any]
    source_transcript: str
    created_at: str


class SeasonPlanApprovalCreate(BaseModel):
    approved_by: str = Field(min_length=1)
    spoken_confirmation: str = Field(min_length=1)
    review_channel: Literal["voice", "visual", "voice_and_visual"]
    guardian_approval: bool = False


class SeasonPlanApproval(SeasonPlanApprovalCreate):
    id: str
    season_id: str
    plan_revision: int
    created_at: str


class EpisodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    episode_number: int = Field(ge=1)
    logline: str = ""
    outline: dict[str, Any] = Field(default_factory=dict)
    target_seconds: int = Field(default=150, ge=15, le=3600)


class Episode(EpisodeCreate):
    id: str
    season_id: str
    status: EpisodeStatus
    approved_script_revision: int | None = None
    created_at: str
    updated_at: str


class EpisodeTransitionRequest(BaseModel):
    target_status: EpisodeStatus
    requested_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class EpisodeEvent(BaseModel):
    id: str
    episode_id: str
    sequence: int
    event_type: str
    from_status: EpisodeStatus
    to_status: EpisodeStatus
    requested_by: str
    reason: str
    created_at: str


class ProjectPlanCreate(BaseModel):
    project: ProjectCreate
    season_title: str = Field(default="第一季", min_length=1, max_length=160)
    season_number: int = Field(default=1, ge=1)
    episode_titles: list[str] = Field(default_factory=list, max_length=500)


class ProjectPlan(BaseModel):
    project: Project
    season: Season
    episodes: list[Episode]


class ScriptRevisionCreate(BaseModel):
    content: str = Field(min_length=1)
    summary_for_voice_review: str = Field(min_length=1)
    source_transcript: str = ""
    narrative_metadata: dict[str, Any] = Field(default_factory=dict)


class ScriptRevision(ScriptRevisionCreate):
    episode_id: str
    revision: int
    approved_at: str | None = None
    created_at: str


class ApprovalCreate(BaseModel):
    approved_by: str = Field(min_length=1)
    spoken_confirmation: str = ""
    guardian_approval: bool = False


class ApprovalRevocationCreate(BaseModel):
    requested_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ApprovalRecord(ApprovalCreate):
    id: str
    action_type: str
    project_id: str
    episode_id: str
    script_revision: int
    created_at: str


class AssetBase(BaseModel):
    kind: AssetKind
    name: str = Field(min_length=1, max_length=160)
    local_uri: str = Field(min_length=1)
    subject_name: str = ""
    season_id: str | None = None
    episode_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    consent_granted: bool = False
    consent_scope: ConsentScope = ConsentScope.PROJECT_ONLY
    guardian_approved: bool = False
    consent_granted_by: str = ""
    consent_statement: str = ""


class AssetCreate(AssetBase):

    @model_validator(mode="after")
    def require_biometric_consent(self) -> AssetCreate:
        if self.season_id is not None and self.episode_id is not None:
            raise ValueError("asset cannot have both season and episode scope")
        biometric = {AssetKind.CHARACTER_IMAGE, AssetKind.VOICE_REFERENCE}
        if self.kind in biometric and not self.consent_granted:
            raise ValueError("character and voice assets require explicit consent")
        if self.kind in biometric and (
            not self.consent_granted_by.strip() or not self.consent_statement.strip()
        ):
            raise ValueError("biometric consent requires recorder identity and statement")
        return self


class Asset(AssetBase):
    id: str
    project_id: str
    created_at: str


class AssetConsentRecord(BaseModel):
    id: str
    asset_id: str
    action_type: Literal["granted", "revoked"]
    consent_scope: ConsentScope
    recorded_by: str
    statement: str
    guardian_approved: bool
    created_at: str


class AssetConsentRevocationCreate(BaseModel):
    requested_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class AssetDependencyReport(BaseModel):
    asset_id: str
    can_delete: bool
    production_run_ids: list[str] = Field(default_factory=list)
    explanation: str


class ContinuitySnapshotCreate(BaseModel):
    source_episode_id: str | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    unresolved_hooks: list[str] = Field(default_factory=list)


class ContinuitySnapshot(ContinuitySnapshotCreate):
    id: str
    episode_id: str
    created_at: str


class ProductionRunCreate(BaseModel):
    dry_run: bool = True
    requested_model: str = "seedance-2.0-pro"
    estimated_budget_credits: int | None = Field(default=None, ge=0)
    paid_generation_approved: bool = False
    approved_by: str | None = None

    @model_validator(mode="after")
    def guard_paid_runs(self) -> ProductionRunCreate:
        if not self.dry_run and (not self.paid_generation_approved or not self.approved_by):
            raise ValueError("paid production requires explicit approval and approver identity")
        return self


class ProductionRun(BaseModel):
    id: str
    project_id: str
    season_id: str
    episode_id: str
    status: RunStatus
    dry_run: bool
    requested_model: str
    estimated_budget_credits: int | None
    package_path: str
    error: str | None = None
    created_at: str
    updated_at: str


class EpisodeProductionProgress(BaseModel):
    episode_id: str
    episode_number: int
    title: str
    episode_status: EpisodeStatus
    run_id: str | None = None
    run_status: RunStatus | None = None
    stage: str
    progress_percent: int = Field(ge=0, le=100)
    current_action: str
    explanation: str
    can_cancel: bool = False
    can_resume: bool = False
    updated_at: str


class RunEvent(BaseModel):
    id: str
    run_id: str
    sequence: int
    event_type: str
    from_status: RunStatus | None = None
    to_status: RunStatus | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class RunActionRequest(BaseModel):
    requested_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class RunResumeRequest(RunActionRequest):
    resume_from_preflight: bool = True


class ProductionPackage(BaseModel):
    schema_version: str = "nalu.production-package/v1"
    project: dict[str, Any]
    season: dict[str, Any]
    episode: dict[str, Any]
    approved_script: dict[str, Any]
    inherited_assets: list[dict[str, Any]]
    continuity: dict[str, Any] | None
    production_policy: dict[str, Any]
    package_sha256: str = ""
