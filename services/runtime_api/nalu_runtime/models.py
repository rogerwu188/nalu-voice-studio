from __future__ import annotations

from enum import StrEnum
from typing import Any

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
    created_at: str
    updated_at: str


class SeasonCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    season_number: int = Field(ge=1)
    planned_episode_count: int = Field(default=1, ge=1, le=500)
    season_arc: dict[str, Any] = Field(default_factory=dict)


class Season(SeasonCreate):
    id: str
    project_id: str
    created_at: str
    updated_at: str


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


class AssetCreate(BaseModel):
    kind: AssetKind
    name: str = Field(min_length=1, max_length=160)
    local_uri: str = Field(min_length=1)
    subject_name: str = ""
    episode_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    consent_granted: bool = False
    consent_scope: ConsentScope = ConsentScope.PROJECT_ONLY
    guardian_approved: bool = False

    @model_validator(mode="after")
    def require_biometric_consent(self) -> AssetCreate:
        biometric = {AssetKind.CHARACTER_IMAGE, AssetKind.VOICE_REFERENCE}
        if self.kind in biometric and not self.consent_granted:
            raise ValueError("character and voice assets require explicit consent")
        return self


class Asset(AssetCreate):
    id: str
    project_id: str
    created_at: str


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
