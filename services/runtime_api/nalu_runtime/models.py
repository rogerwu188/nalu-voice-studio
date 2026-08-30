from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class RemoteTaskState(StrEnum):
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    AMBIGUOUS_CHARGE = "ambiguous_charge"
    ZERO_CHARGE_FAILED = "zero_charge_failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssetKind(StrEnum):
    CHARACTER_IMAGE = "character_image"
    VOICE_REFERENCE = "voice_reference"
    ARCHIVE_AUDIO = "archive_audio"
    ARCHIVE_VIDEO = "archive_video"
    SCENE_REFERENCE = "scene_reference"
    PROP_REFERENCE = "prop_reference"
    STYLE_REFERENCE = "style_reference"
    SOURCE_DOCUMENT = "source_document"


class ConsentScope(StrEnum):
    PROJECT_ONLY = "project_only"
    SERIES = "series"
    UNRESTRICTED = "unrestricted"


class CreativeFormat(StrEnum):
    SHORT_DRAMA_SERIES = "short_drama_series"
    ANIMATION_SERIES = "animation_series"
    COMMERCIAL_CAMPAIGN = "commercial_campaign"
    DOCUMENTARY_SERIES = "documentary_series"


class FeedbackCategory(StrEnum):
    USABILITY = "usability"
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    CORRECTION = "correction"
    PREFERENCE = "preference"


class LibraryEntityKind(StrEnum):
    CHARACTER = "character"
    SCENE = "scene"
    PROP = "prop"
    VOICE = "voice"
    STYLE = "style"


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = ""
    audience_mode: AudienceMode = AudienceMode.GENERAL
    visual_style: str = "warm cinematic realism"
    aspect_ratio: str = Field(default="9:16", pattern=r"^\d+:\d+$")
    planned_episode_count: int = Field(default=1, ge=1, le=500)
    target_episode_seconds: int = Field(default=150, ge=15, le=3600)
    project_bible: dict[str, Any] = Field(default_factory=dict)
    creative_format: CreativeFormat = CreativeFormat.SHORT_DRAMA_SERIES
    production_pipeline: str = Field(default="qingshan-short-drama", min_length=1, max_length=120)

    @model_validator(mode="after")
    def fail_closed_for_documentary_route(self) -> ProjectCreate:
        if (
            self.creative_format == CreativeFormat.DOCUMENTARY_SERIES
            and self.production_pipeline != "unassigned"
        ):
            raise ValueError(
                "documentary projects require the unassigned route until a documentary "
                "adapter passes capability and authenticity QA"
            )
        return self


class Project(ProjectCreate):
    id: str
    archived_at: str | None = None
    created_at: str
    updated_at: str


