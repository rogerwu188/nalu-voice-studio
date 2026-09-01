from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .continuity import ending_hooks_match_review
from .continuity_extraction import extract_semantic_ending_continuity
from .database import Database
from .models import (
    ApprovalCreate,
    ApprovalRecord,
    ApprovalRevocationCreate,
    Asset,
    AssetConsentRecord,
    AssetConsentRevocationCreate,
    AssetCreate,
    AssetDependencyReport,
    ContinuityExtractionConfirmation,
    ContinuityExtractionConfirmationResult,
    ContinuityExtractionProposal,
    ContinuityHookReview,
    ContinuitySnapshot,
    ContinuitySnapshotCreate,
    ContinuityState,
    DocumentaryEvidenceItem,
    DocumentaryReadinessReport,
    Episode,
    EpisodeCreate,
    EpisodeEvent,
    EpisodePlanUpdate,
    EpisodeStatus,
    EpisodeTransitionRequest,
    FeedbackCreate,
    FeedbackItem,
    FeedbackReleaseLinkage,
    FeedbackReleaseLinkageCreate,
    FeedbackReviewBundle,
    FeedbackReviewBundleCreate,
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
    MemoryGraphConflict,
    MemoryGraphConflictReport,
    ProductionRun,
    Project,
    ProjectArchiveRequest,
    ProjectCreate,
    ProjectDeletionPreview,
    ProjectDeletionRequest,
    ProjectExport,
    ProjectPlan,
    ProjectPlanCreate,
    ProjectRename,
    RemoteTaskBinding,
    RemoteTaskState,
    RunEvent,
    RunStatus,
    ScriptRevision,
    ScriptRevisionCreate,
    Season,
    SeasonCreate,
    SeasonPlanApproval,
    SeasonPlanApprovalCreate,
    SeasonPlanRevision,
    SeasonPlanUpdate,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def decode(value: str) -> Any:
    return json.loads(value)


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


EPISODE_TRANSITIONS: dict[EpisodeStatus, set[EpisodeStatus]] = {
    EpisodeStatus.PLANNED: {EpisodeStatus.SCRIPT_REVIEW, EpisodeStatus.BLOCKED},
    EpisodeStatus.SCRIPT_DRAFT: {EpisodeStatus.SCRIPT_REVIEW, EpisodeStatus.BLOCKED},
    EpisodeStatus.SCRIPT_REVIEW: {EpisodeStatus.SCRIPT_APPROVED, EpisodeStatus.BLOCKED},
    EpisodeStatus.SCRIPT_APPROVED: {
        EpisodeStatus.SCRIPT_REVIEW,
        EpisodeStatus.PREPRODUCTION,
        EpisodeStatus.BLOCKED,
    },
    EpisodeStatus.PREPRODUCTION: {EpisodeStatus.GENERATING, EpisodeStatus.BLOCKED},
    EpisodeStatus.GENERATING: {EpisodeStatus.POSTPRODUCTION, EpisodeStatus.BLOCKED},
    EpisodeStatus.POSTPRODUCTION: {EpisodeStatus.QA_REVIEW, EpisodeStatus.BLOCKED},
    EpisodeStatus.QA_REVIEW: {EpisodeStatus.READY_TO_PUBLISH, EpisodeStatus.BLOCKED},
    EpisodeStatus.READY_TO_PUBLISH: {EpisodeStatus.PUBLISHED, EpisodeStatus.BLOCKED},
    EpisodeStatus.PUBLISHED: set(),
    EpisodeStatus.BLOCKED: {
        EpisodeStatus.SCRIPT_REVIEW,
        EpisodeStatus.PREPRODUCTION,
        EpisodeStatus.GENERATING,
        EpisodeStatus.POSTPRODUCTION,
        EpisodeStatus.QA_REVIEW,
    },
}

EDITABLE_EPISODE_PLAN_STATUSES = {
    EpisodeStatus.PLANNED,
    EpisodeStatus.SCRIPT_DRAFT,
    EpisodeStatus.SCRIPT_REVIEW,
}


class Repository:
    def __init__(self, database: Database):
        self.db = database
        self.__remote_task_write_authority: object | None = None

    def _bind_remote_task_submitter(self) -> object:
        """Bind exactly one in-process authority for paid remote-task writes."""
        if self.__remote_task_write_authority is not None:
            raise RuntimeError("the durable remote task submitter is already bound")
        self.__remote_task_write_authority = object()
        return self.__remote_task_write_authority

    def _require_remote_task_write_authority(self, authority: object) -> None:
        if (
            self.__remote_task_write_authority is None
            or authority is not self.__remote_task_write_authority
        ):
            raise PermissionError("remote task writes require the bound durable submitter")

    def create_project(self, request: ProjectCreate) -> Project:
        project_id, now = new_id("prj"), utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO projects (
                   id, title, description, audience_mode, visual_style, aspect_ratio,
                   planned_episode_count, target_episode_seconds, project_bible_json,
                   creative_format, production_pipeline, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    request.title,
                    request.description,
                    request.audience_mode,
                    request.visual_style,
                    request.aspect_ratio,
                    request.planned_episode_count,
                    request.target_episode_seconds,
                    encode(request.project_bible),
                    request.creative_format,
                    request.production_pipeline,
                    now,
                    now,
                ),
            )
        return self.get_project(project_id)

    def claim_operation(
        self,
        scope: str,
        idempotency_key: str,
        request_sha256: str,
        resource_id: str,
    ) -> tuple[str, str]:
        """Atomically reserve a retryable mutation or return its prior resource."""
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT request_sha256, resource_id, status FROM idempotent_operations
                   WHERE scope = ? AND idempotency_key = ?""",
                (scope, idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != request_sha256:
                    raise ConflictError("idempotency key was already used for another request")
                return existing["resource_id"], existing["status"]
            connection.execute(
                "INSERT INTO idempotent_operations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scope,
                    idempotency_key,
                    request_sha256,
                    resource_id,
                    "pending",
                    None,
                    now,
                    now,
                ),
            )
        return resource_id, "claimed"

    def finish_operation(
        self,
        scope: str,
        idempotency_key: str,
        status: str,
        error: str | None = None,
    ) -> None:
        if status not in {"completed", "failed"}:
            raise ValueError("operation status must be completed or failed")
        with self.db.connect() as connection:
            connection.execute(
                """UPDATE idempotent_operations
                   SET status = ?, error = ?, updated_at = ?
                   WHERE scope = ? AND idempotency_key = ?""",
                (status, error, utc_now(), scope, idempotency_key),
            )

    def create_project_plan(
        self, request: ProjectPlanCreate, idempotency_key: str | None = None
    ) -> ProjectPlan:
        """Create or finalize a draft project with its first season atomically."""
        canonical_request = request.model_dump_json(exclude_none=True)
        request_sha = hashlib.sha256(canonical_request.encode()).hexdigest()
        project_id = request.project_id or new_id("prj")
        season_id, now = new_id("sea"), utc_now()
        episode_count = request.project.planned_episode_count
        titles = request.episode_titles or [
            f"第{number}集" for number in range(1, episode_count + 1)
        ]
        if len(titles) != episode_count or any(not title.strip() for title in titles):
            raise ConflictError("episode titles must match planned episode count")
        episode_ids: list[str] = []
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                existing = connection.execute(
                    """SELECT request_sha256, response_json FROM idempotency_records
                       WHERE scope = ? AND idempotency_key = ?""",
                    ("project-plan", idempotency_key),
                ).fetchone()
                if existing:
                    if existing["request_sha256"] != request_sha:
                        raise ConflictError("idempotency key was already used for another request")
                    return ProjectPlan.model_validate_json(existing["response_json"])
            created_at = now
            if request.project_id:
                existing_project = connection.execute(
                    "SELECT created_at FROM projects WHERE id = ?", (project_id,)
                ).fetchone()
                if existing_project is None:
                    raise ConflictError("draft project does not exist")
                existing_season = connection.execute(
                    "SELECT id FROM seasons WHERE project_id = ? LIMIT 1", (project_id,)
                ).fetchone()
                if existing_season is not None:
                    raise ConflictError("draft project has already been finalized")
                created_at = existing_project["created_at"]
                connection.execute(
                    """UPDATE projects SET
                       title = ?, description = ?, audience_mode = ?, visual_style = ?,
                       aspect_ratio = ?, planned_episode_count = ?,
                       target_episode_seconds = ?, project_bible_json = ?,
                       creative_format = ?, production_pipeline = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        request.project.title,
                        request.project.description,
                        request.project.audience_mode,
                        request.project.visual_style,
                        request.project.aspect_ratio,
                        episode_count,
                        request.project.target_episode_seconds,
                        encode(request.project.project_bible),
                        request.project.creative_format,
                        request.project.production_pipeline,
                        now,
                        project_id,
                    ),
                )
            else:
                connection.execute(
                    """INSERT INTO projects (
                       id, title, description, audience_mode, visual_style, aspect_ratio,
                       planned_episode_count, target_episode_seconds, project_bible_json,
                       creative_format, production_pipeline, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        project_id,
                        request.project.title,
                        request.project.description,
                        request.project.audience_mode,
                        request.project.visual_style,
                        request.project.aspect_ratio,
                        episode_count,
                        request.project.target_episode_seconds,
                        encode(request.project.project_bible),
                        request.project.creative_format,
                        request.project.production_pipeline,
                        now,
                        now,
                    ),
                )
            connection.execute(
                "INSERT INTO seasons VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    season_id,
                    project_id,
                    request.season_title,
                    request.season_number,
                    episode_count,
                    encode({}),
                    now,
                    now,
                ),
            )
            for number, title in enumerate(titles, start=1):
                episode_id = new_id("ep")
                episode_ids.append(episode_id)
                connection.execute(
                    "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        episode_id,
                        season_id,
                        title.strip(),
                        number,
                        "等待和用户一起完善",
                        encode({}),
                        request.project.target_episode_seconds,
                        EpisodeStatus.PLANNED,
                        None,
                        now,
                        now,
                    ),
                )
            self._snapshot_season_plan(connection, season_id, "")
            plan = ProjectPlan(
                project=Project(
                    id=project_id,
                    **request.project.model_dump(),
                    created_at=created_at,
                    updated_at=now,
                ),
                season=Season(
                    id=season_id,
                    project_id=project_id,
                    title=request.season_title,
                    season_number=request.season_number,
                    planned_episode_count=episode_count,
                    season_arc={},
                    plan_revision=1,
                    created_at=now,
                    updated_at=now,
                ),
                episodes=[
                    Episode(
                        id=episode_id,
                        season_id=season_id,
                        title=title.strip(),
                        episode_number=number,
                        logline="等待和用户一起完善",
                        outline={},
                        target_seconds=request.project.target_episode_seconds,
                        status=EpisodeStatus.PLANNED,
                        created_at=now,
                        updated_at=now,
                    )
                    for number, (episode_id, title) in enumerate(
                        zip(episode_ids, titles, strict=True), start=1
                    )
                ],
            )
            if idempotency_key:
                connection.execute(
                    "INSERT INTO idempotency_records VALUES (?, ?, ?, ?, ?)",
                    (
                        "project-plan",
                        idempotency_key,
                        request_sha,
                        plan.model_dump_json(),
                        now,
                    ),
                )
        return plan

    def get_project(self, project_id: str) -> Project:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("project not found")
        data = dict(row)
        data["project_bible"] = decode(data.pop("project_bible_json"))
        return Project.model_validate(data)

    def rename_project(self, project_id: str, request: ProjectRename) -> Project:
        self.get_project(project_id)
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE projects SET title = ?, updated_at = ? WHERE id = ?",
                (request.title, utc_now(), project_id),
            )
        return self.get_project(project_id)

    def archive_project(self, project_id: str, request: ProjectArchiveRequest) -> Project:
        self.get_project(project_id)
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE projects SET archived_at = ?, updated_at = ? WHERE id = ?",
                (now if request.archived else None, now, project_id),
            )
        return self.get_project(project_id)

    def list_projects(self, include_archived: bool = False) -> list[Project]:
        with self.db.connect() as connection:
            query = "SELECT id FROM projects"
            if not include_archived:
                query += " WHERE archived_at IS NULL"
            query += " ORDER BY created_at"
            ids = [row["id"] for row in connection.execute(query)]
        return [self.get_project(project_id) for project_id in ids]

    def export_project(self, project_id: str) -> ProjectExport:
        self.get_project(project_id)
        queries = {
            "projects": ("SELECT * FROM projects WHERE id = ?", (project_id,)),
            "seasons": ("SELECT * FROM seasons WHERE project_id = ?", (project_id,)),
            "episodes": (
                """SELECT e.* FROM episodes e JOIN seasons s ON s.id = e.season_id
                   WHERE s.project_id = ?""",
                (project_id,),
            ),
            "season_plan_revisions": (
                """SELECT r.* FROM season_plan_revisions r
                   JOIN seasons s ON s.id = r.season_id WHERE s.project_id = ?""",
                (project_id,),
            ),
            "season_plan_approval_records": (
                """SELECT a.* FROM season_plan_approval_records a
                   JOIN seasons s ON s.id = a.season_id WHERE s.project_id = ?""",
                (project_id,),
            ),
            "script_revisions": (
                """SELECT r.* FROM script_revisions r
                   JOIN episodes e ON e.id = r.episode_id
                   JOIN seasons s ON s.id = e.season_id WHERE s.project_id = ?""",
                (project_id,),
            ),
            "assets": ("SELECT * FROM assets WHERE project_id = ?", (project_id,)),
            "asset_consent_records": (
                """SELECT r.* FROM asset_consent_records r
                   JOIN assets a ON a.id = r.asset_id WHERE a.project_id = ?""",
                (project_id,),
            ),
            "continuity_snapshots": (
                """SELECT c.* FROM continuity_snapshots c
                   JOIN episodes e ON e.id = c.episode_id
                   JOIN seasons s ON s.id = e.season_id WHERE s.project_id = ?""",
                (project_id,),
            ),
            "approval_records": (
                "SELECT * FROM approval_records WHERE project_id = ?",
                (project_id,),
            ),
            "continuity_extraction_confirmation_records": (
                """SELECT c.* FROM continuity_extraction_confirmation_records c
                   JOIN episodes e ON e.id = c.episode_id
                   JOIN seasons s ON s.id = e.season_id WHERE s.project_id = ?""",
                (project_id,),
            ),
            "feedback_items": (
                "SELECT * FROM feedback_items WHERE project_id = ?",
                (project_id,),
            ),
            "feedback_review_bundles": (
                """SELECT b.* FROM feedback_review_bundles b
                   JOIN feedback_items f ON f.id = b.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_release_linkages": (
                """SELECT l.* FROM feedback_release_linkages l
                   JOIN feedback_items f ON f.id = l.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "memory_cards": (
                "SELECT * FROM memory_cards WHERE project_id = ?",
                (project_id,),
            ),
            "memory_card_revisions": (
                """SELECT r.* FROM memory_card_revisions r
                   JOIN memory_cards m ON m.id = r.memory_id WHERE m.project_id = ?""",
                (project_id,),
            ),
            "memory_card_confirmation_records": (
                """SELECT c.* FROM memory_card_confirmation_records c
                   JOIN memory_cards m ON m.id = c.memory_id WHERE m.project_id = ?""",
                (project_id,),
            ),
            "library_entities": (
                "SELECT * FROM library_entities WHERE project_id = ?",
                (project_id,),
            ),
            "library_entity_revisions": (
                """SELECT r.* FROM library_entity_revisions r
                   JOIN library_entities e ON e.id = r.entity_id
                   WHERE e.project_id = ?""",
                (project_id,),
            ),
            "library_entity_confirmation_records": (
                """SELECT c.* FROM library_entity_confirmation_records c
                   JOIN library_entities e ON e.id = c.entity_id
                   WHERE e.project_id = ?""",
                (project_id,),
            ),
        }
        payload: dict[str, list[dict[str, Any]]] = {}
        with self.db.connect() as connection:
            for table, (sql, params) in queries.items():
                payload[table] = [dict(row) for row in connection.execute(sql, params)]
        canonical = encode(payload)
        return ProjectExport(
            exported_at=utc_now(),
            payload=payload,
            payload_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        )

    def restore_project(self, backup: ProjectExport) -> Project:
        canonical = encode(backup.payload)
        if hashlib.sha256(canonical.encode()).hexdigest() != backup.payload_sha256:
            raise ConflictError("project export digest mismatch")
        allowed_columns = {
            "projects": (
                "id",
                "title",
                "description",
                "audience_mode",
                "visual_style",
                "aspect_ratio",
                "planned_episode_count",
                "target_episode_seconds",
                "project_bible_json",
                "created_at",
                "updated_at",
                "archived_at",
                "creative_format",
                "production_pipeline",
            ),
            "seasons": (
                "id",
                "project_id",
                "title",
                "season_number",
                "planned_episode_count",
                "season_arc_json",
                "created_at",
                "updated_at",
            ),
            "episodes": (
                "id",
                "season_id",
                "title",
                "episode_number",
                "logline",
                "outline_json",
                "target_seconds",
                "status",
                "approved_script_revision",
                "created_at",
                "updated_at",
            ),
            "season_plan_revisions": (
                "season_id",
                "revision",
                "plan_json",
                "source_transcript",
                "created_at",
            ),
            "season_plan_approval_records": (
                "id",
                "season_id",
                "plan_revision",
                "approved_by",
                "spoken_confirmation",
                "review_channel",
                "guardian_approval",
                "created_at",
            ),
            "script_revisions": (
                "episode_id",
                "revision",
                "content",
                "summary_for_voice_review",
                "source_transcript",
                "narrative_metadata_json",
                "approved_at",
                "created_at",
            ),
            "assets": (
                "id",
                "project_id",
                "season_id",
                "episode_id",
                "kind",
                "name",
                "local_uri",
                "subject_name",
                "metadata_json",
                "consent_granted",
                "consent_scope",
                "guardian_approved",
                "created_at",
            ),
            "asset_consent_records": (
                "id",
                "asset_id",
                "action_type",
                "consent_scope",
                "recorded_by",
                "statement",
                "guardian_approved",
                "created_at",
            ),
            "continuity_snapshots": (
                "id",
                "episode_id",
                "source_episode_id",
                "state_json",
                "unresolved_hooks_json",
                "created_at",
            ),
            "approval_records": (
                "id",
                "action_type",
                "project_id",
                "episode_id",
                "script_revision",
                "approved_by",
                "spoken_confirmation",
                "guardian_approval",
                "created_at",
            ),
            "continuity_extraction_confirmation_records": (
                "approval_id",
                "snapshot_id",
                "episode_id",
                "reviewed_script_revision",
                "proposal_sha256",
                "reviewed_state_json",
                "unresolved_hooks_json",
                "confirmed_by",
                "spoken_confirmation",
                "review_channel",
                "guardian_approval",
                "change_summary",
                "created_at",
            ),
            "feedback_items": (
                "id",
                "project_id",
                "category",
                "message",
                "source",
                "screen",
                "share_authorized",
                "guardian_approval",
                "status",
                "redaction_applied",
                "created_at",
            ),
            "feedback_review_bundles": (
                "feedback_id",
                "request_sha256",
                "bundle_json",
                "bundle_sha256",
                "created_at",
            ),
            "feedback_release_linkages": (
                "feedback_id",
                "request_sha256",
                "linkage_json",
                "linkage_sha256",
                "created_at",
            ),
            "memory_cards": (
                "id",
                "project_id",
                "asset_id",
                "title",
                "description",
                "ocr_text",
                "spoken_context",
                "approximate_date",
                "place",
                "people_json",
                "story_relevance",
                "allowed_use",
                "current_revision",
                "confirmation_status",
                "confirmed_by",
                "created_at",
                "updated_at",
            ),
            "memory_card_revisions": (
                "memory_id",
                "revision",
                "content_json",
                "source_channel",
                "change_summary",
                "created_at",
            ),
            "memory_card_confirmation_records": (
                "id",
                "memory_id",
                "reviewed_revision",
                "confirmed_by",
                "spoken_confirmation",
                "review_channel",
                "created_at",
            ),
            "library_entities": (
                "id",
                "project_id",
                "kind",
                "stable_name",
                "current_revision",
                "confirmed_revision",
                "created_at",
                "updated_at",
            ),
            "library_entity_revisions": (
                "entity_id",
                "revision",
                "name",
                "description",
                "attributes_json",
                "source_asset_ids_json",
                "source_memory_ids_json",
                "source_channel",
                "change_summary",
                "created_at",
            ),
            "library_entity_confirmation_records": (
                "id",
                "entity_id",
                "reviewed_revision",
                "confirmed_by",
                "spoken_confirmation",
                "review_channel",
                "created_at",
            ),
        }
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
        }:
            allowed_columns["assets"] = tuple(
                column for column in allowed_columns["assets"] if column != "season_id"
            )
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
            "nalu.project-export/v4",
        }:
            allowed_columns["projects"] = tuple(
                column
                for column in allowed_columns["projects"]
                if column not in {"creative_format", "production_pipeline"}
            )
            allowed_columns.pop("feedback_items")
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
            "nalu.project-export/v4",
            "nalu.project-export/v5",
            "nalu.project-export/v6",
            "nalu.project-export/v7",
            "nalu.project-export/v8",
        }:
            allowed_columns.pop("feedback_review_bundles")
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
            "nalu.project-export/v4",
            "nalu.project-export/v5",
            "nalu.project-export/v6",
            "nalu.project-export/v7",
            "nalu.project-export/v8",
            "nalu.project-export/v9",
        }:
            allowed_columns.pop("feedback_release_linkages")
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
            "nalu.project-export/v4",
            "nalu.project-export/v5",
        }:
            allowed_columns.pop("memory_cards")
            allowed_columns.pop("memory_card_revisions")
            allowed_columns.pop("memory_card_confirmation_records")
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
            "nalu.project-export/v4",
            "nalu.project-export/v5",
            "nalu.project-export/v6",
        }:
            allowed_columns.pop("library_entities")
            allowed_columns.pop("library_entity_revisions")
            allowed_columns.pop("library_entity_confirmation_records")
        if backup.schema_version in {
            "nalu.project-export/v1",
            "nalu.project-export/v2",
            "nalu.project-export/v3",
            "nalu.project-export/v4",
            "nalu.project-export/v5",
            "nalu.project-export/v6",
            "nalu.project-export/v7",
        }:
            allowed_columns.pop("continuity_extraction_confirmation_records")
        if backup.schema_version == "nalu.project-export/v1":
            allowed_columns.pop("season_plan_revisions")
            allowed_columns.pop("season_plan_approval_records")
            allowed_columns.pop("asset_consent_records")
        elif backup.schema_version == "nalu.project-export/v2":
            allowed_columns.pop("asset_consent_records")
        if set(backup.payload) != set(allowed_columns):
            raise ConflictError("project export contains an unsupported table set")
        project_rows = backup.payload["projects"]
        if len(project_rows) != 1:
            raise ConflictError("project export must contain exactly one project")
        project_id = project_rows[0].get("id")
        season_ids = {row.get("id") for row in backup.payload["seasons"]}
        episode_ids = {row.get("id") for row in backup.payload["episodes"]}
        if not isinstance(project_id, str) or not project_id:
            raise ConflictError("project export has an invalid project ID")
        if any(row.get("project_id") != project_id for row in backup.payload["seasons"]):
            raise ConflictError("project export contains a season from another project")
        if any(row.get("season_id") not in season_ids for row in backup.payload["episodes"]):
            raise ConflictError("project export contains an episode from another project")
        plan_revision_keys = {
            (row.get("season_id"), row.get("revision"))
            for row in backup.payload.get("season_plan_revisions", [])
        }
        if any(
            row.get("season_id") not in season_ids
            for row in backup.payload.get("season_plan_revisions", [])
        ):
            raise ConflictError("project export contains a plan from another project")
        if any(
            row.get("season_id") not in season_ids
            or (row.get("season_id"), row.get("plan_revision")) not in plan_revision_keys
            for row in backup.payload.get("season_plan_approval_records", [])
        ):
            raise ConflictError("project export contains plan approval from another project")
        if any(
            row.get("episode_id") not in episode_ids for row in backup.payload["script_revisions"]
        ):
            raise ConflictError("project export contains a script from another project")
        if any(
            row.get("project_id") != project_id
            or (row.get("season_id") is not None and row.get("season_id") not in season_ids)
            or (row.get("episode_id") is not None and row.get("episode_id") not in episode_ids)
            for row in backup.payload["assets"]
        ):
            raise ConflictError("project export contains an asset from another project")
        asset_ids = {row.get("id") for row in backup.payload["assets"]}
        if any(
            row.get("asset_id") not in asset_ids
            for row in backup.payload.get("asset_consent_records", [])
        ):
            raise ConflictError("project export contains consent from another project")
        if any(
            row.get("episode_id") not in episode_ids
            or (
                row.get("source_episode_id") is not None
                and row.get("source_episode_id") not in episode_ids
            )
            for row in backup.payload["continuity_snapshots"]
        ):
            raise ConflictError("project export contains continuity from another project")
        if any(
            row.get("project_id") != project_id or row.get("episode_id") not in episode_ids
            for row in backup.payload["approval_records"]
        ):
            raise ConflictError("project export contains approval from another project")
        snapshot_ids = {row.get("id") for row in backup.payload["continuity_snapshots"]}
        approval_ids = {row.get("id") for row in backup.payload["approval_records"]}
        script_revision_keys = {
            (row.get("episode_id"), row.get("revision"))
            for row in backup.payload["script_revisions"]
        }
        if any(
            row.get("episode_id") not in episode_ids
            or row.get("snapshot_id") not in snapshot_ids
            or row.get("approval_id") not in approval_ids
            or (
                row.get("episode_id"), row.get("reviewed_script_revision")
            ) not in script_revision_keys
            for row in backup.payload.get(
                "continuity_extraction_confirmation_records", []
            )
        ):
            raise ConflictError(
                "project export contains a continuity confirmation from another project"
            )
        if any(
            row.get("project_id") != project_id for row in backup.payload.get("feedback_items", [])
        ):
            raise ConflictError("project export contains feedback from another project")
        feedback_ids = {row.get("id") for row in backup.payload.get("feedback_items", [])}
        if any(
            row.get("feedback_id") not in feedback_ids
            for row in backup.payload.get("feedback_review_bundles", [])
        ):
            raise ConflictError("project export contains a feedback bundle from another project")
        feedback_bundle_digests: dict[Any, Any] = {}
        for row in backup.payload.get("feedback_review_bundles", []):
            try:
                bundle_body = decode(row.get("bundle_json", ""))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ConflictError("project export contains an unreadable feedback bundle") from exc
            if (
                bundle_body.get("feedback_id") != row.get("feedback_id")
                or bundle_body.get("request_sha256") != row.get("request_sha256")
                or hashlib.sha256(encode(bundle_body).encode()).hexdigest()
                != row.get("bundle_sha256")
            ):
                raise ConflictError("project export contains a tampered feedback bundle")
            feedback_bundle_digests[row.get("feedback_id")] = row.get("bundle_sha256")
        for row in backup.payload.get("feedback_release_linkages", []):
            try:
                linkage_body = decode(row.get("linkage_json", ""))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ConflictError("project export contains an unreadable release linkage") from exc
            if (
                row.get("feedback_id") not in feedback_ids
                or linkage_body.get("feedback_id") != row.get("feedback_id")
                or linkage_body.get("request_sha256") != row.get("request_sha256")
                or hashlib.sha256(encode(linkage_body).encode()).hexdigest()
                != row.get("linkage_sha256")
            ):
                raise ConflictError("project export contains a tampered release linkage")
            try:
                validated = FeedbackReleaseLinkage.model_validate(
                    {**linkage_body, "linkage_sha256": row.get("linkage_sha256")}
                )
                evidence = FeedbackReleaseLinkageCreate.model_validate(linkage_body)
            except ValueError as exc:
                raise ConflictError("project export contains invalid release evidence") from exc
            if validated.review_bundle_sha256 != feedback_bundle_digests.get(
                row.get("feedback_id")
            ):
                raise ConflictError("release linkage references a different review bundle")
            self._validate_feedback_release_evidence(evidence)
            request_body = {
                "feedback_id": row.get("feedback_id"),
                "idempotency_key_sha256": validated.idempotency_key_sha256,
                "evidence": evidence.model_dump(mode="json"),
            }
            if hashlib.sha256(encode(request_body).encode()).hexdigest() != row.get(
                "request_sha256"
            ):
                raise ConflictError("release linkage request digest does not match its evidence")
        if any(
            row.get("project_id") != project_id or row.get("asset_id") not in asset_ids
            for row in backup.payload.get("memory_cards", [])
        ):
            raise ConflictError("project export contains memory from another project")
        memory_ids = {row.get("id") for row in backup.payload.get("memory_cards", [])}
        if any(
            row.get("memory_id") not in memory_ids
            for row in backup.payload.get("memory_card_revisions", [])
        ):
            raise ConflictError("project export contains a memory revision from another project")
        if any(
            row.get("memory_id") not in memory_ids
            for row in backup.payload.get("memory_card_confirmation_records", [])
        ):
            raise ConflictError(
                "project export contains a memory confirmation from another project"
            )
        library_ids = {row.get("id") for row in backup.payload.get("library_entities", [])}
        if any(
            row.get("project_id") != project_id
            for row in backup.payload.get("library_entities", [])
        ):
            raise ConflictError("project export contains a library entity from another project")
        library_revision_keys = {
            (row.get("entity_id"), row.get("revision"))
            for row in backup.payload.get("library_entity_revisions", [])
        }
        if any(
            row.get("entity_id") not in library_ids
            for row in backup.payload.get("library_entity_revisions", [])
        ):
            raise ConflictError("project export contains a library revision from another project")
        if any(
            row.get("entity_id") not in library_ids
            or (row.get("entity_id"), row.get("reviewed_revision")) not in library_revision_keys
            for row in backup.payload.get("library_entity_confirmation_records", [])
        ):
            raise ConflictError(
                "project export contains a library confirmation from another project"
            )
        try:
            with self.db.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for table, columns in allowed_columns.items():
                    placeholders = ", ".join("?" for _ in columns)
                    column_sql = ", ".join(columns)
                    for row in backup.payload[table]:
                        if set(row) != set(columns):
                            raise ConflictError(f"invalid columns in project export table {table}")
                        connection.execute(
                            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
                            tuple(row[column] for column in columns),
                        )
        except ConflictError:
            raise
        except Exception as exc:
            raise ConflictError("project restore conflicts with existing data") from exc
        return self.get_project(str(project_id))

    @staticmethod
    def _redact_feedback_message(message: str) -> tuple[str, bool]:
        cleaned = message.strip()
        patterns = (
            (r"\bsk-[A-Za-z0-9_-]{10,}\b", "[已隐藏密钥]"),
            (r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[已隐藏邮箱]"),
            (r"(?<!\d)1[3-9]\d{9}(?!\d)", "[已隐藏手机号]"),
            (r"(?:file://)?/Users/[^/\s]+", "/Users/[已隐藏用户]"),
        )
        redacted = cleaned
        for pattern, replacement in patterns:
            redacted = re.sub(pattern, replacement, redacted)
        return redacted, redacted != cleaned

    def create_feedback(self, request: FeedbackCreate) -> FeedbackItem:
        if request.project_id:
            project = self.get_project(request.project_id)
            if (
                project.audience_mode == "child"
                and request.share_authorized
                and not request.guardian_approval
            ):
                raise ConflictError("guardian approval is required before sharing child feedback")
        message, redaction_applied = self._redact_feedback_message(request.message)
        feedback_id, now = new_id("fbk"), utc_now()
        status = "ready_for_review" if request.share_authorized else "local_only"
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO feedback_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feedback_id,
                    request.project_id,
                    request.category,
                    message,
                    request.source,
                    request.screen,
                    int(request.share_authorized),
                    int(request.guardian_approval),
                    status,
                    int(redaction_applied),
                    now,
                ),
            )
        return self.get_feedback(feedback_id)

    def get_feedback(self, feedback_id: str) -> FeedbackItem:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_items WHERE id = ?", (feedback_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback item not found")
        data = dict(row)
        data["share_authorized"] = bool(data["share_authorized"])
        data["guardian_approval"] = bool(data["guardian_approval"])
        data["redaction_applied"] = bool(data["redaction_applied"])
        return FeedbackItem.model_validate(data)

    def list_feedback(self, project_id: str | None = None) -> list[FeedbackItem]:
        query = "SELECT id FROM feedback_items"
        params: tuple[str, ...] = ()
        if project_id:
            self.get_project(project_id)
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY created_at, id"
        with self.db.connect() as connection:
            ids = [row["id"] for row in connection.execute(query, params)]
        return [self.get_feedback(feedback_id) for feedback_id in ids]

    @staticmethod
    def _explicit_feedback_bundle_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in ("我确认生成审核包", "我同意生成审核包", "确认准备审核资料")
        )

    def create_feedback_review_bundle(
        self, feedback_id: str, request: FeedbackReviewBundleCreate
    ) -> FeedbackReviewBundle:
        feedback = self.get_feedback(feedback_id)
        if not feedback.share_authorized or feedback.status != "ready_for_review":
            raise ConflictError("local-only feedback cannot create a review bundle")
        if not self._explicit_feedback_bundle_confirmation(request.confirmation_text):
            raise ConflictError("feedback review bundle requires explicit confirmation")

        expected, expected_redacted = self._redact_feedback_message(request.expected_behavior)
        actual, actual_redacted = self._redact_feedback_message(request.actual_behavior)
        steps: list[str] = []
        step_redacted = False
        for step in request.reproduction_steps:
            cleaned, changed = self._redact_feedback_message(step)
            steps.append(cleaned)
            step_redacted = step_redacted or changed
        prepared_by, preparer_redacted = self._redact_feedback_message(request.prepared_by)
        request_body = {
            "prepared_by": prepared_by,
            "expected_behavior": expected,
            "actual_behavior": actual,
            "reproduction_steps": steps,
            "confirmation_text": request.confirmation_text.strip(),
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()

        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_review_bundles WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("feedback already has a different immutable review bundle")
            stored = decode(existing["bundle_json"])
            if hashlib.sha256(encode(stored).encode()).hexdigest() != existing["bundle_sha256"]:
                raise ConflictError("stored feedback review bundle digest mismatch")
            stored["bundle_sha256"] = existing["bundle_sha256"]
            return FeedbackReviewBundle.model_validate(stored)

        now = utc_now()
        bundle_body = {
            "schema_version": "nalu.feedback-review-bundle/v1",
            "feedback_id": feedback.id,
            "project_id": feedback.project_id,
            "category": feedback.category,
            "redacted_message": feedback.message,
            "source": feedback.source,
            "screen": feedback.screen,
            "expected_behavior": expected,
            "actual_behavior": actual,
            "reproduction_steps": steps,
            "diagnostics": {
                "runtime_version": "0.1.0",
                "schema_version": str(self.db.schema_version()),
                "screen": feedback.screen,
            },
            "prepared_by": prepared_by,
            "created_at": now,
            "redaction_applied": bool(
                feedback.redaction_applied
                or expected_redacted
                or actual_redacted
                or step_redacted
                or preparer_redacted
            ),
            "attachments": [],
            "network_call_performed": False,
            "request_sha256": request_sha256,
        }
        bundle_sha256 = hashlib.sha256(encode(bundle_body).encode()).hexdigest()
        with self.db.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO feedback_review_bundles VALUES (?, ?, ?, ?, ?)",
                    (feedback_id, request_sha256, encode(bundle_body), bundle_sha256, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("feedback review bundle was created concurrently") from exc
        bundle_body["bundle_sha256"] = bundle_sha256
        return FeedbackReviewBundle.model_validate(bundle_body)

    def get_feedback_review_bundle(self, feedback_id: str) -> FeedbackReviewBundle:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_review_bundles WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback review bundle not found")
        stored = decode(row["bundle_json"])
        if hashlib.sha256(encode(stored).encode()).hexdigest() != row["bundle_sha256"]:
            raise ConflictError("stored feedback review bundle digest mismatch")
        stored["bundle_sha256"] = row["bundle_sha256"]
        return FeedbackReviewBundle.model_validate(stored)

    def create_feedback_release_linkage(
        self,
        feedback_id: str,
        request: FeedbackReleaseLinkageCreate,
        idempotency_key: str | None,
    ) -> FeedbackReleaseLinkage:
        feedback = self.get_feedback(feedback_id)
        if not feedback.share_authorized or feedback.status != "ready_for_review":
            raise ConflictError("local-only feedback cannot link release evidence")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")

        bundle = self.get_feedback_review_bundle(feedback_id)
        if request.review_bundle_sha256 != bundle.bundle_sha256:
            raise ConflictError("review bundle digest does not match the immutable local bundle")
        self._validate_feedback_release_evidence(request)

        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "idempotency_key_sha256": idempotency_key_sha256,
            "evidence": request.model_dump(mode="json"),
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_release_linkages WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("feedback already has different immutable release evidence")
            stored = decode(existing["linkage_json"])
            if hashlib.sha256(encode(stored).encode()).hexdigest() != existing["linkage_sha256"]:
                raise ConflictError("stored feedback release linkage digest mismatch")
            stored["linkage_sha256"] = existing["linkage_sha256"]
            return FeedbackReleaseLinkage.model_validate(stored)

        now = utc_now()
        linkage_body = {
            "schema_version": "nalu.feedback-release-linkage/v1",
            "feedback_id": feedback_id,
            **request.model_dump(mode="json"),
            "status": "qa_evidence_linked",
            "release_claimed": False,
            "network_call_performed": False,
            "created_at": now,
            "idempotency_key_sha256": idempotency_key_sha256,
            "request_sha256": request_sha256,
        }
        linkage_sha256 = hashlib.sha256(encode(linkage_body).encode()).hexdigest()
        with self.db.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO feedback_release_linkages VALUES (?, ?, ?, ?, ?)",
                    (
                        feedback_id,
                        request_sha256,
                        encode(linkage_body),
                        linkage_sha256,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("feedback release evidence was linked concurrently") from exc
        linkage_body["linkage_sha256"] = linkage_sha256
        return FeedbackReleaseLinkage.model_validate(linkage_body)

    @staticmethod
    def _validate_feedback_release_evidence(request: FeedbackReleaseLinkageCreate) -> None:
        if request.reviewed_change.commit_sha != request.ci.head_sha:
            raise ConflictError("reviewed change commit does not match successful CI head")
        if request.reviewed_change.commit_sha != request.installed_release.product_commit:
            raise ConflictError("reviewed change commit does not match installed release receipt")
        if request.ci.artifact_sha256 != request.installed_release.artifact_sha256:
            raise ConflictError("CI artifact does not match installed release receipt")
        if request.rollback.previous_build >= request.installed_release.build:
            raise ConflictError("rollback rehearsal must identify an older positive build")

    def get_feedback_release_linkage(self, feedback_id: str) -> FeedbackReleaseLinkage:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_release_linkages WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback release linkage not found")
        stored = decode(row["linkage_json"])
        if hashlib.sha256(encode(stored).encode()).hexdigest() != row["linkage_sha256"]:
            raise ConflictError("stored feedback release linkage digest mismatch")
        stored["linkage_sha256"] = row["linkage_sha256"]
        return FeedbackReleaseLinkage.model_validate(stored)

    def create_memory_card(self, project_id: str, request: MemoryCardCreate) -> MemoryCard:
        project = self.get_project(project_id)
        asset = self.get_asset(request.asset_id)
        if asset.project_id != project_id:
            raise ConflictError("memory evidence belongs to another project")
        if request.allowed_use == "visual_generation":
            if asset.kind in {"character_image", "voice_reference"} and not asset.consent_granted:
                raise ConflictError("visual generation requires active biometric consent")
            if (
                project.audience_mode == "child"
                and asset.kind in {"character_image", "voice_reference"}
                and not asset.guardian_approved
            ):
                raise ConflictError("child visual generation requires guardian approval")
        memory_id, now = new_id("mem"), utc_now()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO memory_cards VALUES (
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )""",
                    (
                        memory_id,
                        project_id,
                        request.asset_id,
                        request.title,
                        request.description,
                        request.ocr_text,
                        request.spoken_context,
                        request.approximate_date,
                        request.place,
                        encode([person.model_dump(mode="json") for person in request.people]),
                        request.story_relevance,
                        request.allowed_use,
                        1,
                        "draft",
                        "",
                        now,
                        now,
                    ),
                )
                content = request.model_dump(mode="json")
                connection.execute(
                    "INSERT INTO memory_card_revisions VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        memory_id,
                        1,
                        encode(content),
                        "system",
                        "素材导入后建立记忆卡草稿",
                        now,
                    ),
                )
        except Exception as exc:
            raise ConflictError("this asset already has a memory card") from exc
        return self.get_memory_card(memory_id)

    def get_memory_card(self, memory_id: str) -> MemoryCard:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM memory_cards WHERE id = ?", (memory_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("memory card not found")
        data = dict(row)
        data["people"] = decode(data.pop("people_json"))
        return MemoryCard.model_validate(data)

    def list_memory_cards(self, project_id: str, confirmed_only: bool = False) -> list[MemoryCard]:
        self.get_project(project_id)
        query = "SELECT id FROM memory_cards WHERE project_id = ?"
        params: tuple[str, ...] = (project_id,)
        if confirmed_only:
            query += " AND confirmation_status = 'confirmed'"
        query += " ORDER BY created_at, id"
        with self.db.connect() as connection:
            ids = [row["id"] for row in connection.execute(query, params)]
        return [self.get_memory_card(memory_id) for memory_id in ids]

    def update_memory_card(self, memory_id: str, request: MemoryCardUpdate) -> MemoryCard:
        current = self.get_memory_card(memory_id)
        if request.allowed_use == "visual_generation":
            project = self.get_project(current.project_id)
            asset = self.get_asset(current.asset_id)
            if asset.kind in {"character_image", "voice_reference"} and not asset.consent_granted:
                raise ConflictError("visual generation requires active biometric consent")
            if (
                project.audience_mode == "child"
                and asset.kind in {"character_image", "voice_reference"}
                and not asset.guardian_approved
            ):
                raise ConflictError("child visual generation requires guardian approval")
        updates = request.model_dump(
            exclude={"source_channel", "change_summary"}, exclude_none=True
        )
        content = current.model_dump(
            mode="json",
            include={
                "asset_id",
                "title",
                "description",
                "ocr_text",
                "spoken_context",
                "approximate_date",
                "place",
                "people",
                "story_relevance",
                "allowed_use",
            },
        )
        content.update(updates)
        next_revision = current.current_revision + 1
        now = utc_now()
        people = content["people"]
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE memory_cards SET title = ?, description = ?, ocr_text = ?,
                   spoken_context = ?, approximate_date = ?, place = ?, people_json = ?,
                   story_relevance = ?, allowed_use = ?, current_revision = ?,
                   confirmation_status = 'draft', confirmed_by = '', updated_at = ?
                   WHERE id = ? AND current_revision = ?""",
                (
                    content["title"],
                    content["description"],
                    content["ocr_text"],
                    content["spoken_context"],
                    content["approximate_date"],
                    content["place"],
                    encode(people),
                    content["story_relevance"],
                    content["allowed_use"],
                    next_revision,
                    now,
                    memory_id,
                    current.current_revision,
                ),
            )
            if connection.total_changes != 1:
                raise ConflictError("memory card changed before this update")
            connection.execute(
                "INSERT INTO memory_card_revisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    memory_id,
                    next_revision,
                    encode(content),
                    request.source_channel,
                    request.change_summary,
                    now,
                ),
            )
        return self.get_memory_card(memory_id)

    def list_memory_card_revisions(self, memory_id: str) -> list[MemoryCardRevision]:
        self.get_memory_card(memory_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM memory_card_revisions
                   WHERE memory_id = ? ORDER BY revision""",
                (memory_id,),
            ).fetchall()
        return [
            MemoryCardRevision.model_validate({**dict(row), "content": decode(row["content_json"])})
            for row in rows
        ]

    def confirm_memory_card(self, memory_id: str, request: MemoryCardConfirmation) -> MemoryCard:
        card = self.get_memory_card(memory_id)
        if request.reviewed_revision != card.current_revision:
            raise ConflictError("memory card changed after it was reviewed")
        conflict_report = self.memory_graph_conflicts(memory_id)
        if conflict_report.blocking:
            raise ConflictError(conflict_report.spoken_summary)
        record_id, now = new_id("mcr"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT id FROM memory_card_confirmation_records
                   WHERE memory_id = ? AND reviewed_revision = ?""",
                (memory_id, request.reviewed_revision),
            ).fetchone()
            if existing is not None:
                return card
            connection.execute(
                """UPDATE memory_cards SET confirmation_status = 'confirmed',
                   confirmed_by = ?, updated_at = ? WHERE id = ?""",
                (request.confirmed_by, now, memory_id),
            )
            connection.execute(
                """INSERT INTO memory_card_confirmation_records
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    memory_id,
                    request.reviewed_revision,
                    request.confirmed_by,
                    request.spoken_confirmation,
                    request.review_channel,
                    now,
                ),
            )
        return self.get_memory_card(memory_id)

    def list_memory_card_confirmations(self, memory_id: str) -> list[MemoryCardConfirmationRecord]:
        self.get_memory_card(memory_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM memory_card_confirmation_records
                   WHERE memory_id = ? ORDER BY created_at, id""",
                (memory_id,),
            ).fetchall()
        return [MemoryCardConfirmationRecord.model_validate(dict(row)) for row in rows]

    @staticmethod
    def _memory_fact_text(value: str) -> str:
        return re.sub(r"[\W_]+", "", value.casefold(), flags=re.UNICODE)

    @classmethod
    def _canonical_relationship(cls, value: str) -> str:
        normalized = cls._memory_fact_text(value)
        aliases = {
            "妻子": "spouse",
            "老婆": "spouse",
            "太太": "spouse",
            "爱人": "spouse",
            "丈夫": "spouse",
            "老公": "spouse",
            "母亲": "mother",
            "妈妈": "mother",
            "母亲大人": "mother",
            "父亲": "father",
            "爸爸": "father",
            "儿子": "son",
            "女儿": "daughter",
            "哥哥": "older_brother",
            "姐姐": "older_sister",
            "弟弟": "younger_brother",
            "妹妹": "younger_sister",
            "朋友": "friend",
            "同学": "classmate",
            "同事": "colleague",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _date_components(value: str) -> dict[str, str]:
        normalized = value.casefold()
        components: dict[str, str] = {}
        if match := re.search(r"(?<!\d)(18|19|20)\d{2}(?!\d)", normalized):
            components["year"] = match.group(0)
        if match := re.search(r"(?:年|[-/.])\s*(1[0-2]|0?[1-9])\s*(?:月|[-/.])", normalized):
            components["month"] = str(int(match.group(1)))
        if match := re.search(r"(?:月|[-/.])\s*(3[01]|[12]\d|0?[1-9])\s*(?:日|号)?", normalized):
            components["day"] = str(int(match.group(1)))
        seasons = {
            "春天": "spring", "春季": "spring", "春": "spring",
            "夏天": "summer", "夏季": "summer", "夏": "summer",
            "秋天": "autumn", "秋季": "autumn", "秋": "autumn",
            "冬天": "winter", "冬季": "winter", "冬": "winter",
        }
        for label, canonical in seasons.items():
            if label in normalized:
                components["season"] = canonical
                break
        return components

    @classmethod
    def _dates_provably_conflict(cls, left: str, right: str) -> bool:
        left_parts = cls._date_components(left)
        right_parts = cls._date_components(right)
        shared = set(left_parts) & set(right_parts)
        return any(left_parts[key] != right_parts[key] for key in shared)

    def memory_graph_conflicts(self, memory_id: str) -> MemoryGraphConflictReport:
        candidate = self.get_memory_card(memory_id)
        confirmed = [
            card
            for card in self.list_memory_cards(candidate.project_id, confirmed_only=True)
            if card.id != candidate.id
            and card.allowed_use in {"story_development", "visual_generation"}
        ]
        if candidate.allowed_use == "reference_only":
            return MemoryGraphConflictReport(
                project_id=candidate.project_id,
                candidate_memory_id=candidate.id,
                checked_against_confirmed_cards=len(confirmed),
                blocking=False,
                conflicts=[],
                spoken_summary=(
                    "这张记忆卡只供理解和核对，不会成为剧本事实，因此不参与叙事矛盾阻断。"
                ),
            )
        conflicts: list[MemoryGraphConflict] = []
        candidate_people = {
            self._memory_fact_text(person.name): person
            for person in candidate.people
            if self._memory_fact_text(person.name) and self._canonical_relationship(person.relationship)
        }
        candidate_event = self._memory_fact_text(candidate.title)
        generic_event_titles = {"照片", "老照片", "全家福", "家庭照片", "资料", "手稿"}
        for existing in confirmed:
            for person in existing.people:
                person_key = self._memory_fact_text(person.name)
                candidate_person = candidate_people.get(person_key)
                if candidate_person is None:
                    continue
                left = self._canonical_relationship(candidate_person.relationship)
                right = self._canonical_relationship(person.relationship)
                if left and right and left != right:
                    conflicts.append(
                        MemoryGraphConflict(
                            kind="relationship",
                            subject=candidate_person.name,
                            candidate_value=candidate_person.relationship,
                            existing_value=person.relationship,
                            candidate_memory_id=candidate.id,
                            candidate_revision=candidate.current_revision,
                            candidate_asset_id=candidate.asset_id,
                            existing_memory_id=existing.id,
                            existing_revision=existing.current_revision,
                            existing_asset_id=existing.asset_id,
                            explanation=(
                                f"{candidate_person.name} 在这张资料中是“{candidate_person.relationship}”，"
                                f"但已确认资料中是“{person.relationship}”。"
                            ),
                        )
                    )
            if (
                not candidate_event
                or candidate_event in generic_event_titles
                or candidate_event != self._memory_fact_text(existing.title)
            ):
                continue
            if (
                candidate.approximate_date
                and existing.approximate_date
                and self._dates_provably_conflict(
                    candidate.approximate_date, existing.approximate_date
                )
            ):
                conflicts.append(
                    MemoryGraphConflict(
                        kind="event_date",
                        subject=candidate.title,
                        candidate_value=candidate.approximate_date,
                        existing_value=existing.approximate_date,
                        candidate_memory_id=candidate.id,
                        candidate_revision=candidate.current_revision,
                        candidate_asset_id=candidate.asset_id,
                        existing_memory_id=existing.id,
                        existing_revision=existing.current_revision,
                        existing_asset_id=existing.asset_id,
                        explanation=(
                            f"事件“{candidate.title}”的时间在这张资料中是“{candidate.approximate_date}”，"
                            f"但已确认资料中是“{existing.approximate_date}”。"
                        ),
                    )
                )
            candidate_place = self._memory_fact_text(candidate.place)
            existing_place = self._memory_fact_text(existing.place)
            if (
                candidate_place
                and existing_place
                and candidate_place != existing_place
                and candidate_place not in existing_place
                and existing_place not in candidate_place
            ):
                conflicts.append(
                    MemoryGraphConflict(
                        kind="event_place",
                        subject=candidate.title,
                        candidate_value=candidate.place,
                        existing_value=existing.place,
                        candidate_memory_id=candidate.id,
                        candidate_revision=candidate.current_revision,
                        candidate_asset_id=candidate.asset_id,
                        existing_memory_id=existing.id,
                        existing_revision=existing.current_revision,
                        existing_asset_id=existing.asset_id,
                        explanation=(
                            f"事件“{candidate.title}”的地点在这张资料中是“{candidate.place}”，"
                            f"但已确认资料中是“{existing.place}”。"
                        ),
                    )
                )
        if conflicts:
            spoken_summary = (
                f"我发现 {len(conflicts)} 处资料对不上，暂时不能归档。"
                + " ".join(conflict.explanation for conflict in conflicts)
                + " 请修改其中一张记忆卡，再重新确认。"
            )
        else:
            spoken_summary = "没有发现与已确认家庭资料相冲突的关系、时间或事件地点。"
        return MemoryGraphConflictReport(
            project_id=candidate.project_id,
            candidate_memory_id=candidate.id,
            checked_against_confirmed_cards=len(confirmed),
            blocking=bool(conflicts),
            conflicts=conflicts,
            spoken_summary=spoken_summary,
        )

    def documentary_readiness(self, project_id: str) -> DocumentaryReadinessReport:
        project = self.get_project(project_id)
        if project.creative_format != "documentary_series":
            raise ConflictError("documentary readiness is only available for documentary projects")

        mode = str(project.project_bible.get("documentary_mode", "archival_voiceover"))
        if mode not in {"archival_voiceover", "archival_with_reenactment"}:
            mode = "archival_voiceover"
        cards_by_asset = {card.asset_id: card for card in self.list_memory_cards(project_id)}
        evidence: list[DocumentaryEvidenceItem] = []
        confirmed_authority = 0
        draft_or_unlinked = 0
        for asset in self.list_assets(project_id):
            card = cards_by_asset.get(asset.id)
            scope = "episode" if asset.episode_id else "season" if asset.season_id else "project"
            confirmation_status = card.confirmation_status if card else "unlinked"
            narrative_authority = bool(
                card
                and card.confirmation_status == "confirmed"
                and card.allowed_use in {"story_development", "visual_generation"}
            )
            if narrative_authority:
                confirmed_authority += 1
            if confirmation_status != "confirmed":
                draft_or_unlinked += 1
            biometric_generation_allowed = asset.kind not in {
                "character_image",
                "voice_reference",
            } or (
                asset.consent_granted
                and (project.audience_mode != "child" or asset.guardian_approved)
            )
            evidence.append(
                DocumentaryEvidenceItem(
                    asset_id=asset.id,
                    memory_id=card.id if card else None,
                    name=asset.name,
                    kind=asset.kind,
                    scope=scope,
                    confirmation_status=confirmation_status,
                    current_revision=card.current_revision if card else None,
                    allowed_use=card.allowed_use if card else None,
                    narrative_authority=narrative_authority,
                    visual_generation_authorized=bool(
                        card
                        and card.confirmation_status == "confirmed"
                        and card.allowed_use == "visual_generation"
                        and biometric_generation_allowed
                    ),
                )
            )

        blockers: list[str] = []
        if not evidence:
            blockers.append("no documentary source material has been imported")
        if confirmed_authority == 0:
            blockers.append("at least one confirmed story-development source is required")
        if draft_or_unlinked:
            blockers.append("draft or unlinked sources must be reviewed before they can be cited")
        if project.production_pipeline == "unassigned":
            blockers.append("no documentary adapter has passed authenticity and release QA")
        else:
            blockers.append("the selected documentary adapter has not been capability-verified")

        next_questions: list[str] = []
        if not evidence:
            next_questions.append("请上传一张老照片、手稿、录音或家庭视频。")
        if draft_or_unlinked:
            next_questions.append("我们逐份确认这些资料里的人、时间、地点和用途，可以吗？")
        if confirmed_authority:
            next_questions.append("您想按时间顺序讲，还是按人生主题分章？")
        next_questions.append("旁白由您自己讲、家人讲，还是使用合成声音？")

        return DocumentaryReadinessReport(
            project_id=project_id,
            documentary_mode=mode,
            evidence=evidence,
            confirmed_narrative_source_count=confirmed_authority,
            draft_or_unlinked_source_count=draft_or_unlinked,
            can_plan_chapters=confirmed_authority > 0,
            can_enter_production=False,
            generated_reenactment_label_required=mode == "archival_with_reenactment",
            blockers=blockers,
            next_questions=next_questions,
        )

    def project_deletion_preview(self, project_id: str) -> ProjectDeletionPreview:
        project = self.get_project(project_id)
        with self.db.connect() as connection:
            asset_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM assets WHERE project_id = ?",
                    (project_id,),
                ).fetchone()["count"]
            )
            run_count = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM production_runs WHERE project_id = ?",
                    (project_id,),
                ).fetchone()["count"]
            )
        return ProjectDeletionPreview(
            project_id=project_id,
            project_title=project.title,
            asset_count=asset_count,
            production_run_count=run_count,
            requires_snapshot_deletion_confirmation=run_count > 0,
            explanation=(
                "deletion includes immutable production snapshots and requires explicit confirmation"
                if run_count
                else "deletion removes the project and its local managed assets"
            ),
        )

    def delete_project_records(
        self, project_id: str, request: ProjectDeletionRequest
    ) -> tuple[int, int]:
        preview = self.project_deletion_preview(project_id)
        if request.confirmation_title != preview.project_title:
            raise ConflictError("project title confirmation does not match")
        if preview.production_run_count and not request.delete_production_snapshots:
            raise ConflictError("immutable production snapshot deletion was not confirmed")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM production_runs WHERE project_id = ?", (project_id,))
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return preview.asset_count, preview.production_run_count

    def project_run_ids(self, project_id: str) -> list[str]:
        self.get_project(project_id)
        with self.db.connect() as connection:
            return [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM production_runs WHERE project_id = ? ORDER BY id",
                    (project_id,),
                )
            ]

    def create_season(self, project_id: str, request: SeasonCreate) -> Season:
        self.get_project(project_id)
        season_id, now = new_id("sea"), utc_now()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO seasons VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        season_id,
                        project_id,
                        request.title,
                        request.season_number,
                        request.planned_episode_count,
                        encode(request.season_arc),
                        now,
                        now,
                    ),
                )
                self._snapshot_season_plan(connection, season_id, "")
        except Exception as exc:
            raise ConflictError("season number already exists") from exc
        return self.get_season(season_id)

    def get_season(self, season_id: str) -> Season:
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT s.*,
                          COALESCE((SELECT MAX(revision) FROM season_plan_revisions
                                    WHERE season_id = s.id), 0) AS plan_revision,
                          (SELECT MAX(plan_revision) FROM season_plan_approval_records
                           WHERE season_id = s.id) AS approved_plan_revision
                   FROM seasons s WHERE s.id = ?""",
                (season_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("season not found")
        data = dict(row)
        data["season_arc"] = decode(data.pop("season_arc_json"))
        return Season.model_validate(data)

    def _snapshot_season_plan(
        self, connection, season_id: str, source_transcript: str
    ) -> SeasonPlanRevision:
        season = connection.execute("SELECT * FROM seasons WHERE id = ?", (season_id,)).fetchone()
        if season is None:
            raise NotFoundError("season not found")
        episodes = [
            dict(row)
            for row in connection.execute(
                """SELECT id, title, episode_number, logline, outline_json,
                          target_seconds, status, approved_script_revision
                   FROM episodes WHERE season_id = ? ORDER BY episode_number""",
                (season_id,),
            )
        ]
        for episode in episodes:
            episode["outline"] = decode(episode.pop("outline_json"))
        current = connection.execute(
            "SELECT COALESCE(MAX(revision), 0) AS revision FROM season_plan_revisions WHERE season_id = ?",
            (season_id,),
        ).fetchone()
        revision, now = int(current["revision"]) + 1, utc_now()
        plan = {
            "season": {
                "title": season["title"],
                "season_number": season["season_number"],
                "planned_episode_count": season["planned_episode_count"],
                "season_arc": decode(season["season_arc_json"]),
            },
            "episodes": episodes,
        }
        connection.execute(
            "INSERT INTO season_plan_revisions VALUES (?, ?, ?, ?, ?)",
            (season_id, revision, encode(plan), source_transcript, now),
        )
        return SeasonPlanRevision(
            season_id=season_id,
            revision=revision,
            plan=plan,
            source_transcript=source_transcript,
            created_at=now,
        )

    def update_season_plan(self, season_id: str, request: SeasonPlanUpdate) -> Season:
        self.get_season(season_id)
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if request.title is not None:
                connection.execute(
                    "UPDATE seasons SET title = ?, updated_at = ? WHERE id = ?",
                    (request.title, utc_now(), season_id),
                )
            if request.season_arc is not None:
                connection.execute(
                    "UPDATE seasons SET season_arc_json = ?, updated_at = ? WHERE id = ?",
                    (encode(request.season_arc), utc_now(), season_id),
                )
            self._snapshot_season_plan(connection, season_id, request.source_transcript)
        return self.get_season(season_id)

    def list_season_plan_revisions(self, season_id: str) -> list[SeasonPlanRevision]:
        self.get_season(season_id)
        with self.db.connect() as connection:
            rows = list(
                connection.execute(
                    "SELECT * FROM season_plan_revisions WHERE season_id = ? ORDER BY revision",
                    (season_id,),
                )
            )
        return [
            SeasonPlanRevision(
                season_id=row["season_id"],
                revision=row["revision"],
                plan=decode(row["plan_json"]),
                source_transcript=row["source_transcript"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def approve_season_plan(
        self, season_id: str, request: SeasonPlanApprovalCreate
    ) -> SeasonPlanApproval:
        season = self.get_season(season_id)
        if season.plan_revision == 0:
            raise ConflictError("season plan has no revision to approve")
        approval_id, now = new_id("spa"), utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO season_plan_approval_records
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    season_id,
                    season.plan_revision,
                    request.approved_by,
                    request.spoken_confirmation,
                    request.review_channel,
                    int(request.guardian_approval),
                    now,
                ),
            )
        return SeasonPlanApproval(
            id=approval_id,
            season_id=season_id,
            plan_revision=season.plan_revision,
            created_at=now,
            **request.model_dump(),
        )

    def list_season_plan_approvals(self, season_id: str) -> list[SeasonPlanApproval]:
        self.get_season(season_id)
        with self.db.connect() as connection:
            rows = list(
                connection.execute(
                    """SELECT * FROM season_plan_approval_records
                       WHERE season_id = ? ORDER BY created_at""",
                    (season_id,),
                )
            )
        return [SeasonPlanApproval.model_validate(dict(row)) for row in rows]

    def list_project_seasons(self, project_id: str) -> list[Season]:
        self.get_project(project_id)
        with self.db.connect() as connection:
            ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM seasons WHERE project_id = ? ORDER BY season_number",
                    (project_id,),
                )
            ]
        return [self.get_season(season_id) for season_id in ids]

    def create_episode(self, season_id: str, request: EpisodeCreate) -> Episode:
        self.get_season(season_id)
        episode_id, now = new_id("ep"), utc_now()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        episode_id,
                        season_id,
                        request.title,
                        request.episode_number,
                        request.logline,
                        encode(request.outline),
                        request.target_seconds,
                        EpisodeStatus.PLANNED,
                        None,
                        now,
                        now,
                    ),
                )
                self._snapshot_season_plan(connection, season_id, "")
        except Exception as exc:
            raise ConflictError("episode number already exists") from exc
        return self.get_episode(episode_id)

    def update_episode_plan(self, episode_id: str, request: EpisodePlanUpdate) -> Episode:
        episode = self.get_episode(episode_id)
        if episode.status not in EDITABLE_EPISODE_PLAN_STATUSES:
            raise ConflictError("approved or production-stage episode plans are immutable")
        updates: list[str] = []
        values: list[Any] = []
        for column, value in (
            ("title", request.title),
            ("logline", request.logline),
            ("target_seconds", request.target_seconds),
        ):
            if value is not None:
                updates.append(f"{column} = ?")
                values.append(value)
        if request.outline is not None:
            updates.append("outline_json = ?")
            values.append(encode(request.outline))
        updates.append("updated_at = ?")
        values.extend((utc_now(), episode_id))
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT status, season_id FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
            if current is None:
                raise NotFoundError("episode not found")
            if EpisodeStatus(current["status"]) not in EDITABLE_EPISODE_PLAN_STATUSES:
                raise ConflictError("approved or production-stage episode plans are immutable")
            connection.execute(f"UPDATE episodes SET {', '.join(updates)} WHERE id = ?", values)
            self._snapshot_season_plan(connection, current["season_id"], request.source_transcript)
        return self.get_episode(episode_id)

    def get_episode(self, episode_id: str) -> Episode:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("episode not found")
        data = dict(row)
        data["outline"] = decode(data.pop("outline_json"))
        return Episode.model_validate(data)

    def list_season_episodes(self, season_id: str) -> list[Episode]:
        self.get_season(season_id)
        with self.db.connect() as connection:
            ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM episodes WHERE season_id = ? ORDER BY episode_number",
                    (season_id,),
                )
            ]
        return [self.get_episode(episode_id) for episode_id in ids]

    def _record_episode_transition(
        self,
        connection,
        episode_id: str,
        from_status: EpisodeStatus,
        to_status: EpisodeStatus,
        requested_by: str,
        reason: str,
    ) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM episode_events WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        connection.execute(
            "INSERT INTO episode_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("eev"),
                episode_id,
                int(row["sequence"]),
                "status_transition",
                from_status,
                to_status,
                requested_by,
                reason,
                utc_now(),
            ),
        )

    def transition_episode(self, episode_id: str, request: EpisodeTransitionRequest) -> Episode:
        episode = self.get_episode(episode_id)
        if request.target_status not in EPISODE_TRANSITIONS[episode.status]:
            raise ConflictError(
                f"episode transition {episode.status} -> {request.target_status} is not allowed"
            )
        if request.target_status in {EpisodeStatus.SCRIPT_APPROVED, EpisodeStatus.PUBLISHED}:
            raise ConflictError("this transition requires its dedicated approval endpoint")
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = EpisodeStatus(
                connection.execute(
                    "SELECT status FROM episodes WHERE id = ?", (episode_id,)
                ).fetchone()["status"]
            )
            if current != episode.status:
                raise ConflictError("episode state changed; reload and retry")
            connection.execute(
                "UPDATE episodes SET status = ?, updated_at = ? WHERE id = ?",
                (request.target_status, now, episode_id),
            )
            self._record_episode_transition(
                connection,
                episode_id,
                current,
                request.target_status,
                request.requested_by,
                request.reason,
            )
        return self.get_episode(episode_id)

    def list_episode_events(self, episode_id: str) -> list[EpisodeEvent]:
        self.get_episode(episode_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM episode_events WHERE episode_id = ? ORDER BY sequence",
                (episode_id,),
            ).fetchall()
        return [EpisodeEvent.model_validate(dict(row)) for row in rows]

    def create_script(self, episode_id: str, request: ScriptRevisionCreate) -> ScriptRevision:
        episode = self.get_episode(episode_id)
        if (
            EpisodeStatus.SCRIPT_REVIEW not in EPISODE_TRANSITIONS[episode.status]
            and episode.status != EpisodeStatus.SCRIPT_REVIEW
        ):
            raise ConflictError(
                f"cannot create a script revision while episode is {episode.status}"
            )
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 AS revision FROM script_revisions WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            revision = int(row["revision"])
            connection.execute(
                """INSERT INTO script_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    revision,
                    request.content,
                    request.summary_for_voice_review,
                    request.source_transcript,
                    encode(request.narrative_metadata),
                    None,
                    now,
                ),
            )
            connection.execute(
                "UPDATE episodes SET status = ?, updated_at = ? WHERE id = ?",
                (EpisodeStatus.SCRIPT_REVIEW, now, episode.id),
            )
            if episode.status != EpisodeStatus.SCRIPT_REVIEW:
                self._record_episode_transition(
                    connection,
                    episode_id,
                    episode.status,
                    EpisodeStatus.SCRIPT_REVIEW,
                    "script-service",
                    f"script revision {revision} created",
                )
        return self.get_script(episode_id, revision)

    def get_script(self, episode_id: str, revision: int) -> ScriptRevision:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM script_revisions WHERE episode_id = ? AND revision = ?",
                (episode_id, revision),
            ).fetchone()
        if row is None:
            raise NotFoundError("script revision not found")
        data = dict(row)
        data["narrative_metadata"] = decode(data.pop("narrative_metadata_json"))
        return ScriptRevision.model_validate(data)

    def list_scripts(self, episode_id: str) -> list[ScriptRevision]:
        self.get_episode(episode_id)
        with self.db.connect() as connection:
            revisions = [
                row["revision"]
                for row in connection.execute(
                    """SELECT revision FROM script_revisions
                       WHERE episode_id = ? ORDER BY revision""",
                    (episode_id,),
                )
            ]
        return [self.get_script(episode_id, revision) for revision in revisions]

    def approve_script(
        self, episode_id: str, revision: int, approval: ApprovalCreate
    ) -> ScriptRevision:
        self.get_script(episode_id, revision)
        episode = self.get_episode(episode_id)
        if episode.status != EpisodeStatus.SCRIPT_REVIEW:
            raise ConflictError("only a script in review may be approved")
        season = self.get_season(episode.season_id)
        now = utc_now()
        approval_id = new_id("apr")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT status FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
            latest = connection.execute(
                """SELECT MAX(revision) AS revision FROM script_revisions
                   WHERE episode_id = ?""",
                (episode_id,),
            ).fetchone()
            if (
                current is None
                or EpisodeStatus(current["status"]) != EpisodeStatus.SCRIPT_REVIEW
                or latest is None
                or revision != latest["revision"]
            ):
                raise ConflictError("only the latest script revision in review may be approved")
            connection.execute(
                "UPDATE script_revisions SET approved_at = NULL WHERE episode_id = ?", (episode_id,)
            )
            self._record_episode_transition(
                connection,
                episode_id,
                episode.status,
                EpisodeStatus.SCRIPT_APPROVED,
                approval.approved_by,
                f"approved script revision {revision}",
            )
            connection.execute(
                "UPDATE script_revisions SET approved_at = ? WHERE episode_id = ? AND revision = ?",
                (now, episode_id, revision),
            )
            connection.execute(
                "UPDATE episodes SET approved_script_revision = ?, status = ?, updated_at = ? WHERE id = ?",
                (revision, EpisodeStatus.SCRIPT_APPROVED, now, episode_id),
            )
            connection.execute(
                """INSERT INTO approval_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    "script_approved",
                    season.project_id,
                    episode_id,
                    revision,
                    approval.approved_by,
                    approval.spoken_confirmation,
                    int(approval.guardian_approval),
                    now,
                ),
            )
        return self.get_script(episode_id, revision)

    def revoke_script_approval(
        self, episode_id: str, revision: int, request: ApprovalRevocationCreate
    ) -> ScriptRevision:
        script = self.get_script(episode_id, revision)
        episode = self.get_episode(episode_id)
        if (
            episode.status != EpisodeStatus.SCRIPT_APPROVED
            or episode.approved_script_revision != revision
            or script.approved_at is None
        ):
            raise ConflictError("only the currently approved script may be revoked")
        season = self.get_season(episode.season_id)
        approval_id, now = new_id("apr"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """SELECT status, approved_script_revision FROM episodes
                   WHERE id = ?""",
                (episode_id,),
            ).fetchone()
            if (
                current is None
                or EpisodeStatus(current["status"]) != EpisodeStatus.SCRIPT_APPROVED
                or current["approved_script_revision"] != revision
            ):
                raise ConflictError("script approval changed before revocation")
            connection.execute(
                """UPDATE script_revisions SET approved_at = NULL
                   WHERE episode_id = ? AND revision = ?""",
                (episode_id, revision),
            )
            connection.execute(
                """UPDATE episodes SET approved_script_revision = NULL,
                   status = ?, updated_at = ? WHERE id = ?""",
                (EpisodeStatus.SCRIPT_REVIEW, now, episode_id),
            )
            self._record_episode_transition(
                connection,
                episode_id,
                EpisodeStatus.SCRIPT_APPROVED,
                EpisodeStatus.SCRIPT_REVIEW,
                request.requested_by,
                request.reason,
            )
            connection.execute(
                """INSERT INTO approval_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    "script_revoked",
                    season.project_id,
                    episode_id,
                    revision,
                    request.requested_by,
                    request.reason,
                    0,
                    now,
                ),
            )
        return self.get_script(episode_id, revision)

    def list_script_approvals(self, episode_id: str) -> list[ApprovalRecord]:
        self.get_episode(episode_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM approval_records WHERE episode_id = ? ORDER BY created_at, id",
                (episode_id,),
            ).fetchall()
        records = []
        for row in rows:
            data = dict(row)
            data["guardian_approval"] = bool(data["guardian_approval"])
            records.append(ApprovalRecord.model_validate(data))
        return records

    def create_asset(
        self, project_id: str, request: AssetCreate, asset_id: str | None = None
    ) -> Asset:
        self.get_project(project_id)
        if request.season_id:
            season = self.get_season(request.season_id)
            if season.project_id != project_id:
                raise ConflictError("asset season belongs to another project")
        if request.episode_id:
            episode = self.get_episode(request.episode_id)
            season = self.get_season(episode.season_id)
            if season.project_id != project_id:
                raise ConflictError("asset episode belongs to another project")
        asset_id, now = asset_id or new_id("ast"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO assets
                   (id, project_id, season_id, episode_id, kind, name, local_uri,
                    subject_name, metadata_json, consent_granted, consent_scope,
                    guardian_approved, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset_id,
                    project_id,
                    request.season_id,
                    request.episode_id,
                    request.kind,
                    request.name,
                    request.local_uri,
                    request.subject_name,
                    encode(request.metadata),
                    int(request.consent_granted),
                    request.consent_scope,
                    int(request.guardian_approved),
                    now,
                ),
            )
            if request.consent_granted:
                connection.execute(
                    """INSERT INTO asset_consent_records
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_id("acr"),
                        asset_id,
                        "granted",
                        request.consent_scope,
                        request.consent_granted_by,
                        request.consent_statement,
                        int(request.guardian_approved),
                        now,
                    ),
                )
        return self.get_asset(asset_id)

    def get_asset(self, asset_id: str) -> Asset:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise NotFoundError("asset not found")
        data = dict(row)
        data["metadata"] = decode(data.pop("metadata_json"))
        data["consent_granted"] = bool(data["consent_granted"])
        data["guardian_approved"] = bool(data["guardian_approved"])
        return Asset.model_validate(data)

    def list_assets(
        self,
        project_id: str,
        episode_id: str | None = None,
        season_id: str | None = None,
    ) -> list[Asset]:
        self.get_project(project_id)
        sql = "SELECT id FROM assets WHERE project_id = ?"
        params: tuple[Any, ...] = (project_id,)
        if episode_id:
            episode = self.get_episode(episode_id)
            season = self.get_season(episode.season_id)
            if season.project_id != project_id:
                raise ConflictError("asset episode belongs to another project")
            sql += " AND (season_id IS NULL OR season_id = ?)"
            sql += " AND (episode_id IS NULL OR episode_id = ?)"
            params += (season.id, episode_id)
        elif season_id:
            season = self.get_season(season_id)
            if season.project_id != project_id:
                raise ConflictError("asset season belongs to another project")
            sql += " AND episode_id IS NULL AND (season_id IS NULL OR season_id = ?)"
            params += (season_id,)
        sql += " ORDER BY created_at"
        with self.db.connect() as connection:
            ids = [row["id"] for row in connection.execute(sql, params)]
        return [self.get_asset(asset_id) for asset_id in ids]

    def list_asset_consent_records(self, asset_id: str) -> list[AssetConsentRecord]:
        self.get_asset(asset_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM asset_consent_records
                   WHERE asset_id = ? ORDER BY created_at, id""",
                (asset_id,),
            ).fetchall()
        records = []
        for row in rows:
            data = dict(row)
            data["guardian_approved"] = bool(data["guardian_approved"])
            records.append(AssetConsentRecord.model_validate(data))
        return records

    def revoke_asset_consent(
        self, asset_id: str, request: AssetConsentRevocationCreate
    ) -> AssetConsentRecord:
        asset = self.get_asset(asset_id)
        if not asset.consent_granted:
            raise ConflictError("asset consent is not currently active")
        record_id, now = new_id("acr"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT consent_granted FROM assets WHERE id = ?", (asset_id,)
            ).fetchone()
            if current is None or not bool(current["consent_granted"]):
                raise ConflictError("asset consent changed before revocation")
            connection.execute("UPDATE assets SET consent_granted = 0 WHERE id = ?", (asset_id,))
            connection.execute(
                """INSERT INTO asset_consent_records
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    asset_id,
                    "revoked",
                    asset.consent_scope,
                    request.requested_by,
                    request.reason,
                    int(asset.guardian_approved),
                    now,
                ),
            )
        return self.list_asset_consent_records(asset_id)[-1]

    def bind_run_assets(self, run_id: str, assets: list[Asset]) -> None:
        self.get_run(run_id)
        with self.db.connect() as connection:
            for asset in assets:
                connection.execute(
                    """INSERT OR IGNORE INTO production_run_assets
                       VALUES (?, ?, ?)""",
                    (run_id, asset.id, str(asset.metadata.get("sha256", ""))),
                )

    def asset_dependency_report(self, asset_id: str) -> AssetDependencyReport:
        self.get_asset(asset_id)
        with self.db.connect() as connection:
            run_ids = [
                row["run_id"]
                for row in connection.execute(
                    """SELECT run_id FROM production_run_assets
                       WHERE asset_id = ? ORDER BY run_id""",
                    (asset_id,),
                )
            ]
        return AssetDependencyReport(
            asset_id=asset_id,
            can_delete=not run_ids,
            production_run_ids=run_ids,
            explanation=(
                "asset is referenced by immutable production snapshots"
                if run_ids
                else "asset has no immutable production snapshot dependencies"
            ),
        )

    def delete_asset_record(self, asset_id: str) -> None:
        report = self.asset_dependency_report(asset_id)
        if not report.can_delete:
            raise ConflictError(report.explanation)
        with self.db.connect() as connection:
            connection.execute("DELETE FROM assets WHERE id = ?", (asset_id,))

    @staticmethod
    def _continuity_marker(content: str, label: str) -> str:
        match = re.search(
            rf"【{re.escape(label)}】\s*[：:]?\s*([^\r\n]+)",
            content,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _continuity_extracted_paths(
        state: ContinuityState, unresolved_hooks: list[str]
    ) -> list[str]:
        paths: list[str] = []
        paths.extend(f"characters.{name}" for name in sorted(state.characters))
        paths.extend(f"props.{name}" for name in sorted(state.props))
        for field in ("scene_location", "story_time", "weather"):
            if getattr(state, field):
                paths.append(field)
        if unresolved_hooks:
            paths.append("unresolved_hooks")
        return paths

    @staticmethod
    def _continuity_proposal_summary(
        state: ContinuityState, unresolved_hooks: list[str]
    ) -> str:
        parts = ["我从当前定稿剧本整理了本集结尾，请您核对"]
        if state.scene_location:
            parts.append(f"地点是 {state.scene_location}")
        if state.story_time:
            parts.append(f"时间是 {state.story_time}")
        if state.weather:
            parts.append(f"天气是 {state.weather}")
        for name, character in sorted(state.characters.items()):
            details = [name]
            if character.location:
                details.append(f"在 {character.location}")
            if character.wardrobe:
                details.append("穿着" + "、".join(character.wardrobe))
            if character.injuries:
                details.append("伤势是" + "、".join(character.injuries))
            if character.held_props:
                details.append("拿着" + "、".join(character.held_props))
            if character.relationships:
                relationships = "、".join(
                    f"和{person}的关系是{relationship}"
                    for person, relationship in sorted(character.relationships.items())
                )
                details.append(relationships)
            if character.revealed_facts:
                details.append("已经知道" + "、".join(character.revealed_facts))
            parts.append("，".join(details))
        for name, prop in sorted(state.props.items()):
            details = [f"道具 {name}"]
            if prop.owner:
                details.append(f"属于 {prop.owner}")
            if prop.location:
                details.append(f"在 {prop.location}")
            if prop.condition:
                details.append(f"状态是 {prop.condition}")
            parts.append("，".join(details))
        if unresolved_hooks:
            parts.append("还没有解决的是" + "、".join(unresolved_hooks))
        parts.append("这只是待确认草稿，不会自动成为下一集事实")
        return "。".join(parts) + "。"

    def continuity_extraction_proposal(
        self, episode_id: str
    ) -> ContinuityExtractionProposal:
        episode = self.get_episode(episode_id)
        revision = episode.approved_script_revision
        if episode.status != EpisodeStatus.SCRIPT_APPROVED or revision is None:
            raise ConflictError("continuity extraction requires the current approved script")
        script = self.get_script(episode_id, revision)
        if script.approved_at is None:
            raise ConflictError("continuity extraction requires the current approved script")
        metadata_state = script.narrative_metadata.get("ending_continuity")
        metadata_hooks = script.narrative_metadata.get("ending_unresolved_hooks", [])
        source = "approved_script_metadata"
        evidence = []
        if metadata_state is not None:
            if not isinstance(metadata_state, dict) or not isinstance(metadata_hooks, list):
                raise ConflictError("approved script ending continuity metadata is invalid")
            try:
                candidate = ContinuitySnapshotCreate.model_validate(
                    {"state": metadata_state, "unresolved_hooks": metadata_hooks}
                )
            except Exception as exc:
                raise ConflictError(
                    "approved script ending continuity metadata is invalid"
                ) from exc
        else:
            source = "approved_script_markers"
            scene_location = self._continuity_marker(script.content, "结尾地点")
            story_time = self._continuity_marker(script.content, "结尾时间")
            weather = self._continuity_marker(script.content, "结尾天气")
            hooks_text = self._continuity_marker(script.content, "未解悬念")
            hooks = [
                item.strip()
                for item in re.split(r"[、,，;；]", hooks_text)
                if item.strip()
            ]
            try:
                candidate = ContinuitySnapshotCreate(
                    state=ContinuityState(
                        scene_location=scene_location or None,
                        story_time=story_time or None,
                        weather=weather or None,
                    ),
                    unresolved_hooks=hooks,
                )
            except ValueError:
                semantic = extract_semantic_ending_continuity(script.content)
                source = "approved_script_semantic"
                evidence = semantic.evidence
                try:
                    candidate = ContinuitySnapshotCreate(
                        state=semantic.state,
                        unresolved_hooks=semantic.unresolved_hooks,
                    )
                except Exception as exc:
                    raise ConflictError(
                        "approved script has no extractable ending continuity that is "
                        "safe to propose; "
                        "add ending facts in the final scene, explicit ending markers, "
                        "or an ending state, then approve a new revision"
                    ) from exc
        state = candidate.state
        hooks = candidate.unresolved_hooks
        extracted_paths = self._continuity_extracted_paths(state, hooks)
        canonical = encode(
            {
                "episode_id": episode_id,
                "script_revision": revision,
                "source": source,
                "state": state.model_dump(mode="json", exclude_none=True),
                "unresolved_hooks": hooks,
            }
        )
        return ContinuityExtractionProposal(
            episode_id=episode_id,
            script_revision=revision,
            proposal_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
            source=source,
            state=state,
            unresolved_hooks=hooks,
            extracted_paths=extracted_paths,
            evidence=evidence,
            spoken_summary=self._continuity_proposal_summary(state, hooks),
        )

    def confirm_continuity_extraction(
        self, episode_id: str, request: ContinuityExtractionConfirmation
    ) -> ContinuityExtractionConfirmationResult:
        proposal = self.continuity_extraction_proposal(episode_id)
        if request.reviewed_script_revision != proposal.script_revision:
            raise ConflictError("approved script changed after continuity review")
        if request.proposal_sha256 != proposal.proposal_sha256:
            raise ConflictError("continuity proposal changed after it was reviewed")
        reviewed = {
            "state": request.reviewed_state.model_dump(mode="json", exclude_none=True),
            "unresolved_hooks": request.unresolved_hooks,
        }
        proposed = {
            "state": proposal.state.model_dump(mode="json", exclude_none=True),
            "unresolved_hooks": proposal.unresolved_hooks,
        }
        if reviewed != proposed and not request.change_summary.strip():
            raise ConflictError("edited continuity extraction requires a change summary")
        episode = self.get_episode(episode_id)
        season = self.get_season(episode.season_id)
        inherited = self.latest_continuity(season.id, episode.episode_number)
        script = self.get_script(episode_id, proposal.script_revision)
        raw_hook_review = script.narrative_metadata.get("continuity_hook_review")
        try:
            hook_review = (
                ContinuityHookReview.model_validate(raw_hook_review)
                if raw_hook_review is not None
                else None
            )
        except ValueError as exc:
            raise ConflictError(f"invalid continuity hook review: {exc}") from exc
        project = self.get_project(season.project_id)
        if (
            project.audience_mode == "child"
            and hook_review is not None
            and not hook_review.guardian_approval
        ):
            raise ConflictError("child hook review requires guardian approval")
        hooks_match, hook_message = ending_hooks_match_review(
            inherited, hook_review, request.unresolved_hooks
        )
        if not hooks_match:
            raise ConflictError(hook_message)
        snapshot_id, approval_id, now = new_id("con"), new_id("apr"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT status, approved_script_revision FROM episodes WHERE id = ?",
                (episode_id,),
            ).fetchone()
            if (
                current is None
                or current["status"] != EpisodeStatus.SCRIPT_APPROVED
                or current["approved_script_revision"] != proposal.script_revision
            ):
                raise ConflictError("approved script changed before continuity confirmation")
            existing = connection.execute(
                """SELECT id FROM approval_records
                   WHERE episode_id = ? AND script_revision = ?
                   AND action_type = 'continuity_extraction_confirmed'""",
                (episode_id, proposal.script_revision),
            ).fetchone()
            if existing is not None:
                raise ConflictError(
                    "this approved script already has a confirmed ending handoff"
                )
            connection.execute(
                "INSERT INTO continuity_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    episode_id,
                    None,
                    encode(reviewed["state"]),
                    encode(request.unresolved_hooks),
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO approval_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval_id,
                    "continuity_extraction_confirmed",
                    season.project_id,
                    episode_id,
                    proposal.script_revision,
                    request.confirmed_by,
                    request.spoken_confirmation,
                    int(request.guardian_approval),
                    now,
                ),
            )
            connection.execute(
                """INSERT INTO continuity_extraction_confirmation_records
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval_id,
                    snapshot_id,
                    episode_id,
                    proposal.script_revision,
                    proposal.proposal_sha256,
                    encode(reviewed["state"]),
                    encode(request.unresolved_hooks),
                    request.confirmed_by,
                    request.spoken_confirmation,
                    request.review_channel,
                    int(request.guardian_approval),
                    request.change_summary.strip(),
                    now,
                ),
            )
        return ContinuityExtractionConfirmationResult(
            snapshot=self.get_continuity_snapshot(snapshot_id),
            approval=ApprovalRecord(
                id=approval_id,
                action_type="continuity_extraction_confirmed",
                project_id=season.project_id,
                episode_id=episode_id,
                script_revision=proposal.script_revision,
                approved_by=request.confirmed_by,
                spoken_confirmation=request.spoken_confirmation,
                guardian_approval=request.guardian_approval,
                created_at=now,
            ),
        )

    def create_continuity_snapshot(
        self, episode_id: str, request: ContinuitySnapshotCreate
    ) -> ContinuitySnapshot:
        episode = self.get_episode(episode_id)
        if request.source_episode_id:
            source = self.get_episode(request.source_episode_id)
            if source.season_id != episode.season_id:
                raise ConflictError("continuity source episode must belong to the same season")
            if source.episode_number > episode.episode_number:
                raise ConflictError("continuity source cannot be a future episode")
        snapshot_id, now = new_id("con"), utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO continuity_snapshots VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    episode_id,
                    request.source_episode_id,
                    encode(request.state.model_dump(mode="json", exclude_none=True)),
                    encode(request.unresolved_hooks),
                    now,
                ),
            )
        return self.get_continuity_snapshot(snapshot_id)

    def get_continuity_snapshot(self, snapshot_id: str) -> ContinuitySnapshot:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM continuity_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("continuity snapshot not found")
        data = dict(row)
        data["state"] = decode(data.pop("state_json"))
        data["unresolved_hooks"] = decode(data.pop("unresolved_hooks_json"))
        return ContinuitySnapshot.model_validate(data)

    def list_continuity_snapshots(self, episode_id: str) -> list[ContinuitySnapshot]:
        self.get_episode(episode_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT id FROM continuity_snapshots
                   WHERE episode_id = ? ORDER BY created_at, id""",
                (episode_id,),
            ).fetchall()
        return [self.get_continuity_snapshot(row["id"]) for row in rows]

    def latest_continuity(self, season_id: str, before_episode: int) -> ContinuitySnapshot | None:
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT c.id FROM continuity_snapshots c
                   JOIN episodes e ON e.id = c.episode_id
                   WHERE e.season_id = ? AND e.episode_number < ?
                   ORDER BY e.episode_number DESC, c.created_at DESC LIMIT 1""",
                (season_id, before_episode),
            ).fetchone()
        return self.get_continuity_snapshot(row["id"]) if row else None

    def _validate_library_sources(
        self, project_id: str, request: LibraryEntityRevisionCreate
    ) -> None:
        for asset_id in request.source_asset_ids:
            asset = self.get_asset(asset_id)
            if asset.project_id != project_id:
                raise ConflictError("library source asset belongs to another project")
            if asset.kind in {"character_image", "voice_reference"} and not asset.consent_granted:
                raise ConflictError("library biometric source requires active consent")
        for memory_id in request.source_memory_ids:
            memory = self.get_memory_card(memory_id)
            if memory.project_id != project_id:
                raise ConflictError("library source memory belongs to another project")
            if memory.confirmation_status != "confirmed":
                raise ConflictError("library source memory must be confirmed")
            if memory.allowed_use == "reference_only":
                raise ConflictError("reference-only memory cannot become library authority")

    def create_library_entity(self, project_id: str, request: LibraryEntityCreate) -> LibraryEntity:
        self.get_project(project_id)
        self._validate_library_sources(project_id, request)
        entity_id, now = new_id("lib"), utc_now()
        stable_name = re.sub(r"\s+", " ", request.name.strip()).casefold()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO library_entities
                       VALUES (?, ?, ?, ?, 1, NULL, ?, ?)""",
                    (entity_id, project_id, request.kind, stable_name, now, now),
                )
                connection.execute(
                    """INSERT INTO library_entity_revisions
                       VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entity_id,
                        request.name.strip(),
                        request.description,
                        encode(request.attributes),
                        encode(request.source_asset_ids),
                        encode(request.source_memory_ids),
                        request.source_channel,
                        request.change_summary,
                        now,
                    ),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ConflictError(
                    "a library entity with this kind and name already exists"
                ) from exc
            raise
        return self.get_library_entity(entity_id)

    def get_library_revision(self, entity_id: str, revision: int) -> LibraryEntityRevision:
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT * FROM library_entity_revisions
                   WHERE entity_id = ? AND revision = ?""",
                (entity_id, revision),
            ).fetchone()
        if row is None:
            raise NotFoundError("library revision not found")
        data = dict(row)
        data["attributes"] = decode(data.pop("attributes_json"))
        data["source_asset_ids"] = decode(data.pop("source_asset_ids_json"))
        data["source_memory_ids"] = decode(data.pop("source_memory_ids_json"))
        return LibraryEntityRevision.model_validate(data)

    def get_library_entity(self, entity_id: str) -> LibraryEntity:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM library_entities WHERE id = ?", (entity_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("library entity not found")
        data = dict(row)
        data["current"] = self.get_library_revision(entity_id, data["current_revision"])
        return LibraryEntity.model_validate(data)

    def list_library_entities(self, project_id: str) -> list[LibraryEntity]:
        self.get_project(project_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT id FROM library_entities WHERE project_id = ?
                   ORDER BY kind, stable_name""",
                (project_id,),
            ).fetchall()
        return [self.get_library_entity(row["id"]) for row in rows]

    def list_library_revisions(self, entity_id: str) -> list[LibraryEntityRevision]:
        self.get_library_entity(entity_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT revision FROM library_entity_revisions
                   WHERE entity_id = ? ORDER BY revision""",
                (entity_id,),
            ).fetchall()
        return [self.get_library_revision(entity_id, row["revision"]) for row in rows]

    def create_library_revision(
        self, entity_id: str, request: LibraryEntityRevisionCreate
    ) -> LibraryEntity:
        entity = self.get_library_entity(entity_id)
        self._validate_library_sources(entity.project_id, request)
        revision, now = entity.current_revision + 1, utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO library_entity_revisions
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity_id,
                    revision,
                    request.name.strip(),
                    request.description,
                    encode(request.attributes),
                    encode(request.source_asset_ids),
                    encode(request.source_memory_ids),
                    request.source_channel,
                    request.change_summary,
                    now,
                ),
            )
            connection.execute(
                """UPDATE library_entities SET current_revision = ?, updated_at = ?
                   WHERE id = ?""",
                (revision, now, entity_id),
            )
        return self.get_library_entity(entity_id)

    def confirm_library_entity(
        self, entity_id: str, request: LibraryEntityConfirmation
    ) -> LibraryEntityConfirmationRecord:
        entity = self.get_library_entity(entity_id)
        if request.reviewed_revision != entity.current_revision:
            raise ConflictError("only the current library revision can be confirmed")
        candidate = self.get_library_revision(entity_id, request.reviewed_revision)
        candidate_names = self._library_resolution_names(entity.stable_name, candidate)
        for other in self.list_library_entities(entity.project_id):
            if (
                other.id == entity_id
                or other.kind != entity.kind
                or other.confirmed_revision is None
            ):
                continue
            other_revision = self.get_library_revision(other.id, other.confirmed_revision)
            overlap = candidate_names & self._library_resolution_names(
                other.stable_name, other_revision
            )
            if overlap:
                raise ConflictError(
                    "library alias conflicts with another confirmed entity: "
                    + ", ".join(sorted(overlap))
                )
        record_id, now = new_id("lcf"), utc_now()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO library_entity_confirmation_records
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record_id,
                        entity_id,
                        request.reviewed_revision,
                        request.confirmed_by,
                        request.spoken_confirmation,
                        request.review_channel,
                        now,
                    ),
                )
                connection.execute(
                    """UPDATE library_entities SET confirmed_revision = ?, updated_at = ?
                       WHERE id = ?""",
                    (request.reviewed_revision, now, entity_id),
                )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ConflictError("this library revision is already confirmed") from exc
            raise
        return LibraryEntityConfirmationRecord(
            id=record_id, entity_id=entity_id, created_at=now, **request.model_dump()
        )

    @staticmethod
    def _normalized_library_mention(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip()).casefold()

    def _library_resolution_names(
        self, stable_name: str, revision: LibraryEntityRevision
    ) -> set[str]:
        names = {stable_name, self._normalized_library_mention(revision.name)}
        aliases = revision.attributes.get("aliases", [])
        if isinstance(aliases, list):
            names.update(
                self._normalized_library_mention(alias)
                for alias in aliases
                if isinstance(alias, str) and alias.strip()
            )
        return names

    def resolve_library_entity(
        self, project_id: str, kind: str, mention: str
    ) -> LibraryEntityResolution:
        normalized = self._normalized_library_mention(mention)
        if not normalized:
            raise NotFoundError("library mention is empty")
        matches: list[tuple[LibraryEntity, str]] = []
        for entity in self.list_library_entities(project_id):
            if str(entity.kind) != kind or entity.confirmed_revision is None:
                continue
            revision = self.get_library_revision(entity.id, entity.confirmed_revision)
            names = self._library_resolution_names(entity.stable_name, revision)
            if normalized in names:
                matched_by = "stable_name" if normalized == entity.stable_name else "alias"
                matches.append((entity, matched_by))
        if not matches:
            raise NotFoundError("no confirmed library entity matches this mention")
        if len(matches) > 1:
            raise ConflictError("library mention is ambiguous across confirmed entities")
        entity, matched_by = matches[0]
        return LibraryEntityResolution(
            mention=mention,
            normalized_mention=normalized,
            entity_id=entity.id,
            kind=entity.kind,
            confirmed_revision=entity.confirmed_revision or 0,
            matched_by=matched_by,
        )

    def resolved_project_library(self, project_id: str) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for entity in self.list_library_entities(project_id):
            if entity.confirmed_revision is None:
                continue
            revision = self.get_library_revision(entity.id, entity.confirmed_revision)
            resolved.append(
                {
                    "entity_id": entity.id,
                    "kind": entity.kind,
                    "stable_name": entity.stable_name,
                    "confirmed_revision": entity.confirmed_revision,
                    "revision": revision.model_dump(mode="json"),
                }
            )
        return resolved

    def save_run(self, run: ProductionRun) -> None:
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO production_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.id,
                    run.project_id,
                    run.season_id,
                    run.episode_id,
                    run.status,
                    int(run.dry_run),
                    run.requested_model,
                    run.estimated_budget_credits,
                    run.package_path,
                    run.error,
                    run.created_at,
                    run.updated_at,
                ),
            )

    def update_run_status(
        self, run_id: str, status: RunStatus, error: str | None = None
    ) -> ProductionRun:
        self.get_run(run_id)
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE production_runs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
                (status, error, now, run_id),
            )
        return self.get_run(run_id)

    def mark_postproduction_materialized(
        self,
        run_id: str,
        *,
        plan_sha256: str,
        result_sha256: str,
        requested_by: str,
    ) -> tuple[ProductionRun, Episode]:
        run = self.get_run(run_id)
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_run = connection.execute(
                "SELECT status, episode_id FROM production_runs WHERE id = ?", (run_id,)
            ).fetchone()
            current_episode = connection.execute(
                "SELECT status FROM episodes WHERE id = ?", (run.episode_id,)
            ).fetchone()
            if current_run is None:
                raise NotFoundError("production run not found")
            if current_episode is None:
                raise NotFoundError("episode not found")
            run_status = RunStatus(current_run["status"])
            episode_status = EpisodeStatus(current_episode["status"])
            if run_status == RunStatus.QA_REVIEW and episode_status == EpisodeStatus.QA_REVIEW:
                prior = connection.execute(
                    """SELECT payload_json FROM run_events
                       WHERE run_id = ? AND event_type = 'postproduction_materialized'
                       ORDER BY sequence DESC LIMIT 1""",
                    (run_id,),
                ).fetchone()
                payload = decode(prior["payload_json"]) if prior else {}
                if (
                    payload.get("plan_sha256") == plan_sha256
                    and payload.get("result_sha256") == result_sha256
                ):
                    return self.get_run(run_id), self.get_episode(run.episode_id)
                raise ConflictError(
                    "production run entered QA review from different postproduction evidence"
                )
            if run_status != RunStatus.RUNNING:
                raise ConflictError(
                    "production run must be running before local postproduction materialization"
                )
            if episode_status != EpisodeStatus.POSTPRODUCTION:
                raise ConflictError(
                    "episode must be in postproduction before local materialization"
                )
            latest = connection.execute(
                """SELECT id FROM production_runs WHERE episode_id = ?
                   ORDER BY created_at DESC, id DESC LIMIT 1""",
                (run.episode_id,),
            ).fetchone()
            if latest is None or latest["id"] != run_id:
                raise ConflictError("only the latest episode production run can materialize")

            connection.execute(
                "UPDATE production_runs SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
                (RunStatus.QA_REVIEW, now, run_id),
            )
            connection.execute(
                "UPDATE episodes SET status = ?, updated_at = ? WHERE id = ?",
                (EpisodeStatus.QA_REVIEW, now, run.episode_id),
            )
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            connection.execute(
                "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("evt"),
                    run_id,
                    int(row["sequence"]),
                    "postproduction_materialized",
                    RunStatus.RUNNING,
                    RunStatus.QA_REVIEW,
                    "Local postproduction rendered normalized media, five audio layers and a final master.",
                    encode(
                        {
                            "plan_sha256": plan_sha256,
                            "result_sha256": result_sha256,
                            "requested_by": requested_by,
                            "network_call_performed": False,
                        }
                    ),
                    now,
                ),
            )
            self._record_episode_transition(
                connection,
                run.episode_id,
                EpisodeStatus.POSTPRODUCTION,
                EpisodeStatus.QA_REVIEW,
                requested_by,
                f"production run {run_id} completed local postproduction materialization",
            )
        return self.get_run(run_id), self.get_episode(run.episode_id)

    def complete_run_after_qa(
        self,
        run_id: str,
        *,
        output_seal_sha256: str,
        qa_report_sha256: str,
        completed_by: str,
    ) -> tuple[ProductionRun, Episode]:
        run = self.get_run(run_id)
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_run = connection.execute(
                "SELECT status, episode_id FROM production_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if current_run is None:
                raise NotFoundError("production run not found")
            current_episode = connection.execute(
                "SELECT status FROM episodes WHERE id = ?", (run.episode_id,)
            ).fetchone()
            if current_episode is None:
                raise NotFoundError("episode not found")
            run_status = RunStatus(current_run["status"])
            episode_status = EpisodeStatus(current_episode["status"])
            if (
                run_status == RunStatus.COMPLETED
                and episode_status == EpisodeStatus.READY_TO_PUBLISH
            ):
                prior = connection.execute(
                    """SELECT payload_json FROM run_events
                       WHERE run_id = ? AND event_type = 'production_completed'
                       ORDER BY sequence DESC LIMIT 1""",
                    (run_id,),
                ).fetchone()
                payload = decode(prior["payload_json"]) if prior else {}
                if (
                    payload.get("output_seal_sha256") == output_seal_sha256
                    and payload.get("qa_report_sha256") == qa_report_sha256
                ):
                    return self.get_run(run_id), self.get_episode(run.episode_id)
                raise ConflictError("production run was completed with different QA evidence")
            if run_status != RunStatus.QA_REVIEW:
                raise ConflictError("production run must be in QA review before completion")
            if episode_status != EpisodeStatus.QA_REVIEW:
                raise ConflictError("episode must be in QA review before completion")
            latest = connection.execute(
                """SELECT id FROM production_runs WHERE episode_id = ?
                   ORDER BY created_at DESC, id DESC LIMIT 1""",
                (run.episode_id,),
            ).fetchone()
            if latest is None or latest["id"] != run_id:
                raise ConflictError("only the latest episode production run can complete")

            connection.execute(
                "UPDATE production_runs SET status = ?, error = NULL, updated_at = ? WHERE id = ?",
                (RunStatus.COMPLETED, now, run_id),
            )
            connection.execute(
                "UPDATE episodes SET status = ?, updated_at = ? WHERE id = ?",
                (EpisodeStatus.READY_TO_PUBLISH, now, run.episode_id),
            )
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            connection.execute(
                "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("evt"),
                    run_id,
                    int(row["sequence"]),
                    "production_completed",
                    RunStatus.QA_REVIEW,
                    RunStatus.COMPLETED,
                    "Verified rendered outputs and final QA evidence completed production.",
                    encode(
                        {
                            "output_seal_sha256": output_seal_sha256,
                            "qa_report_sha256": qa_report_sha256,
                            "completed_by": completed_by,
                        }
                    ),
                    now,
                ),
            )
            self._record_episode_transition(
                connection,
                run.episode_id,
                EpisodeStatus.QA_REVIEW,
                EpisodeStatus.READY_TO_PUBLISH,
                completed_by,
                f"production run {run_id} passed sealed final QA",
            )
        return self.get_run(run_id), self.get_episode(run.episode_id)

    def get_run(self, run_id: str) -> ProductionRun:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM production_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("production run not found")
        data = dict(row)
        data["dry_run"] = bool(data["dry_run"])
        return ProductionRun.model_validate(data)

    def latest_run_for_episode(self, episode_id: str) -> ProductionRun | None:
        self.get_episode(episode_id)
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT id FROM production_runs WHERE episode_id = ?
                   ORDER BY created_at DESC, id DESC LIMIT 1""",
                (episode_id,),
            ).fetchone()
        return self.get_run(row["id"]) if row else None

    @staticmethod
    def _remote_task_from_row(row: Any) -> RemoteTaskBinding:
        data = dict(row)
        data["receipt"] = decode(data.pop("receipt_json"))
        return RemoteTaskBinding.model_validate(data)

    def get_remote_task_binding(self, binding_id: str) -> RemoteTaskBinding:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM remote_task_bindings WHERE id = ?", (binding_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("remote task binding not found")
        return self._remote_task_from_row(row)

    def list_remote_task_bindings(self, run_id: str) -> list[RemoteTaskBinding]:
        self.get_run(run_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM remote_task_bindings
                   WHERE run_id = ? ORDER BY created_at, id""",
                (run_id,),
            ).fetchall()
        return [self._remote_task_from_row(row) for row in rows]

    def _record_remote_task_event(
        self,
        connection: Any,
        binding: RemoteTaskBinding,
        event_type: str,
        message: str,
    ) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?",
            (binding.run_id,),
        ).fetchone()
        connection.execute(
            "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id("evt"),
                binding.run_id,
                int(row["sequence"]),
                event_type,
                None,
                None,
                message,
                encode(
                    {
                        "binding_id": binding.id,
                        "task_key": binding.task_key,
                        "provider": binding.provider,
                        "state": binding.state,
                        "provider_task_id": binding.provider_task_id,
                        "response_sha256": binding.response_sha256,
                        "charge_classification": binding.charge_classification,
                    }
                ),
                binding.updated_at,
            ),
        )

    def _prepare_remote_task_binding(
        self,
        authority: object,
        run_id: str,
        *,
        task_key: str,
        provider: str,
        model: str,
        submission_fingerprint: str,
        request_sha256: str,
    ) -> RemoteTaskBinding:
        self._require_remote_task_write_authority(authority)
        run = self.get_run(run_id)
        if run.dry_run:
            raise ConflictError("dry runs cannot prepare remote paid task bindings")
        if model != run.requested_model:
            raise ConflictError("remote task model does not match its production run")
        if run.status not in {
            RunStatus.WAITING_FOR_APPROVAL,
            RunStatus.QUEUED,
            RunStatus.RUNNING,
        }:
            raise ConflictError("production run state cannot prepare a remote task")
        values = {
            "task_key": task_key.strip(),
            "provider": provider.strip(),
            "model": model.strip(),
        }
        if not all(values.values()):
            raise ConflictError("remote task key, provider and model are required")
        for name, digest in (
            ("submission fingerprint", submission_fingerprint),
            ("request SHA", request_sha256),
        ):
            if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
                raise ConflictError(f"{name} must be a SHA-256 digest")

        now, binding_id = utc_now(), new_id("remote")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT * FROM remote_task_bindings
                   WHERE run_id = ? AND task_key = ?""",
                (run_id, values["task_key"]),
            ).fetchone()
            if existing is not None:
                binding = self._remote_task_from_row(existing)
                if (
                    binding.provider == values["provider"]
                    and binding.model == values["model"]
                    and binding.submission_fingerprint == submission_fingerprint
                    and binding.request_sha256 == request_sha256
                ):
                    return binding
                raise ConflictError(
                    "remote task key is already bound to different submission inputs"
                )
            connection.execute(
                """INSERT INTO remote_task_bindings
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    binding_id,
                    run_id,
                    values["task_key"],
                    values["provider"],
                    values["model"],
                    submission_fingerprint,
                    request_sha256,
                    RemoteTaskState.PREPARED,
                    None,
                    None,
                    None,
                    encode({}),
                    "",
                    None,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM remote_task_bindings WHERE id = ?", (binding_id,)
            ).fetchone()
            binding = self._remote_task_from_row(row)
            self._record_remote_task_event(
                connection,
                binding,
                "remote_task_prepared",
                "Durable remote task intent recorded before provider submission.",
            )
        return self.get_remote_task_binding(binding_id)

    def _transition_remote_task_binding(
        self,
        authority: object,
        binding_id: str,
        *,
        target_state: RemoteTaskState,
        response_sha256: str,
        provider_task_id: str | None = None,
        result_uri: str | None = None,
        receipt: dict[str, Any] | None = None,
        charge_classification: str,
        actual_charged_credits: int | None = None,
    ) -> RemoteTaskBinding:
        self._require_remote_task_write_authority(authority)
        if re.fullmatch(r"[a-f0-9]{64}", response_sha256) is None:
            raise ConflictError("provider response SHA must be a SHA-256 digest")
        if actual_charged_credits is not None and actual_charged_credits < 0:
            raise ConflictError("actual charged credits cannot be negative")
        if target_state in {
            RemoteTaskState.SUBMITTED,
            RemoteTaskState.COMPLETED,
        } and (not provider_task_id or not provider_task_id.strip()):
            raise ConflictError("submitted and completed tasks require a provider task ID")
        if target_state == RemoteTaskState.COMPLETED and not result_uri:
            raise ConflictError("completed remote tasks require a result URI")
        if target_state == RemoteTaskState.COMPLETED and (
            actual_charged_credits is None or not receipt
        ):
            raise ConflictError("completed remote tasks require a credit receipt")
        if (
            target_state == RemoteTaskState.ZERO_CHARGE_FAILED
            and actual_charged_credits != 0
        ):
            raise ConflictError("zero-charge failures require an exact zero-credit receipt")
        if target_state == RemoteTaskState.AMBIGUOUS_CHARGE and actual_charged_credits is not None:
            raise ConflictError("ambiguous-charge tasks cannot claim a reconciled credit total")
        if target_state in {
            RemoteTaskState.AMBIGUOUS_CHARGE,
            RemoteTaskState.ZERO_CHARGE_FAILED,
        } and not charge_classification.strip():
            raise ConflictError("failed or ambiguous provider responses require classification")

        allowed = {
            RemoteTaskState.PREPARED: {
                RemoteTaskState.SUBMITTED,
                RemoteTaskState.AMBIGUOUS_CHARGE,
                RemoteTaskState.ZERO_CHARGE_FAILED,
                RemoteTaskState.CANCELLED,
            },
            RemoteTaskState.AMBIGUOUS_CHARGE: {
                RemoteTaskState.SUBMITTED,
                RemoteTaskState.ZERO_CHARGE_FAILED,
            },
            RemoteTaskState.SUBMITTED: {
                RemoteTaskState.COMPLETED,
                RemoteTaskState.AMBIGUOUS_CHARGE,
                RemoteTaskState.CANCELLED,
            },
        }
        now = utc_now()
        receipt = receipt or {}
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM remote_task_bindings WHERE id = ?", (binding_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("remote task binding not found")
            current = self._remote_task_from_row(row)
            if current.provider_task_id and provider_task_id != current.provider_task_id:
                raise ConflictError("provider task identity cannot be changed or discarded")
            expected = {
                "state": target_state,
                "provider_task_id": provider_task_id,
                "response_sha256": response_sha256,
                "result_uri": result_uri,
                "receipt": receipt,
                "charge_classification": charge_classification,
                "actual_charged_credits": actual_charged_credits,
            }
            if current.state == target_state:
                if all(getattr(current, key) == value for key, value in expected.items()):
                    return current
                raise ConflictError("remote task state is already bound to different evidence")
            if target_state not in allowed.get(current.state, set()):
                raise ConflictError(
                    f"remote task cannot transition from {current.state} to {target_state}"
                )
            try:
                connection.execute(
                    """UPDATE remote_task_bindings
                       SET state = ?, provider_task_id = ?, response_sha256 = ?,
                           result_uri = ?, receipt_json = ?, charge_classification = ?,
                           actual_charged_credits = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        target_state,
                        provider_task_id,
                        response_sha256,
                        result_uri,
                        encode(receipt),
                        charge_classification,
                        actual_charged_credits,
                        now,
                        binding_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("provider task ID is already bound to another task") from exc
            updated_row = connection.execute(
                "SELECT * FROM remote_task_bindings WHERE id = ?", (binding_id,)
            ).fetchone()
            updated = self._remote_task_from_row(updated_row)
            self._record_remote_task_event(
                connection,
                updated,
                f"remote_task_{target_state}",
                "Remote task state and provider evidence committed atomically.",
            )
        return self.get_remote_task_binding(binding_id)

    def append_run_event(
        self,
        run_id: str,
        event_type: str,
        *,
        from_status: RunStatus | None = None,
        to_status: RunStatus | None = None,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        self.get_run(run_id)
        event_id, now = new_id("evt"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            sequence = int(row["sequence"])
            connection.execute(
                """INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    run_id,
                    sequence,
                    event_type,
                    from_status,
                    to_status,
                    message,
                    encode(payload or {}),
                    now,
                ),
            )
        return self.get_run_event(event_id)

    def record_local_visual_analysis(
        self,
        run_id: str,
        *,
        result_sha256: str,
        manifest_sha256: str,
        status: str,
        failure_count: int,
    ) -> RunEvent:
        """Record immutable visual evidence once and recover after a file/DB boundary crash."""
        run = self.get_run(run_id)
        event_id, now = new_id("evt"), utc_now()
        payload = {
            "status": status,
            "result_sha256": result_sha256,
            "manifest_sha256": manifest_sha256,
            "failure_count": failure_count,
            "provider_upload_performed": False,
        }
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                """SELECT id, payload_json FROM run_events
                   WHERE run_id = ? AND event_type = 'local_visual_analysis_completed'
                   ORDER BY sequence DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            if prior is not None:
                prior_payload = decode(prior["payload_json"])
                if (
                    prior_payload.get("result_sha256") == result_sha256
                    and prior_payload.get("manifest_sha256") == manifest_sha256
                ):
                    return self.get_run_event(prior["id"])
                raise ConflictError("production run has different local visual evidence")
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            connection.execute(
                """INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    run_id,
                    int(row["sequence"]),
                    "local_visual_analysis_completed",
                    run.status,
                    run.status,
                    (
                        "Apple Vision analyzed decoded final-master frames against confirmed "
                        "local character and prop references."
                    ),
                    encode(payload),
                    now,
                ),
            )
        return self.get_run_event(event_id)

    def get_run_event(self, event_id: str) -> RunEvent:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM run_events WHERE id = ?", (event_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("run event not found")
        data = dict(row)
        data["payload"] = decode(data.pop("payload_json"))
        return RunEvent.model_validate(data)

    def list_run_events(self, run_id: str) -> list[RunEvent]:
        self.get_run(run_id)
        with self.db.connect() as connection:
            ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM run_events WHERE run_id = ? ORDER BY sequence", (run_id,)
                )
            ]
        return [self.get_run_event(event_id) for event_id in ids]