class ProjectRename(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class StorageDiagnostics(BaseModel):
    status: Literal["healthy", "warning", "critical"]
    available_bytes: int = Field(ge=0)
    total_bytes: int = Field(gt=0)
    database_bytes: int = Field(ge=0)
    minimum_production_reserve_bytes: int = Field(gt=0)
    recommended_free_bytes: int = Field(gt=0)
    can_start_new_production: bool
    explanation: str


class ProjectArchiveRequest(BaseModel):
    archived: bool = True


class ProjectExport(BaseModel):
    schema_version: Literal[
        "nalu.project-export/v1",
        "nalu.project-export/v2",
        "nalu.project-export/v3",
        "nalu.project-export/v4",
        "nalu.project-export/v5",
        "nalu.project-export/v6",
        "nalu.project-export/v7",
        "nalu.project-export/v8",
    ] = "nalu.project-export/v8"
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
            value is None for value in (self.title, self.logline, self.outline, self.target_seconds)
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
    project_id: str | None = None
    project: ProjectCreate
    season_title: str = Field(default="第一季", min_length=1, max_length=160)
    season_number: int = Field(default=1, ge=1)
    episode_titles: list[str] = Field(default_factory=list, max_length=500)


class ProjectPlan(BaseModel):
    project: Project
    season: Season
    episodes: list[Episode]


class FeedbackCreate(BaseModel):
    project_id: str | None = None
    category: FeedbackCategory
    message: str = Field(min_length=1, max_length=4000)
    source: Literal["voice", "text"] = "voice"
    screen: str = Field(default="interview", max_length=80)
    share_authorized: bool = False
    guardian_approval: bool = False


class FeedbackItem(FeedbackCreate):
    id: str
    status: Literal["local_only", "ready_for_review"]
    redaction_applied: bool
    created_at: str


class MemoryPerson(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    relationship: str = Field(default="", max_length=160)
    note: str = Field(default="", max_length=1000)


class MemoryCardCreate(BaseModel):
    asset_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10000)
    ocr_text: str = Field(default="", max_length=30000)
    spoken_context: str = Field(default="", max_length=30000)
    approximate_date: str = Field(default="", max_length=160)
    place: str = Field(default="", max_length=300)
    people: list[MemoryPerson] = Field(default_factory=list, max_length=50)
    story_relevance: str = Field(default="", max_length=5000)
    allowed_use: Literal["reference_only", "story_development", "visual_generation"] = (
        "reference_only"
    )


class MemoryCard(MemoryCardCreate):
    id: str
    project_id: str
    current_revision: int
    confirmation_status: Literal["draft", "confirmed"]
    confirmed_by: str = ""
    created_at: str
    updated_at: str


class MemoryCardConfirmation(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=160)
    reviewed_revision: int = Field(ge=1)
    review_channel: Literal["voice", "visual", "voice_and_visual"]
    spoken_confirmation: str = Field(min_length=1, max_length=1000)


class MemoryCardConfirmationRecord(MemoryCardConfirmation):
    id: str
    memory_id: str
    created_at: str


class MemoryCardUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10000)
    ocr_text: str | None = Field(default=None, max_length=30000)
    spoken_context: str | None = Field(default=None, max_length=30000)
    approximate_date: str | None = Field(default=None, max_length=160)
    place: str | None = Field(default=None, max_length=300)
    people: list[MemoryPerson] | None = Field(default=None, max_length=50)
    story_relevance: str | None = Field(default=None, max_length=5000)
    allowed_use: Literal["reference_only", "story_development", "visual_generation"] | None = None
    source_channel: Literal["voice", "visual"]
    change_summary: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_memory_change(self) -> MemoryCardUpdate:
        values = (
            self.title,
            self.description,
            self.ocr_text,
            self.spoken_context,
            self.approximate_date,
            self.place,
            self.people,
            self.story_relevance,
            self.allowed_use,
        )
        if all(value is None for value in values):
            raise ValueError("memory card update requires a changed field")
        return self


class MemoryCardRevision(BaseModel):
    memory_id: str
    revision: int
    content: dict[str, Any]
    source_channel: Literal["voice", "visual", "system"]
    change_summary: str
    created_at: str


class MemoryGraphConflict(BaseModel):
    kind: Literal["relationship", "event_date", "event_place"]
    subject: str
    candidate_value: str
    existing_value: str
    candidate_memory_id: str
    candidate_revision: int
    candidate_asset_id: str
    existing_memory_id: str
    existing_revision: int
    existing_asset_id: str
    explanation: str


class MemoryGraphConflictReport(BaseModel):
    project_id: str
    candidate_memory_id: str
    checked_against_confirmed_cards: int
    blocking: bool
    conflicts: list[MemoryGraphConflict] = Field(default_factory=list)
    spoken_summary: str


class DocumentaryEvidenceItem(BaseModel):
    asset_id: str
    memory_id: str | None = None
    name: str
    kind: AssetKind
    scope: Literal["project", "season", "episode"]
    confirmation_status: Literal["unlinked", "draft", "confirmed"]
    current_revision: int | None = None
    allowed_use: Literal["reference_only", "story_development", "visual_generation"] | None = None
    narrative_authority: bool = False
    visual_generation_authorized: bool = False


class DocumentaryReadinessReport(BaseModel):
    project_id: str
    documentary_mode: Literal["archival_voiceover", "archival_with_reenactment"]
    evidence: list[DocumentaryEvidenceItem] = Field(default_factory=list)
    confirmed_narrative_source_count: int = 0
    draft_or_unlinked_source_count: int = 0
    can_plan_chapters: bool = False
    can_enter_production: bool = False
    generated_reenactment_label_required: bool = False
    blockers: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)


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


class CharacterContinuityState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str | None = None
    wardrobe: list[str] | None = None
    injuries: list[str] | None = None
    held_props: list[str] | None = None
    relationships: dict[str, str] | None = None
    revealed_facts: list[str] | None = None


class PropContinuityState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner: str | None = None
    location: str | None = None
    condition: str | None = None


class ContinuityState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characters: dict[str, CharacterContinuityState] = Field(default_factory=dict)
    props: dict[str, PropContinuityState] = Field(default_factory=dict)
    scene_location: str | None = None
    story_time: str | None = None
    weather: str | None = None


class ContinuityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["nalu.continuity-override/v1"]
    conflict_paths: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)
    reviewed_by: str = Field(min_length=1, max_length=160)
    spoken_confirmation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_explicit_review(self) -> ContinuityOverride:
        cleaned_paths = [path.strip() for path in self.conflict_paths]
        if any(not path for path in cleaned_paths) or len(set(cleaned_paths)) != len(cleaned_paths):
            raise ValueError("continuity override paths must be non-empty and unique")
        confirmation = self.spoken_confirmation
        if not any(word in confirmation for word in ("我确认", "我同意")):
            raise ValueError("continuity override requires explicit confirmation language")
        self.conflict_paths = cleaned_paths
        return self


class ContinuityConflict(BaseModel):
    path: str
    inherited_value: Any
    proposed_value: Any
    explanation: str = ""
    overridden: bool = False


class ContinuityHookResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook: str = Field(min_length=1, max_length=1000)
    disposition: Literal["carry_forward", "resolved", "abandoned"]
    explanation: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def require_closure_explanation(self) -> ContinuityHookResolution:
        self.hook = self.hook.strip()
        self.explanation = self.explanation.strip()
        if self.disposition in {"resolved", "abandoned"} and not self.explanation:
            raise ValueError("resolved or abandoned hooks require an explanation")
        return self


class ContinuityHookReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["nalu.continuity-hook-review/v1"]
    inherited_snapshot_id: str = Field(min_length=1)
    resolutions: list[ContinuityHookResolution] = Field(min_length=1, max_length=100)
    reviewed_by: str = Field(min_length=1, max_length=160)
    spoken_confirmation: str = Field(min_length=1, max_length=1000)
    guardian_approval: bool = False

    @model_validator(mode="after")
    def require_explicit_unique_review(self) -> ContinuityHookReview:
        hooks = [item.hook for item in self.resolutions]
        if len(set(hooks)) != len(hooks):
            raise ValueError("hook review resolutions must be unique")
        if not any(word in self.spoken_confirmation for word in ("我确认", "我同意")):
            raise ValueError("hook review requires explicit confirmation language")
        return self


class ContinuityPreflightRequest(BaseModel):
    opening_state: ContinuityState = Field(default_factory=ContinuityState)
    transition_explanations: dict[str, str] = Field(default_factory=dict)
    override: ContinuityOverride | None = None
    hook_review: ContinuityHookReview | None = None


class ContinuityPreflightResult(BaseModel):
    inherited_snapshot_id: str | None = None
    can_proceed: bool
    conflicts: list[ContinuityConflict] = Field(default_factory=list)
    hook_review_status: Literal[
        "not_required", "missing", "stale", "incomplete", "accepted"
    ] = "not_required"
    hook_resolutions: list[ContinuityHookResolution] = Field(default_factory=list)
    explanation: str


class ContinuitySnapshotCreate(BaseModel):
    source_episode_id: str | None = None
    state: ContinuityState = Field(default_factory=ContinuityState)
    unresolved_hooks: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_end_state_content(self) -> ContinuitySnapshotCreate:
        state = self.state
        has_state = bool(
            state.characters
            or state.props
            or state.scene_location
            or state.story_time
            or state.weather
        )
        if not has_state and not self.unresolved_hooks:
            raise ValueError("continuity snapshot requires end-state content or a hook")
        return self


class ContinuitySnapshot(ContinuitySnapshotCreate):
    id: str
    episode_id: str
    created_at: str


class ContinuityExtractionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=500)
    excerpt: str = Field(min_length=1, max_length=300)
    rule: str = Field(min_length=1, max_length=100)
    confidence: Literal["high", "medium"]


class ContinuityExtractionProposal(BaseModel):
    schema_version: Literal["nalu.continuity-extraction/v1"] = (
        "nalu.continuity-extraction/v1"
    )
    episode_id: str
    script_revision: int
    proposal_sha256: str
    source: Literal[
        "approved_script_metadata",
        "approved_script_markers",
        "approved_script_semantic",
    ]
    state: ContinuityState
    unresolved_hooks: list[str] = Field(default_factory=list)
    extracted_paths: list[str] = Field(default_factory=list)
    evidence: list[ContinuityExtractionEvidence] = Field(default_factory=list)
    spoken_summary: str


class ContinuityExtractionConfirmation(BaseModel):
    reviewed_script_revision: int = Field(ge=1)
    proposal_sha256: str = Field(min_length=64, max_length=64)
    reviewed_state: ContinuityState
    unresolved_hooks: list[str] = Field(default_factory=list)
    confirmed_by: str = Field(min_length=1, max_length=160)
    spoken_confirmation: str = Field(min_length=1, max_length=1000)
    review_channel: Literal["voice", "visual", "voice_and_visual"]
    guardian_approval: bool = False
    change_summary: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_explicit_review_and_content(self) -> ContinuityExtractionConfirmation:
        if not any(
            phrase in self.spoken_confirmation for phrase in ("我确认", "我同意")
        ):
            raise ValueError("continuity extraction requires explicit confirmation language")
        snapshot = ContinuitySnapshotCreate(
            state=self.reviewed_state,
            unresolved_hooks=self.unresolved_hooks,
        )
        self.reviewed_state = snapshot.state
        self.unresolved_hooks = snapshot.unresolved_hooks
        return self


class ContinuityExtractionConfirmationResult(BaseModel):
    snapshot: ContinuitySnapshot
    approval: ApprovalRecord


class InheritedContinuityResult(BaseModel):
    snapshot: ContinuitySnapshot | None = None


class LibraryEntityRevisionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=10000)
    attributes: dict[str, Any] = Field(default_factory=dict)
    source_asset_ids: list[str] = Field(default_factory=list, max_length=100)
    source_memory_ids: list[str] = Field(default_factory=list, max_length=100)
    source_channel: Literal["voice", "visual", "system"]
    change_summary: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_unique_sources(self) -> LibraryEntityRevisionCreate:
        if len(set(self.source_asset_ids)) != len(self.source_asset_ids):
            raise ValueError("library source asset IDs must be unique")
        if len(set(self.source_memory_ids)) != len(self.source_memory_ids):
            raise ValueError("library source memory IDs must be unique")
        return self


class LibraryEntityCreate(LibraryEntityRevisionCreate):
    kind: LibraryEntityKind


class LibraryEntityRevision(LibraryEntityRevisionCreate):
    entity_id: str
    revision: int
    created_at: str


class LibraryEntity(BaseModel):
    id: str
    project_id: str
    kind: LibraryEntityKind
    stable_name: str
    current_revision: int
    confirmed_revision: int | None = None
    current: LibraryEntityRevision
    created_at: str
    updated_at: str


class LibraryEntityConfirmation(BaseModel):
    confirmed_by: str = Field(min_length=1, max_length=160)
    reviewed_revision: int = Field(ge=1)
    review_channel: Literal["voice", "visual", "voice_and_visual"]
    spoken_confirmation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_explicit_confirmation(self) -> LibraryEntityConfirmation:
        if not any(word in self.spoken_confirmation for word in ("我确认", "我同意")):
            raise ValueError("library confirmation requires explicit confirmation language")
        return self


class LibraryEntityConfirmationRecord(LibraryEntityConfirmation):
    id: str
    entity_id: str
    created_at: str


class LibraryEntityResolution(BaseModel):
    mention: str
    normalized_mention: str
    entity_id: str
    kind: LibraryEntityKind
    confirmed_revision: int
    matched_by: Literal["stable_name", "alias"]


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


class RemoteTaskBinding(BaseModel):
    id: str
    run_id: str
    task_key: str
    provider: str
    model: str
    submission_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: RemoteTaskState
    provider_task_id: str | None = None
    response_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    result_uri: str | None = None
    receipt: dict[str, Any] = Field(default_factory=dict)
    charge_classification: str = ""
    actual_charged_credits: int | None = Field(default=None, ge=0)
    created_at: str
    updated_at: str


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
    resolved_library: list[dict[str, Any]] = Field(default_factory=list)
    continuity: dict[str, Any] | None
    continuity_preflight: dict[str, Any] | None = None
    production_policy: dict[str, Any]
    package_sha256: str = ""


class RenderedOutputCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "master_video",
        "audio_master",
        "captions",
        "cover",
        "qa_report",
        "release_metadata",
    ]
    relative_path: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_safe_relative_path(self) -> RenderedOutputCandidate:
        path = self.relative_path.replace("\\", "/")
        parts = path.split("/")
        if path.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("rendered output path must be a safe relative path")
        self.relative_path = path
        return self


class RenderedOutputSealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifacts: list[RenderedOutputCandidate] = Field(min_length=1, max_length=50)
    sealed_by: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_unique_master_and_paths(self) -> RenderedOutputSealCreate:
        paths = [artifact.relative_path for artifact in self.artifacts]
        if len(set(paths)) != len(paths):
            raise ValueError("rendered output paths must be unique")
        if sum(artifact.kind == "master_video" for artifact in self.artifacts) != 1:
            raise ValueError("rendered output seal requires exactly one master video")
        return self


class RenderedOutputArtifact(RenderedOutputCandidate):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_size: int = Field(ge=1)


class RenderedOutputSeal(BaseModel):
    schema_version: Literal["nalu.rendered-output-seal/v1"] = (
        "nalu.rendered-output-seal/v1"
    )
    run_id: str
    project_id: str
    episode_id: str
    production_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    resolved_library_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifacts: list[RenderedOutputArtifact]
    sealed_by: str
    sealed_at: str
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class RenderedOutputIntegrityReport(BaseModel):
    seal: RenderedOutputSeal
    integrity_ok: bool
    failures: list[str] = Field(default_factory=list)


class FinalQAEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["nalu.final-qa-evidence/v1"]
    run_id: str = Field(min_length=1)
    master_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_resolution_reviewed: bool
    picture_passed: bool
    audio_sync_passed: bool
    captions_passed: bool
    continuity_passed: bool
    safety_passed: bool
    reviewed_by: str = Field(min_length=1, max_length=160)
    review_channel: Literal["human_original_resolution"]
    reviewed_at: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def require_every_release_check(self) -> FinalQAEvidence:
        checks = (
            self.original_resolution_reviewed,
            self.picture_passed,
            self.audio_sync_passed,
            self.captions_passed,
            self.continuity_passed,
            self.safety_passed,
        )
        if not all(checks):
            raise ValueError("final QA evidence requires every release check to pass")
        return self


class PostproductionRepairTask(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=160)
    issue: str = Field(min_length=1, max_length=1000)
    required_action: str = Field(min_length=1, max_length=2000)
    release_blocking: Literal[True] = True


class PostproductionRepairPlan(BaseModel):
    schema_version: Literal["nalu.postproduction-repair-plan/v1"] = (
        "nalu.postproduction-repair-plan/v1"
    )
    run_id: str
    output_seal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    master_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_qa_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    repair_tasks: list[PostproductionRepairTask] = Field(min_length=1)
    created_at: str
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class MediaStructureQAReport(BaseModel):
    schema_version: Literal["nalu.media-structure-qa/v1"] = "nalu.media-structure-qa/v1"
    run_id: str
    output_seal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    master_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    captions_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mp4: dict[str, Any]
    captions: dict[str, Any]
    status: Literal["PASS", "FAIL"]
    failures: list[str] = Field(default_factory=list)
    created_at: str
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReleasePackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    prepared_by: str = Field(min_length=1, max_length=160)


class ReleasePackage(BaseModel):
    schema_version: Literal["nalu.release-package/v1"] = "nalu.release-package/v1"
    run_id: str
    project_id: str
    episode_id: str
    output_seal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_qa_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str
    description: str
    artifacts: list[RenderedOutputArtifact]
    prepared_by: str
    prepared_at: str
    publishing_enabled: Literal[False] = False
    platform_approvals: list[dict[str, Any]] = Field(default_factory=list)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PublicationDryRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Literal["youtube", "bilibili"]
    confirmed_platform: Literal["youtube", "bilibili"]
    channel_reference: str = Field(min_length=1, max_length=300)
    approved_by: str = Field(min_length=1, max_length=160)
    spoken_confirmation: str = Field(min_length=1, max_length=1000)
    guardian_approval: bool = False

    @model_validator(mode="after")
    def require_platform_specific_confirmation(self) -> PublicationDryRunCreate:
        if self.confirmed_platform != self.platform:
            raise ValueError("confirmed platform must match the requested platform")
        if not any(phrase in self.spoken_confirmation for phrase in ("我确认", "我同意")):
            raise ValueError("publication dry-run requires explicit confirmation language")
        return self


class PlatformPublicationApproval(BaseModel):
    platform: Literal["youtube", "bilibili"]
    channel_reference: str
    approved_by: str
    spoken_confirmation: str
    guardian_approval: bool
    approved_at: str
    approval_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PublicationDryRun(BaseModel):
    schema_version: Literal["nalu.publication-dry-run/v1"] = (
        "nalu.publication-dry-run/v1"
    )
    id: str
    run_id: str
    project_id: str
    episode_id: str
    release_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    platform: Literal["youtube", "bilibili"]
    adapter_version: str
    approval: PlatformPublicationApproval
    duplicate_guard_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    compiled_plan: dict[str, Any]
    dry_run: Literal[True] = True
    network_call_performed: Literal[False] = False
    episode_state_changed: Literal[False] = False
    created_at: str
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProductionCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_seal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_by: str = Field(min_length=1, max_length=160)
    spoken_confirmation: str = Field(min_length=1, max_length=1000)
    guardian_approval: bool = False

    @model_validator(mode="after")
    def require_explicit_completion(self) -> ProductionCompletionRequest:
        if not any(phrase in self.spoken_confirmation for phrase in ("我确认", "我同意")):
            raise ValueError("production completion requires explicit confirmation language")
        return self


class ProductionCompletionResult(BaseModel):
    run: ProductionRun
    episode: Episode
    output_seal_sha256: str
    qa_report_sha256: str
