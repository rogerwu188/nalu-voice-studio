from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .continuity import ending_hooks_match_review
from .continuity_extraction import extract_semantic_ending_continuity
from .database import Database
from .development_handoff import (
    DevelopmentHandoffPolicy,
    DevelopmentHandoffReconciliationVerifier,
    DevelopmentHandoffTransport,
)
from .development_result import DevelopmentResultVerifier
from .feedback_export import (
    FeedbackExportPolicy,
    IssueTrackerReconciliationVerifier,
    IssueTrackerTransport,
)
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
    DirectorStrategyRevision,
    DocumentaryEvidenceItem,
    DocumentaryReadinessReport,
    Episode,
    EpisodeCreate,
    EpisodeEvent,
    EpisodePlanUpdate,
    EpisodeStatus,
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
    FeedbackReleaseReadinessCheck,
    FeedbackReviewBundle,
    FeedbackReviewBundleCreate,
    FeedbackTriageCreate,
    FeedbackTriageRecord,
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
    PublicationMetricsLearningResult,
    PublicationMetricsSnapshot,
    PublicationMetricsSyncCreate,
    PublicationReconciliationCreate,
    PublicationReconciliationRecord,
    RemoteTaskBinding,
    RemoteTaskState,
    RunEvent,
    RunStatus,
    ScriptAuthoringProvenance,
    ScriptRevision,
    ScriptRevisionCreate,
    Season,
    SeasonCreate,
    SeasonPlanApproval,
    SeasonPlanApprovalCreate,
    SeasonPlanRevision,
    SeasonPlanUpdate,
)
from .publication_learning import (
    PublicationLearningVerifier,
    PublicationVerificationError,
)
from .release_evidence import (
    ReleaseEvidenceVerificationError,
    ReleaseEvidenceVerifier,
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def decode(value: str) -> Any:
    return json.loads(value)


SCRIPT_AUTHORING_PROVENANCE_KEY = "_nalu_script_authoring_provenance"


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _seal_script_authoring_provenance(
    request: ScriptRevisionCreate,
) -> ScriptAuthoringProvenance:
    external_writer = (
        request.authoring.external_writer.model_dump(mode="json")
        if request.authoring.external_writer is not None
        else None
    )
    external_origin = request.authoring.origin in {
        "external_ai_generated",
        "external_ai_assisted",
    }
    body = {
        "schema_version": "nalu.script-authoring-provenance/v1",
        "origin": request.authoring.origin,
        "content_sha256": _text_sha256(request.content),
        "source_transcript_sha256": _text_sha256(request.source_transcript),
        "external_writer": external_writer,
        "verification_status": "external_unverified" if external_origin else "user_attested",
        "writer_receipt_verified": False,
        "network_call_performed_by_runtime": False,
    }
    return ScriptAuthoringProvenance.model_validate(
        {**body, "provenance_sha256": _text_sha256(encode(body))}
    )


def _verify_script_authoring_provenance(
    *, content: Any, source_transcript: Any, raw_provenance: Any
) -> ScriptAuthoringProvenance:
    if not isinstance(content, str) or not isinstance(source_transcript, str):
        raise ConflictError("script provenance cannot bind non-text script fields")
    if raw_provenance is None:
        body = {
            "schema_version": "nalu.script-authoring-provenance/v1",
            "origin": "legacy_unknown",
            "content_sha256": _text_sha256(content),
            "source_transcript_sha256": _text_sha256(source_transcript),
            "external_writer": None,
            "verification_status": "legacy_unverified",
            "writer_receipt_verified": False,
            "network_call_performed_by_runtime": False,
        }
        return ScriptAuthoringProvenance.model_validate(
            {**body, "provenance_sha256": _text_sha256(encode(body))}
        )
    if not isinstance(raw_provenance, dict):
        raise ConflictError("script authoring provenance is not an object")
    try:
        provenance = ScriptAuthoringProvenance.model_validate(raw_provenance)
    except ValueError as exc:
        raise ConflictError("script authoring provenance is invalid") from exc
    body = provenance.model_dump(mode="json", exclude={"provenance_sha256"})
    if (
        provenance.content_sha256 != _text_sha256(content)
        or provenance.source_transcript_sha256 != _text_sha256(source_transcript)
        or provenance.provenance_sha256 != _text_sha256(encode(body))
    ):
        raise ConflictError("script authoring provenance digest mismatch")
    return provenance


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
            "feedback_triage_records": (
                """SELECT t.* FROM feedback_triage_records t
                   JOIN feedback_items f ON f.id = t.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_external_exports": (
                """SELECT x.* FROM feedback_external_exports x
                   JOIN feedback_items f ON f.id = x.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_external_reconciliations": (
                """SELECT r.* FROM feedback_external_reconciliations r
                   JOIN feedback_items f ON f.id = r.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_development_work_orders": (
                """SELECT w.* FROM feedback_development_work_orders w
                   JOIN feedback_items f ON f.id = w.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_development_handoffs": (
                """SELECT h.* FROM feedback_development_handoffs h
                   JOIN feedback_items f ON f.id = h.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_development_handoff_reconciliations": (
                """SELECT r.* FROM feedback_development_handoff_reconciliations r
                   JOIN feedback_items f ON f.id = r.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_development_results": (
                """SELECT d.* FROM feedback_development_results d
                   JOIN feedback_items f ON f.id = d.feedback_id
                   WHERE f.project_id = ?""",
                (project_id,),
            ),
            "feedback_release_evidence_reconciliations": (
                """SELECT r.* FROM feedback_release_evidence_reconciliations r
                   JOIN feedback_items f ON f.id = r.feedback_id
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
            "production_runs": (
                """SELECT r.* FROM production_runs r
                   WHERE r.project_id = ? AND EXISTS (
                     SELECT 1 FROM publication_reconciliations p WHERE p.run_id = r.id
                   )""",
                (project_id,),
            ),
            "publication_reconciliations": (
                """SELECT p.* FROM publication_reconciliations p
                   JOIN production_runs r ON r.id = p.run_id WHERE r.project_id = ?""",
                (project_id,),
            ),
            "publication_metric_snapshots": (
                """SELECT m.* FROM publication_metric_snapshots m
                   JOIN production_runs r ON r.id = m.run_id WHERE r.project_id = ?""",
                (project_id,),
            ),
            "director_strategy_revisions": (
                "SELECT * FROM director_strategy_revisions WHERE project_id = ?",
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
            "feedback_triage_records": (
                "feedback_id",
                "request_sha256",
                "record_json",
                "record_sha256",
                "created_at",
            ),
            "feedback_external_exports": (
                "feedback_id",
                "policy_sha256",
                "policy_json",
                "idempotency_key_sha256",
                "confirmation_sha256",
                "request_sha256",
                "state",
                "payload_json",
                "payload_sha256",
                "response_json",
                "response_sha256",
                "remote_issue_id",
                "remote_issue_url",
                "error",
                "created_at",
                "updated_at",
            ),
            "feedback_external_reconciliations": (
                "feedback_id",
                "request_sha256",
                "record_json",
                "record_sha256",
                "created_at",
            ),
            "feedback_development_work_orders": (
                "feedback_id",
                "request_sha256",
                "record_json",
                "record_sha256",
                "created_at",
            ),
            "feedback_development_handoffs": (
                "feedback_id",
                "policy_sha256",
                "policy_json",
                "idempotency_key_sha256",
                "confirmation_sha256",
                "request_sha256",
                "state",
                "payload_json",
                "payload_sha256",
                "response_json",
                "response_sha256",
                "remote_task_id",
                "remote_task_url",
                "error",
                "created_at",
                "updated_at",
            ),
            "feedback_development_handoff_reconciliations": (
                "feedback_id",
                "request_sha256",
                "record_json",
                "record_sha256",
                "created_at",
            ),
            "feedback_development_results": (
                "feedback_id",
                "request_sha256",
                "record_json",
                "record_sha256",
                "created_at",
            ),
            "feedback_release_evidence_reconciliations": (
                "feedback_id",
                "request_sha256",
                "record_json",
                "record_sha256",
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
            "production_runs": (
                "id",
                "project_id",
                "season_id",
                "episode_id",
                "status",
                "dry_run",
                "requested_model",
                "estimated_budget_credits",
                "package_path",
                "error",
                "created_at",
                "updated_at",
            ),
            "publication_reconciliations": (
                "run_id",
                "platform",
                "remote_publication_id",
                "request_sha256",
                "idempotency_key_sha256",
                "record_json",
                "record_sha256",
                "created_at",
            ),
            "publication_metric_snapshots": (
                "id",
                "run_id",
                "platform",
                "remote_publication_id",
                "window_start",
                "window_end",
                "request_sha256",
                "idempotency_key_sha256",
                "snapshot_json",
                "snapshot_sha256",
                "created_at",
            ),
            "director_strategy_revisions": (
                "id",
                "project_id",
                "target_episode_id",
                "source_metrics_id",
                "revision",
                "strategy_json",
                "strategy_sha256",
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
            "nalu.project-export/v6",
            "nalu.project-export/v7",
            "nalu.project-export/v8",
            "nalu.project-export/v9",
            "nalu.project-export/v10",
        }:
            allowed_columns.pop("feedback_triage_records")
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
            "nalu.project-export/v10",
            "nalu.project-export/v11",
        }:
            allowed_columns.pop("feedback_external_exports")
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
            "nalu.project-export/v10",
            "nalu.project-export/v11",
            "nalu.project-export/v12",
        }:
            allowed_columns.pop("feedback_external_reconciliations")
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
            "nalu.project-export/v10",
            "nalu.project-export/v11",
            "nalu.project-export/v12",
            "nalu.project-export/v13",
        }:
            allowed_columns.pop("feedback_development_work_orders")
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
            "nalu.project-export/v10",
            "nalu.project-export/v11",
            "nalu.project-export/v12",
            "nalu.project-export/v13",
            "nalu.project-export/v14",
        }:
            allowed_columns.pop("feedback_development_handoffs")
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
            "nalu.project-export/v10",
            "nalu.project-export/v11",
            "nalu.project-export/v12",
            "nalu.project-export/v13",
            "nalu.project-export/v14",
            "nalu.project-export/v15",
        }:
            allowed_columns.pop("feedback_development_handoff_reconciliations")
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
            "nalu.project-export/v10",
            "nalu.project-export/v11",
            "nalu.project-export/v12",
            "nalu.project-export/v13",
            "nalu.project-export/v14",
            "nalu.project-export/v15",
            "nalu.project-export/v16",
        }:
            allowed_columns.pop("feedback_development_results")
        if backup.schema_version not in {
            "nalu.project-export/v19",
            "nalu.project-export/v20",
        }:
            allowed_columns.pop("feedback_release_evidence_reconciliations")
        if backup.schema_version != "nalu.project-export/v20":
            allowed_columns.pop("production_runs")
            allowed_columns.pop("publication_reconciliations")
            allowed_columns.pop("publication_metric_snapshots")
            allowed_columns.pop("director_strategy_revisions")
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
        for row in backup.payload["script_revisions"]:
            try:
                metadata = decode(row.get("narrative_metadata_json", ""))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ConflictError("project export contains unreadable script metadata") from exc
            if not isinstance(metadata, dict):
                raise ConflictError("project export contains invalid script metadata")
            _verify_script_authoring_provenance(
                content=row.get("content"),
                source_transcript=row.get("source_transcript"),
                raw_provenance=metadata.get(SCRIPT_AUTHORING_PROVENANCE_KEY),
            )
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
            or (row.get("episode_id"), row.get("reviewed_script_revision"))
            not in script_revision_keys
            for row in backup.payload.get("continuity_extraction_confirmation_records", [])
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
                raise ConflictError(
                    "project export contains an unreadable feedback bundle"
                ) from exc
            if (
                bundle_body.get("feedback_id") != row.get("feedback_id")
                or bundle_body.get("request_sha256") != row.get("request_sha256")
                or hashlib.sha256(encode(bundle_body).encode()).hexdigest()
                != row.get("bundle_sha256")
            ):
                raise ConflictError("project export contains a tampered feedback bundle")
            feedback_bundle_digests[row.get("feedback_id")] = row.get("bundle_sha256")
        feedback_release_linkages: dict[Any, FeedbackReleaseLinkage] = {}
        for row in backup.payload.get("feedback_release_linkages", []):
            try:
                linkage_body = decode(row.get("linkage_json", ""))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ConflictError(
                    "project export contains an unreadable release linkage"
                ) from exc
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
            if validated.development_result_sha256 is not None:
                request_body["development_result_sha256"] = validated.development_result_sha256
            if hashlib.sha256(encode(request_body).encode()).hexdigest() != row.get(
                "request_sha256"
            ):
                raise ConflictError("release linkage request digest does not match its evidence")
            feedback_release_linkages[row.get("feedback_id")] = validated
        feedback_triage_digests: dict[Any, Any] = {}
        for row in backup.payload.get("feedback_triage_records", []):
            try:
                record_body = decode(row.get("record_json", ""))
            except (TypeError, json.JSONDecodeError) as exc:
                raise ConflictError("project export contains unreadable feedback triage") from exc
            if (
                row.get("feedback_id") not in feedback_ids
                or record_body.get("feedback_id") != row.get("feedback_id")
                or record_body.get("request_sha256") != row.get("request_sha256")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
            ):
                raise ConflictError("project export contains tampered feedback triage")
            try:
                triage = FeedbackTriageRecord.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except ValueError as exc:
                raise ConflictError("project export contains invalid feedback triage") from exc
            if triage.review_bundle_sha256 != feedback_bundle_digests.get(row.get("feedback_id")):
                raise ConflictError("feedback triage references a different review bundle")
            if triage.duplicate_of_feedback_id is not None and (
                triage.disposition != "duplicate"
                or triage.duplicate_of_feedback_id not in feedback_ids
                or triage.duplicate_of_feedback_id == triage.feedback_id
            ):
                raise ConflictError("feedback triage has an invalid duplicate reference")
            evidence = {
                "review_bundle_sha256": triage.review_bundle_sha256,
                "priority": triage.priority,
                "disposition": triage.disposition,
                "duplicate_of_feedback_id": triage.duplicate_of_feedback_id,
                "rationale": triage.rationale,
                "reviewed_by": triage.reviewed_by,
                "reviewed_at": triage.reviewed_at,
            }
            request_body = {
                "feedback_id": triage.feedback_id,
                "idempotency_key_sha256": triage.idempotency_key_sha256,
                "confirmation_sha256": triage.confirmation_sha256,
                "evidence": evidence,
            }
            if hashlib.sha256(encode(request_body).encode()).hexdigest() != triage.request_sha256:
                raise ConflictError("feedback triage request digest does not match its evidence")
            feedback_triage_digests[row.get("feedback_id")] = row.get("record_sha256")
        feedback_external_exports: dict[Any, dict[str, Any]] = {}
        for row in backup.payload.get("feedback_external_exports", []):
            try:
                policy_body = decode(row.get("policy_json", ""))
                payload_body = decode(row.get("payload_json", ""))
                policy = FeedbackExportPolicy(**policy_body)
                policy.validate()
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError("project export contains invalid external export") from exc
            if (
                row.get("feedback_id") not in feedback_ids
                or hashlib.sha256(encode(policy_body).encode()).hexdigest()
                != row.get("policy_sha256")
                or hashlib.sha256(encode(payload_body).encode()).hexdigest()
                != row.get("payload_sha256")
                or payload_body.get("feedback", {}).get("id") != row.get("feedback_id")
                or payload_body.get("review_bundle", {}).get("sha256")
                != feedback_bundle_digests.get(row.get("feedback_id"))
                or payload_body.get("triage", {}).get("sha256")
                != feedback_triage_digests.get(row.get("feedback_id"))
                or payload_body.get("attachments") != []
            ):
                raise ConflictError("project export contains tampered external export")
            request_body = {
                "feedback_id": row.get("feedback_id"),
                "policy_sha256": row.get("policy_sha256"),
                "idempotency_key_sha256": row.get("idempotency_key_sha256"),
                "confirmation_sha256": row.get("confirmation_sha256"),
                "payload_sha256": row.get("payload_sha256"),
            }
            if hashlib.sha256(encode(request_body).encode()).hexdigest() != row.get(
                "request_sha256"
            ):
                raise ConflictError("external export request digest does not match")
            if row.get("state") not in {
                "submitting",
                "ambiguous",
                "confirmed",
                "rejected",
            }:
                raise ConflictError("project export contains invalid external export state")
            if row.get("state") == "confirmed":
                try:
                    response = decode(row.get("response_json", ""))
                    remote_url = urlsplit(row.get("remote_issue_url", ""))
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ConflictError("confirmed external export receipt is unreadable") from exc
                if (
                    hashlib.sha256(encode(response).encode()).hexdigest()
                    != row.get("response_sha256")
                    or not row.get("remote_issue_id")
                    or remote_url.scheme != "https"
                    or not remote_url.hostname
                    or remote_url.username is not None
                    or remote_url.password is not None
                    or remote_url.query
                    or remote_url.fragment
                    or (
                        backup.schema_version
                        in {
                            "nalu.project-export/v13",
                            "nalu.project-export/v14",
                            "nalu.project-export/v15",
                        }
                        and response
                        != {
                            "remote_issue_id": row.get("remote_issue_id"),
                            "remote_issue_url": row.get("remote_issue_url"),
                        }
                    )
                ):
                    raise ConflictError("confirmed external export receipt is invalid")
            elif any(
                row.get(field) is not None
                for field in (
                    "response_json",
                    "response_sha256",
                    "remote_issue_id",
                    "remote_issue_url",
                )
            ):
                raise ConflictError("unconfirmed external export contains a receipt")
            feedback_external_exports[row.get("feedback_id")] = row
        for row in backup.payload.get("feedback_external_reconciliations", []):
            try:
                record_body = decode(row.get("record_json", ""))
                record = FeedbackExternalReconciliationRecord.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError(
                    "project export contains invalid external reconciliation"
                ) from exc
            export = feedback_external_exports.get(row.get("feedback_id"))
            if (
                export is None
                or record.feedback_id != row.get("feedback_id")
                or record.export_request_sha256 != export.get("request_sha256")
                or record.payload_sha256 != export.get("payload_sha256")
                or record.idempotency_key_sha256 != export.get("idempotency_key_sha256")
                or record.request_sha256 != row.get("request_sha256")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
            ):
                raise ConflictError("project export contains tampered external reconciliation")
            reconciliation_request = {
                "feedback_id": record.feedback_id,
                "export_request_sha256": record.export_request_sha256,
                "payload_sha256": record.payload_sha256,
                "reconciled_by": record.reconciled_by,
                "reconciled_at": record.reconciled_at,
                "idempotency_key_sha256": record.idempotency_key_sha256,
                "confirmation_sha256": record.confirmation_sha256,
            }
            if (
                hashlib.sha256(encode(reconciliation_request).encode()).hexdigest()
                != record.request_sha256
            ):
                raise ConflictError("external reconciliation request digest does not match")
            if record.outcome == "confirmed" and (
                export.get("state") != "confirmed"
                or record.remote_issue_id != export.get("remote_issue_id")
                or record.remote_issue_url != export.get("remote_issue_url")
                or record.response_sha256 != export.get("response_sha256")
            ):
                raise ConflictError("confirmed reconciliation does not match export receipt")
            if record.outcome == "verified_absent" and export.get("state") != "rejected":
                raise ConflictError("absent reconciliation does not match export state")
        feedback_development_work_orders: dict[str, FeedbackDevelopmentWorkOrder] = {}
        for row in backup.payload.get("feedback_development_work_orders", []):
            try:
                record_body = decode(row.get("record_json", ""))
                work_order = FeedbackDevelopmentWorkOrder.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError(
                    "project export contains invalid development work order"
                ) from exc
            export = feedback_external_exports.get(row.get("feedback_id"))
            if export is None:
                raise ConflictError("development work order has no external export")
            try:
                export_policy = FeedbackExportPolicy(**decode(export.get("policy_json", "")))
                export_policy.validate()
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError("development work order export policy is invalid") from exc
            if (
                work_order.feedback_id != row.get("feedback_id")
                or work_order.project_id != project_id
                or work_order.triage_record_sha256
                != feedback_triage_digests.get(row.get("feedback_id"))
                or work_order.export_request_sha256 != export.get("request_sha256")
                or export.get("state") != "confirmed"
                or work_order.repository != export_policy.repository
                or work_order.remote_issue_id != export.get("remote_issue_id")
                or work_order.remote_issue_url != export.get("remote_issue_url")
                or work_order.request_sha256 != row.get("request_sha256")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
            ):
                raise ConflictError("project export contains tampered development work order")
            work_order_request = {
                "feedback_id": work_order.feedback_id,
                "triage_record_sha256": work_order.triage_record_sha256,
                "export_request_sha256": work_order.export_request_sha256,
                "title": work_order.title,
                "scope": work_order.scope,
                "acceptance_tests": work_order.acceptance_tests,
                "privacy_requirements": work_order.privacy_requirements,
                "accessibility_requirements": work_order.accessibility_requirements,
                "approved_by": work_order.approved_by,
                "approved_at": work_order.approved_at,
                "idempotency_key_sha256": work_order.idempotency_key_sha256,
                "confirmation_sha256": work_order.confirmation_sha256,
            }
            if (
                hashlib.sha256(encode(work_order_request).encode()).hexdigest()
                != work_order.request_sha256
            ):
                raise ConflictError("development work order request digest does not match")
            feedback_development_work_orders[work_order.feedback_id] = work_order
        feedback_development_handoffs: dict[str, dict[str, Any]] = {}
        for row in backup.payload.get("feedback_development_handoffs", []):
            work_order = feedback_development_work_orders.get(row.get("feedback_id"))
            try:
                policy_body = decode(row.get("policy_json", ""))
                payload_body = decode(row.get("payload_json", ""))
                policy = DevelopmentHandoffPolicy(**policy_body)
                policy.validate()
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError("project export contains invalid development handoff") from exc
            if (
                work_order is None
                or hashlib.sha256(encode(policy_body).encode()).hexdigest()
                != row.get("policy_sha256")
                or hashlib.sha256(encode(payload_body).encode()).hexdigest()
                != row.get("payload_sha256")
                or payload_body.get("feedback_id") != row.get("feedback_id")
                or payload_body.get("work_order_sha256") != work_order.record_sha256
                or payload_body.get("report_text_treated_as_inert") is not True
                or payload_body.get("automatic_actions")
                != {
                    "branch_created": False,
                    "code_change_performed": False,
                    "merge_performed": False,
                    "signing_performed": False,
                    "release_performed": False,
                }
            ):
                raise ConflictError("project export contains tampered development handoff")
            request_body = {
                "feedback_id": row.get("feedback_id"),
                "policy_sha256": row.get("policy_sha256"),
                "work_order_sha256": work_order.record_sha256,
                "idempotency_key_sha256": row.get("idempotency_key_sha256"),
                "confirmation_sha256": row.get("confirmation_sha256"),
                "payload_sha256": row.get("payload_sha256"),
            }
            if hashlib.sha256(encode(request_body).encode()).hexdigest() != row.get(
                "request_sha256"
            ):
                raise ConflictError("development handoff request digest does not match")
            if row.get("state") not in {
                "submitting",
                "ambiguous",
                "confirmed",
                "rejected",
            }:
                raise ConflictError("project export contains invalid development handoff state")
            receipt_fields = (
                row.get("response_json"),
                row.get("response_sha256"),
                row.get("remote_task_id"),
                row.get("remote_task_url"),
            )
            if row.get("state") == "confirmed":
                try:
                    response = decode(row.get("response_json", ""))
                    remote_url = urlsplit(row.get("remote_task_url", ""))
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ConflictError("development handoff receipt is unreadable") from exc
                if (
                    hashlib.sha256(encode(response).encode()).hexdigest()
                    != row.get("response_sha256")
                    or response
                    != {
                        "remote_task_id": row.get("remote_task_id"),
                        "remote_task_url": row.get("remote_task_url"),
                    }
                    or not row.get("remote_task_id")
                    or remote_url.scheme != "https"
                    or not remote_url.hostname
                    or remote_url.username is not None
                    or remote_url.password is not None
                    or remote_url.query
                    or remote_url.fragment
                ):
                    raise ConflictError("confirmed development handoff receipt is invalid")
            elif any(value is not None for value in receipt_fields):
                raise ConflictError("unconfirmed development handoff contains a receipt")
            feedback_development_handoffs[row["feedback_id"]] = row
        for row in backup.payload.get("feedback_development_handoff_reconciliations", []):
            try:
                record_body = decode(row.get("record_json", ""))
                record = FeedbackDevelopmentHandoffReconciliationRecord.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError(
                    "project export contains invalid development handoff reconciliation"
                ) from exc
            handoff = feedback_development_handoffs.get(row.get("feedback_id"))
            if (
                handoff is None
                or record.feedback_id != row.get("feedback_id")
                or record.handoff_request_sha256 != handoff.get("request_sha256")
                or record.payload_sha256 != handoff.get("payload_sha256")
                or record.idempotency_key_sha256 != handoff.get("idempotency_key_sha256")
                or record.request_sha256 != row.get("request_sha256")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
            ):
                raise ConflictError(
                    "project export contains tampered development handoff reconciliation"
                )
            reconciliation_request = {
                "feedback_id": record.feedback_id,
                "handoff_request_sha256": record.handoff_request_sha256,
                "payload_sha256": record.payload_sha256,
                "reconciled_by": record.reconciled_by,
                "reconciled_at": record.reconciled_at,
                "idempotency_key_sha256": record.idempotency_key_sha256,
                "confirmation_sha256": record.confirmation_sha256,
            }
            if (
                hashlib.sha256(encode(reconciliation_request).encode()).hexdigest()
                != record.request_sha256
            ):
                raise ConflictError(
                    "development handoff reconciliation request digest does not match"
                )
            if record.outcome == "confirmed" and (
                handoff.get("state") != "confirmed"
                or record.remote_task_id != handoff.get("remote_task_id")
                or record.remote_task_url != handoff.get("remote_task_url")
                or record.response_sha256 != handoff.get("response_sha256")
            ):
                raise ConflictError(
                    "confirmed development handoff reconciliation does not match receipt"
                )
            if record.outcome == "verified_absent" and handoff.get("state") != "rejected":
                raise ConflictError(
                    "absent development handoff reconciliation does not match state"
                )
        feedback_development_results: dict[Any, FeedbackDevelopmentResultRecord] = {}
        for row in backup.payload.get("feedback_development_results", []):
            try:
                record_body = decode(row.get("record_json", ""))
                record = FeedbackDevelopmentResultRecord.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except (TypeError, json.JSONDecodeError, ValueError) as exc:
                raise ConflictError("project export contains invalid development result") from exc
            handoff = feedback_development_handoffs.get(row.get("feedback_id"))
            work_order = feedback_development_work_orders.get(row.get("feedback_id"))
            review_url = urlsplit(record.review_url)
            expected_repository_url = (
                f"https://github.com/{work_order.repository}" if work_order else None
            )
            if (
                handoff is None
                or work_order is None
                or handoff.get("state") != "confirmed"
                or record.feedback_id != row.get("feedback_id")
                or record.handoff_request_sha256 != handoff.get("request_sha256")
                or record.handoff_response_sha256 != handoff.get("response_sha256")
                or record.remote_task_id != handoff.get("remote_task_id")
                or record.repository_url != expected_repository_url
                or review_url.scheme != "https"
                or review_url.hostname != "github.com"
                or not re.fullmatch(
                    rf"/{re.escape(work_order.repository)}/pull/[1-9][0-9]*",
                    review_url.path,
                )
                or review_url.query
                or review_url.fragment
                or not re.fullmatch(
                    r"(?=.{1,200}$)(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+",
                    record.branch_name,
                )
                or ".." in record.branch_name
                or record.request_sha256 != row.get("request_sha256")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
            ):
                raise ConflictError("project export contains tampered development result")
            result_request = {
                "feedback_id": record.feedback_id,
                "handoff_request_sha256": record.handoff_request_sha256,
                "handoff_response_sha256": record.handoff_response_sha256,
                "verified_by": record.verified_by,
                "verified_at": record.verified_at,
                "idempotency_key_sha256": record.idempotency_key_sha256,
                "confirmation_sha256": record.confirmation_sha256,
            }
            if hashlib.sha256(encode(result_request).encode()).hexdigest() != record.request_sha256:
                raise ConflictError("development result request digest does not match")
            feedback_development_results[row.get("feedback_id")] = record
        for feedback_id, linkage in feedback_release_linkages.items():
            result = feedback_development_results.get(feedback_id)
            if backup.schema_version in {
                "nalu.project-export/v18",
                "nalu.project-export/v19",
                "nalu.project-export/v20",
            } and (
                result is None
                or linkage.development_result_sha256 != result.record_sha256
                or linkage.reviewed_change.repository_url != result.repository_url
                or linkage.reviewed_change.review_url != result.review_url
                or linkage.reviewed_change.commit_sha != result.commit_sha
                or linkage.reviewed_change.test_evidence_sha256 != result.test_evidence_sha256
            ):
                raise ConflictError(
                    "release linkage does not match the verified development result"
                )
        for row in backup.payload.get("feedback_release_evidence_reconciliations", []):
            try:
                record_body = decode(row.get("record_json", ""))
                record = FeedbackReleaseEvidenceReconciliationRecord.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConflictError(
                    "project export contains invalid release evidence reconciliation"
                ) from exc
            linkage = feedback_release_linkages.get(row.get("feedback_id"))
            reconciliation_request = {
                "feedback_id": record.feedback_id,
                "release_linkage_sha256": record.release_linkage_sha256,
                "idempotency_key_sha256": record.idempotency_key_sha256,
            }
            if (
                record.feedback_id != row.get("feedback_id")
                or linkage is None
                or record.release_linkage_sha256 != linkage.linkage_sha256
                or record.request_sha256 != row.get("request_sha256")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
                or hashlib.sha256(encode(reconciliation_request).encode()).hexdigest()
                != record.request_sha256
            ):
                raise ConflictError(
                    "project export contains tampered release evidence reconciliation"
                )
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
        learning_run_ids = {row.get("id") for row in backup.payload.get("production_runs", [])}
        learning_runs = {row.get("id"): row for row in backup.payload.get("production_runs", [])}
        if any(
            row.get("project_id") != project_id
            or row.get("season_id") not in season_ids
            or row.get("episode_id") not in episode_ids
            or row.get("status") != RunStatus.COMPLETED
            or row.get("dry_run") not in {0, 1}
            or not isinstance(row.get("package_path"), str)
            or not row.get("package_path")
            for row in backup.payload.get("production_runs", [])
        ):
            raise ConflictError("project export contains an invalid publication source run")
        publication_records: dict[tuple[Any, Any], PublicationReconciliationRecord] = {}
        for row in backup.payload.get("publication_reconciliations", []):
            try:
                record_body = decode(row.get("record_json", ""))
                record = PublicationReconciliationRecord.model_validate(
                    {**record_body, "record_sha256": row.get("record_sha256")}
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConflictError(
                    "project export contains invalid publication reconciliation"
                ) from exc
            source_run = learning_runs.get(row.get("run_id"))
            if (
                source_run is None
                or record.run_id != row.get("run_id")
                or record.project_id != project_id
                or record.episode_id != source_run.get("episode_id")
                or record.platform != row.get("platform")
                or record.remote_publication_id != row.get("remote_publication_id")
                or record.request_sha256 != row.get("request_sha256")
                or record.idempotency_key_sha256 != row.get("idempotency_key_sha256")
                or record.created_at != row.get("created_at")
                or hashlib.sha256(encode(record_body).encode()).hexdigest()
                != row.get("record_sha256")
            ):
                raise ConflictError("project export contains tampered publication reconciliation")
            publication_records[(record.run_id, record.platform)] = record
        metric_records: dict[Any, PublicationMetricsSnapshot] = {}
        for row in backup.payload.get("publication_metric_snapshots", []):
            try:
                snapshot_body = decode(row.get("snapshot_json", ""))
                snapshot = PublicationMetricsSnapshot.model_validate(
                    {**snapshot_body, "snapshot_sha256": row.get("snapshot_sha256")}
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConflictError("project export contains invalid publication metrics") from exc
            source_run = learning_runs.get(row.get("run_id"))
            publication = publication_records.get((row.get("run_id"), row.get("platform")))
            if (
                source_run is None
                or publication is None
                or snapshot.id != row.get("id")
                or snapshot.run_id != row.get("run_id")
                or snapshot.project_id != project_id
                or snapshot.episode_id != source_run.get("episode_id")
                or snapshot.platform != row.get("platform")
                or snapshot.remote_publication_id != row.get("remote_publication_id")
                or snapshot.publication_record_sha256 != publication.record_sha256
                or snapshot.window_start != row.get("window_start")
                or snapshot.window_end != row.get("window_end")
                or snapshot.request_sha256 != row.get("request_sha256")
                or snapshot.idempotency_key_sha256 != row.get("idempotency_key_sha256")
                or snapshot.created_at != row.get("created_at")
                or hashlib.sha256(encode(snapshot_body).encode()).hexdigest()
                != row.get("snapshot_sha256")
            ):
                raise ConflictError("project export contains tampered publication metrics")
            metric_records[snapshot.id] = snapshot
        strategy_revisions: list[int] = []
        for row in backup.payload.get("director_strategy_revisions", []):
            try:
                strategy_body = decode(row.get("strategy_json", ""))
                strategy = DirectorStrategyRevision.model_validate(
                    {**strategy_body, "strategy_sha256": row.get("strategy_sha256")}
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ConflictError("project export contains invalid director strategy") from exc
            source_metrics = metric_records.get(row.get("source_metrics_id"))
            if (
                source_metrics is None
                or strategy.id != row.get("id")
                or strategy.project_id != project_id
                or strategy.target_episode_id not in episode_ids
                or strategy.source_metrics_id != row.get("source_metrics_id")
                or strategy.source_metrics_sha256 != source_metrics.snapshot_sha256
                or strategy.revision != row.get("revision")
                or strategy.created_at != row.get("created_at")
                or hashlib.sha256(encode(strategy_body).encode()).hexdigest()
                != row.get("strategy_sha256")
            ):
                raise ConflictError("project export contains tampered director strategy")
            strategy_revisions.append(strategy.revision)
        if strategy_revisions and sorted(strategy_revisions) != list(
            range(1, len(strategy_revisions) + 1)
        ):
            raise ConflictError("project export contains a non-contiguous strategy history")
        if learning_run_ids and not publication_records:
            raise ConflictError("project export contains an unused publication source run")
        try:
            with self.db.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for table, columns in allowed_columns.items():
                    placeholders = ", ".join("?" for _ in columns)
                    column_sql = ", ".join(columns)
                    for row in backup.payload[table]:
                        if set(row) != set(columns):
                            raise ConflictError(f"invalid columns in project export table {table}")
                        values = dict(row)
                        if table == "production_runs":
                            values["package_path"] = str(
                                self.db.path.parent
                                / "restored-publication-sources"
                                / str(row["id"])
                                / "production-package.json"
                            )
                        connection.execute(
                            f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
                            tuple(values[column] for column in columns),
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

    @staticmethod
    def _explicit_feedback_triage_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in ("我确认这份分诊", "我同意保存分诊", "确认人工分诊结果")
        )

    def create_feedback_triage_record(
        self,
        feedback_id: str,
        request: FeedbackTriageCreate,
        idempotency_key: str | None,
    ) -> FeedbackTriageRecord:
        feedback = self.get_feedback(feedback_id)
        if not feedback.share_authorized or feedback.status != "ready_for_review":
            raise ConflictError("local-only feedback cannot be triaged for development")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_feedback_triage_confirmation(request.confirmation_text):
            raise ConflictError("feedback triage requires explicit human confirmation")
        bundle = self.get_feedback_review_bundle(feedback_id)
        if request.review_bundle_sha256 != bundle.bundle_sha256:
            raise ConflictError("triage review bundle digest does not match")
        if request.duplicate_of_feedback_id:
            if request.duplicate_of_feedback_id == feedback_id:
                raise ConflictError("feedback cannot be a duplicate of itself")
            duplicate = self.get_feedback(request.duplicate_of_feedback_id)
            if duplicate.project_id != feedback.project_id:
                raise ConflictError("duplicate feedback must belong to the same project")

        rationale, rationale_redacted = self._redact_feedback_message(request.rationale)
        reviewed_by, reviewer_redacted = self._redact_feedback_message(request.reviewed_by)
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        evidence = {
            "review_bundle_sha256": request.review_bundle_sha256,
            "priority": request.priority,
            "disposition": request.disposition,
            "duplicate_of_feedback_id": request.duplicate_of_feedback_id,
            "rationale": rationale,
            "reviewed_by": reviewed_by,
            "reviewed_at": request.reviewed_at,
        }
        request_body = {
            "feedback_id": feedback_id,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "evidence": evidence,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_triage_records WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("feedback already has a different immutable triage record")
            stored = decode(existing["record_json"])
            if hashlib.sha256(encode(stored).encode()).hexdigest() != existing["record_sha256"]:
                raise ConflictError("stored feedback triage record digest mismatch")
            stored["record_sha256"] = existing["record_sha256"]
            return FeedbackTriageRecord.model_validate(stored)

        now = utc_now()
        record_body = {
            "schema_version": "nalu.feedback-triage/v1",
            "feedback_id": feedback_id,
            **evidence,
            "status": "triaged_local",
            "human_review_confirmed": True,
            "redaction_applied": bool(rationale_redacted or reviewer_redacted),
            "tool_calls": [],
            "code_change_performed": False,
            "network_call_performed": False,
            "created_at": now,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "request_sha256": request_sha256,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        with self.db.connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO feedback_triage_records VALUES (?, ?, ?, ?, ?)",
                    (feedback_id, request_sha256, encode(record_body), record_sha256, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("feedback triage was created concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return FeedbackTriageRecord.model_validate(record_body)

    def get_feedback_triage_record(self, feedback_id: str) -> FeedbackTriageRecord:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_triage_records WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback triage record not found")
        stored = decode(row["record_json"])
        if hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]:
            raise ConflictError("stored feedback triage record digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return FeedbackTriageRecord.model_validate(stored)

    @staticmethod
    def _explicit_feedback_export_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in ("我确认导出问题单", "我同意发送审核资料", "确认发送到问题跟踪器")
        )

    def export_feedback_to_issue_tracker(
        self,
        feedback_id: str,
        request: FeedbackExternalExportCreate,
        idempotency_key: str | None,
        policy: FeedbackExportPolicy,
        transport: IssueTrackerTransport,
    ) -> FeedbackExternalExportReceipt:
        policy.validate()
        if not policy.enabled or not policy.administrator_authorized:
            raise ConflictError("external feedback export is disabled")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_feedback_export_confirmation(request.confirmation_text):
            raise ConflictError("external feedback export requires explicit confirmation")
        feedback = self.get_feedback(feedback_id)
        if not feedback.share_authorized or feedback.status != "ready_for_review":
            raise ConflictError("local-only feedback cannot be exported")
        bundle = self.get_feedback_review_bundle(feedback_id)
        triage = self.get_feedback_triage_record(feedback_id)
        if request.review_bundle_sha256 != bundle.bundle_sha256:
            raise ConflictError("export review bundle digest does not match")
        if request.triage_record_sha256 != triage.record_sha256:
            raise ConflictError("export triage record digest does not match")

        payload = {
            "schema_version": "nalu.feedback-issue-payload/v1",
            "feedback": {
                "id": feedback.id,
                "category": feedback.category,
                "redacted_message": feedback.message,
                "source": feedback.source,
                "screen": feedback.screen,
            },
            "review_bundle": {
                "sha256": bundle.bundle_sha256,
                "expected_behavior": bundle.expected_behavior,
                "actual_behavior": bundle.actual_behavior,
                "reproduction_steps": bundle.reproduction_steps,
                "diagnostics": bundle.diagnostics,
            },
            "triage": {
                "sha256": triage.record_sha256,
                "priority": triage.priority,
                "disposition": triage.disposition,
                "duplicate_of_feedback_id": triage.duplicate_of_feedback_id,
                "rationale": triage.rationale,
                "reviewed_by": triage.reviewed_by,
                "reviewed_at": triage.reviewed_at,
            },
            "attachments": [],
        }
        payload_json = encode(payload)
        if len(payload_json.encode()) > policy.max_payload_bytes:
            raise ConflictError("redacted issue payload exceeds the configured limit")
        payload_sha256 = hashlib.sha256(payload_json.encode()).hexdigest()
        policy_body = {
            "schema_version": policy.schema_version,
            "enabled": policy.enabled,
            "administrator_authorized": policy.administrator_authorized,
            "provider": policy.provider,
            "endpoint": policy.endpoint,
            "repository": policy.repository,
            "max_payload_bytes": policy.max_payload_bytes,
        }
        policy_sha256 = hashlib.sha256(encode(policy_body).encode()).hexdigest()
        policy_json = encode(policy_body)
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "policy_sha256": policy_sha256,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "payload_sha256": payload_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_external_exports WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if (
                existing["policy_sha256"] != policy_sha256
                or existing["idempotency_key_sha256"] != idempotency_key_sha256
                or existing["request_sha256"] != request_sha256
            ):
                raise ConflictError("feedback export already has different immutable inputs")
            if existing["state"] != "confirmed":
                raise ConflictError("feedback export requires administrator reconciliation")
            return self.get_feedback_external_export(feedback_id)

        now = utc_now()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO feedback_external_exports VALUES (
                       ?, ?, ?, ?, ?, ?, 'submitting', ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?
                    )""",
                    (
                        feedback_id,
                        policy_sha256,
                        policy_json,
                        idempotency_key_sha256,
                        confirmation_sha256,
                        request_sha256,
                        payload_json,
                        payload_sha256,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            with self.db.connect() as connection:
                concurrent = connection.execute(
                    "SELECT * FROM feedback_external_exports WHERE feedback_id = ?",
                    (feedback_id,),
                ).fetchone()
            if (
                concurrent is not None
                and concurrent["policy_sha256"] == policy_sha256
                and concurrent["idempotency_key_sha256"] == idempotency_key_sha256
                and concurrent["request_sha256"] == request_sha256
                and concurrent["state"] == "confirmed"
            ):
                return self.get_feedback_external_export(feedback_id)
            raise ConflictError(
                "feedback export was created concurrently and requires reconciliation"
            ) from exc
        try:
            receipt = transport.create_issue(
                endpoint=policy.endpoint,
                repository=policy.repository,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            parsed = urlsplit(receipt.remote_issue_url)
            if (
                not receipt.remote_issue_id
                or len(receipt.remote_issue_id) > 160
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("issue tracker returned an invalid receipt")
            response_json = encode(
                {
                    "remote_issue_id": receipt.remote_issue_id,
                    "remote_issue_url": receipt.remote_issue_url,
                }
            )
            if len(response_json.encode()) > policy.max_payload_bytes:
                raise ValueError("issue tracker response exceeds the configured limit")
            response_sha256 = hashlib.sha256(response_json.encode()).hexdigest()
        except Exception as exc:
            with self.db.connect() as connection:
                connection.execute(
                    """UPDATE feedback_external_exports
                       SET state = 'ambiguous', error = ?, updated_at = ?
                       WHERE feedback_id = ? AND state = 'submitting'""",
                    (type(exc).__name__, utc_now(), feedback_id),
                )
            raise ConflictError(
                "external feedback export outcome is ambiguous; automatic retry is forbidden"
            ) from exc

        updated_at = utc_now()
        with self.db.connect() as connection:
            updated = connection.execute(
                """UPDATE feedback_external_exports
                   SET state = 'confirmed', response_json = ?, response_sha256 = ?,
                       remote_issue_id = ?, remote_issue_url = ?, updated_at = ?
                   WHERE feedback_id = ? AND state = 'submitting'""",
                (
                    response_json,
                    response_sha256,
                    receipt.remote_issue_id,
                    receipt.remote_issue_url,
                    updated_at,
                    feedback_id,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("feedback export state changed concurrently")
        return self.get_feedback_external_export(feedback_id)

    def get_feedback_external_export(self, feedback_id: str) -> FeedbackExternalExportReceipt:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_external_exports WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback external export not found")
        if row["state"] != "confirmed":
            raise ConflictError("feedback export is not confirmed")
        try:
            response = decode(row["response_json"])
            remote_url = urlsplit(row["remote_issue_url"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ConflictError("stored feedback export receipt is unreadable") from exc
        if (
            hashlib.sha256(row["payload_json"].encode()).hexdigest() != row["payload_sha256"]
            or hashlib.sha256(encode(response).encode()).hexdigest() != row["response_sha256"]
            or not row["remote_issue_id"]
            or remote_url.scheme != "https"
            or not remote_url.hostname
            or remote_url.username is not None
            or remote_url.password is not None
            or remote_url.query
            or remote_url.fragment
        ):
            raise ConflictError("stored feedback export digest mismatch")
        return FeedbackExternalExportReceipt(
            feedback_id=feedback_id,
            provider="github_issues",
            repository=self._feedback_export_repository(row["policy_sha256"], row["policy_json"]),
            state="confirmed",
            remote_issue_id=row["remote_issue_id"],
            remote_issue_url=row["remote_issue_url"],
            payload_sha256=row["payload_sha256"],
            response_sha256=row["response_sha256"],
            idempotency_key_sha256=row["idempotency_key_sha256"],
            request_sha256=row["request_sha256"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _feedback_export_repository(policy_sha256: str, policy_json: str) -> str:
        if hashlib.sha256(policy_json.encode()).hexdigest() != policy_sha256:
            raise ConflictError("stored feedback export policy digest mismatch")
        try:
            policy = FeedbackExportPolicy(**decode(policy_json))
            policy.validate()
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ConflictError("stored feedback export policy target is invalid") from exc
        return policy.repository

    @staticmethod
    def _explicit_feedback_reconciliation_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in ("我确认核对导出结果", "我同意保存对账结果", "确认问题单对账")
        )

    def reconcile_feedback_external_export(
        self,
        feedback_id: str,
        request: FeedbackExternalReconciliationCreate,
        idempotency_key: str | None,
        policy: FeedbackExportPolicy,
        verifier: IssueTrackerReconciliationVerifier,
    ) -> FeedbackExternalReconciliationRecord:
        policy.validate()
        if not policy.enabled or not policy.administrator_authorized:
            raise ConflictError("external feedback reconciliation is disabled")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("the original stable idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_feedback_reconciliation_confirmation(request.confirmation_text):
            raise ConflictError("external feedback reconciliation requires confirmation")
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            export = connection.execute(
                "SELECT * FROM feedback_external_exports WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if export is None:
            raise NotFoundError("feedback external export not found")
        if request.payload_sha256 != export["payload_sha256"]:
            raise ConflictError("reconciliation payload digest does not match")
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        if idempotency_key_sha256 != export["idempotency_key_sha256"]:
            raise ConflictError("reconciliation idempotency key does not match the export")
        policy_body = {
            "schema_version": policy.schema_version,
            "enabled": policy.enabled,
            "administrator_authorized": policy.administrator_authorized,
            "provider": policy.provider,
            "endpoint": policy.endpoint,
            "repository": policy.repository,
            "max_payload_bytes": policy.max_payload_bytes,
        }
        if hashlib.sha256(encode(policy_body).encode()).hexdigest() != export["policy_sha256"]:
            raise ConflictError("reconciliation policy differs from the export policy")
        reconciled_by, _ = self._redact_feedback_message(request.reconciled_by)
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "export_request_sha256": export["request_sha256"],
            "payload_sha256": request.payload_sha256,
            "reconciled_by": reconciled_by,
            "reconciled_at": request.reconciled_at,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_external_reconciliations WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("feedback export already has different reconciliation")
            return self.get_feedback_external_reconciliation(feedback_id)
        if export["state"] not in {"submitting", "ambiguous"}:
            raise ConflictError("only an uncertain feedback export can be reconciled")

        try:
            lookup = verifier.lookup_issue(
                endpoint=policy.endpoint,
                repository=policy.repository,
                payload_sha256=request.payload_sha256,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            raise ConflictError(
                "issue reconciliation could not independently determine the outcome"
            ) from exc
        evidence_json = encode(lookup.evidence)
        if not lookup.evidence or len(evidence_json.encode()) > policy.max_payload_bytes:
            raise ConflictError("issue reconciliation evidence is missing or too large")
        evidence_sha256 = hashlib.sha256(evidence_json.encode()).hexdigest()
        remote_issue_id: str | None = None
        remote_issue_url: str | None = None
        response_json: str | None = None
        response_sha256: str | None = None
        if lookup.outcome == "found" and lookup.receipt is not None:
            receipt = lookup.receipt
            parsed = urlsplit(receipt.remote_issue_url)
            if (
                not receipt.remote_issue_id
                or len(receipt.remote_issue_id) > 160
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ConflictError("reconciliation returned an invalid issue receipt")
            response_json = encode(
                {
                    "remote_issue_id": receipt.remote_issue_id,
                    "remote_issue_url": receipt.remote_issue_url,
                }
            )
            if len(response_json.encode()) > policy.max_payload_bytes:
                raise ConflictError("reconciliation response exceeds the configured limit")
            response_sha256 = hashlib.sha256(response_json.encode()).hexdigest()
            remote_issue_id = receipt.remote_issue_id
            remote_issue_url = receipt.remote_issue_url
            outcome = "confirmed"
            new_state = "confirmed"
            error = None
        elif lookup.outcome == "absent" and lookup.receipt is None:
            outcome = "verified_absent"
            new_state = "rejected"
            error = "verified_absent"
        else:
            raise ConflictError("reconciliation lookup result is internally inconsistent")

        now = utc_now()
        record_body = {
            "schema_version": "nalu.feedback-external-reconciliation/v1",
            "feedback_id": feedback_id,
            "export_request_sha256": export["request_sha256"],
            "payload_sha256": request.payload_sha256,
            "outcome": outcome,
            "remote_issue_id": remote_issue_id,
            "remote_issue_url": remote_issue_url,
            "response_sha256": response_sha256,
            "verification_evidence_sha256": evidence_sha256,
            "read_only_verification_performed": True,
            "issue_creation_retried": False,
            "external_write_performed": False,
            "reconciled_by": reconciled_by,
            "reconciled_at": request.reconciled_at,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "request_sha256": request_sha256,
            "created_at": now,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        try:
            with self.db.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    """UPDATE feedback_external_exports
                       SET state = ?, response_json = ?, response_sha256 = ?,
                           remote_issue_id = ?, remote_issue_url = ?, error = ?, updated_at = ?
                       WHERE feedback_id = ? AND state IN ('submitting', 'ambiguous')""",
                    (
                        new_state,
                        response_json,
                        response_sha256,
                        remote_issue_id,
                        remote_issue_url,
                        error,
                        now,
                        feedback_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise ConflictError("feedback export state changed during reconciliation")
                connection.execute(
                    "INSERT INTO feedback_external_reconciliations VALUES (?, ?, ?, ?, ?)",
                    (
                        feedback_id,
                        request_sha256,
                        encode(record_body),
                        record_sha256,
                        now,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError("feedback export was reconciled concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return FeedbackExternalReconciliationRecord.model_validate(record_body)

    def get_feedback_external_reconciliation(
        self, feedback_id: str
    ) -> FeedbackExternalReconciliationRecord:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_external_reconciliations WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback external reconciliation not found")
        stored = decode(row["record_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored feedback reconciliation digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return FeedbackExternalReconciliationRecord.model_validate(stored)

    @staticmethod
    def _explicit_work_order_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in ("我确认创建开发工单", "我同意进入人工开发", "确认开发范围")
        )

    def _clean_work_order_list(self, values: list[str], field: str) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            normalized, _ = self._redact_feedback_message(value.strip())
            if not normalized or len(normalized) > 500:
                raise ConflictError(f"{field} entries must contain 1-500 characters")
            if normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            raise ConflictError(f"{field} must contain at least one requirement")
        return cleaned

    def create_feedback_development_work_order(
        self,
        feedback_id: str,
        request: FeedbackDevelopmentWorkOrderCreate,
        idempotency_key: str | None,
    ) -> FeedbackDevelopmentWorkOrder:
        feedback = self.get_feedback(feedback_id)
        if not feedback.share_authorized or feedback.status != "ready_for_review":
            raise ConflictError("local-only feedback cannot create a development work order")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_work_order_confirmation(request.confirmation_text):
            raise ConflictError("development work order requires explicit human approval")
        triage = self.get_feedback_triage_record(feedback_id)
        if triage.disposition != "accepted":
            raise ConflictError("only accepted human triage can create a development work order")
        if request.triage_record_sha256 != triage.record_sha256:
            raise ConflictError("work order triage digest does not match")
        export = self.get_feedback_external_export(feedback_id)
        if request.export_request_sha256 != export.request_sha256:
            raise ConflictError("work order export receipt does not match")

        title, _ = self._redact_feedback_message(request.title.strip())
        scope, _ = self._redact_feedback_message(request.scope.strip())
        approved_by, _ = self._redact_feedback_message(request.approved_by.strip())
        if not title or not scope or not approved_by:
            raise ConflictError("work order title, scope and approver are required")
        acceptance_tests = self._clean_work_order_list(request.acceptance_tests, "acceptance_tests")
        privacy_requirements = self._clean_work_order_list(
            request.privacy_requirements, "privacy_requirements"
        )
        accessibility_requirements = self._clean_work_order_list(
            request.accessibility_requirements, "accessibility_requirements"
        )
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "triage_record_sha256": triage.record_sha256,
            "export_request_sha256": export.request_sha256,
            "title": title,
            "scope": scope,
            "acceptance_tests": acceptance_tests,
            "privacy_requirements": privacy_requirements,
            "accessibility_requirements": accessibility_requirements,
            "approved_by": approved_by,
            "approved_at": request.approved_at,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_development_work_orders WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("feedback already has a different development work order")
            return self.get_feedback_development_work_order(feedback_id)

        now = utc_now()
        record_body = {
            "schema_version": "nalu.feedback-development-work-order/v1",
            "feedback_id": feedback_id,
            "project_id": feedback.project_id,
            "repository": export.repository,
            "remote_issue_id": export.remote_issue_id,
            "remote_issue_url": export.remote_issue_url,
            "triage_record_sha256": triage.record_sha256,
            "export_request_sha256": export.request_sha256,
            "title": title,
            "scope": scope,
            "acceptance_tests": acceptance_tests,
            "privacy_requirements": privacy_requirements,
            "accessibility_requirements": accessibility_requirements,
            "approved_by": approved_by,
            "approved_at": request.approved_at,
            "status": "approved_local",
            "report_text_treated_as_inert": True,
            "tool_calls": [],
            "branch_created": False,
            "code_change_performed": False,
            "merge_performed": False,
            "signing_performed": False,
            "release_performed": False,
            "network_call_performed": False,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "request_sha256": request_sha256,
            "created_at": now,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    "INSERT INTO feedback_development_work_orders VALUES (?, ?, ?, ?, ?)",
                    (
                        feedback_id,
                        request_sha256,
                        encode(record_body),
                        record_sha256,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError("development work order was created concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return FeedbackDevelopmentWorkOrder.model_validate(record_body)

    def get_feedback_development_work_order(self, feedback_id: str) -> FeedbackDevelopmentWorkOrder:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_development_work_orders WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback development work order not found")
        stored = decode(row["record_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored development work order digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return FeedbackDevelopmentWorkOrder.model_validate(stored)

    @staticmethod
    def _explicit_development_handoff_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in (
                "我确认交给开发人员",
                "我同意发送开发工单",
                "确认提交开发工单",
            )
        )

    def handoff_feedback_to_development(
        self,
        feedback_id: str,
        request: FeedbackDevelopmentHandoffCreate,
        idempotency_key: str | None,
        policy: DevelopmentHandoffPolicy,
        transport: DevelopmentHandoffTransport,
    ) -> FeedbackDevelopmentHandoffReceipt:
        policy.validate()
        if not policy.enabled or not policy.administrator_authorized:
            raise ConflictError("development handoff is disabled")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_development_handoff_confirmation(request.confirmation_text):
            raise ConflictError("development handoff requires explicit confirmation")
        work_order = self.get_feedback_development_work_order(feedback_id)
        if request.work_order_sha256 != work_order.record_sha256:
            raise ConflictError("development handoff work order digest does not match")

        payload = {
            "schema_version": "nalu.development-handoff-payload/v1",
            "feedback_id": feedback_id,
            "work_order_sha256": work_order.record_sha256,
            "repository": work_order.repository,
            "remote_issue_id": work_order.remote_issue_id,
            "title": work_order.title,
            "scope": work_order.scope,
            "acceptance_tests": work_order.acceptance_tests,
            "privacy_requirements": work_order.privacy_requirements,
            "accessibility_requirements": work_order.accessibility_requirements,
            "report_text_treated_as_inert": True,
            "automatic_actions": {
                "branch_created": False,
                "code_change_performed": False,
                "merge_performed": False,
                "signing_performed": False,
                "release_performed": False,
            },
            "attachments": [],
        }
        payload_json = encode(payload)
        if len(payload_json.encode()) > policy.max_payload_bytes:
            raise ConflictError("development handoff payload exceeds the configured limit")
        payload_sha256 = hashlib.sha256(payload_json.encode()).hexdigest()
        policy_body = {
            "schema_version": policy.schema_version,
            "enabled": policy.enabled,
            "administrator_authorized": policy.administrator_authorized,
            "provider": policy.provider,
            "endpoint": policy.endpoint,
            "max_payload_bytes": policy.max_payload_bytes,
        }
        policy_json = encode(policy_body)
        policy_sha256 = hashlib.sha256(policy_json.encode()).hexdigest()
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "policy_sha256": policy_sha256,
            "work_order_sha256": work_order.record_sha256,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "payload_sha256": payload_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_development_handoffs WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if (
                existing["policy_sha256"] != policy_sha256
                or existing["idempotency_key_sha256"] != idempotency_key_sha256
                or existing["request_sha256"] != request_sha256
            ):
                raise ConflictError("development handoff already has different immutable inputs")
            if existing["state"] != "confirmed":
                raise ConflictError(
                    "development handoff outcome is uncertain; automatic retry is forbidden"
                )
            return self.get_feedback_development_handoff(feedback_id)

        now = utc_now()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """INSERT INTO feedback_development_handoffs VALUES (
                       ?, ?, ?, ?, ?, ?, 'submitting', ?, ?, NULL, NULL, NULL, NULL, NULL, ?, ?
                    )""",
                    (
                        feedback_id,
                        policy_sha256,
                        policy_json,
                        idempotency_key_sha256,
                        confirmation_sha256,
                        request_sha256,
                        payload_json,
                        payload_sha256,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                "development handoff was created concurrently and requires reconciliation"
            ) from exc

        try:
            receipt = transport.submit_work_order(
                endpoint=policy.endpoint,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            remote_url = urlsplit(receipt.remote_task_url)
            if (
                not receipt.remote_task_id
                or len(receipt.remote_task_id) > 160
                or remote_url.scheme != "https"
                or not remote_url.hostname
                or remote_url.username is not None
                or remote_url.password is not None
                or remote_url.query
                or remote_url.fragment
            ):
                raise ValueError("development agent returned an invalid receipt")
            response_json = encode(
                {
                    "remote_task_id": receipt.remote_task_id,
                    "remote_task_url": receipt.remote_task_url,
                }
            )
            if len(response_json.encode()) > policy.max_payload_bytes:
                raise ValueError("development handoff response exceeds the configured limit")
            response_sha256 = hashlib.sha256(response_json.encode()).hexdigest()
        except Exception as exc:
            with self.db.connect() as connection:
                connection.execute(
                    """UPDATE feedback_development_handoffs
                       SET state = 'ambiguous', error = ?, updated_at = ?
                       WHERE feedback_id = ? AND state = 'submitting'""",
                    (type(exc).__name__, utc_now(), feedback_id),
                )
            raise ConflictError(
                "development handoff outcome is ambiguous; automatic retry is forbidden"
            ) from exc

        updated_at = utc_now()
        with self.db.connect() as connection:
            updated = connection.execute(
                """UPDATE feedback_development_handoffs
                   SET state = 'confirmed', response_json = ?, response_sha256 = ?,
                       remote_task_id = ?, remote_task_url = ?, updated_at = ?
                   WHERE feedback_id = ? AND state = 'submitting'""",
                (
                    response_json,
                    response_sha256,
                    receipt.remote_task_id,
                    receipt.remote_task_url,
                    updated_at,
                    feedback_id,
                ),
            )
            if updated.rowcount != 1:
                raise ConflictError("development handoff state changed concurrently")
        return self.get_feedback_development_handoff(feedback_id)

    def get_feedback_development_handoff(
        self, feedback_id: str
    ) -> FeedbackDevelopmentHandoffReceipt:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_development_handoffs WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback development handoff not found")
        if row["state"] != "confirmed":
            raise ConflictError("development handoff is not confirmed")
        work_order = self.get_feedback_development_work_order(feedback_id)
        try:
            policy_body = decode(row["policy_json"])
            policy = DevelopmentHandoffPolicy(**policy_body)
            policy.validate()
            payload_body = decode(row["payload_json"])
            response = decode(row["response_json"])
            remote_url = urlsplit(row["remote_task_url"])
        except (TypeError, json.JSONDecodeError, ValueError) as exc:
            raise ConflictError("stored development handoff receipt is unreadable") from exc
        if (
            hashlib.sha256(encode(policy_body).encode()).hexdigest() != row["policy_sha256"]
            or hashlib.sha256(encode(payload_body).encode()).hexdigest() != row["payload_sha256"]
            or payload_body.get("feedback_id") != feedback_id
            or payload_body.get("work_order_sha256") != work_order.record_sha256
            or payload_body.get("attachments") != []
            or hashlib.sha256(encode(response).encode()).hexdigest() != row["response_sha256"]
            or response
            != {
                "remote_task_id": row["remote_task_id"],
                "remote_task_url": row["remote_task_url"],
            }
            or not row["remote_task_id"]
            or remote_url.scheme != "https"
            or not remote_url.hostname
            or remote_url.username is not None
            or remote_url.password is not None
            or remote_url.query
            or remote_url.fragment
        ):
            raise ConflictError("stored development handoff digest mismatch")
        request_body = {
            "feedback_id": feedback_id,
            "policy_sha256": row["policy_sha256"],
            "work_order_sha256": work_order.record_sha256,
            "idempotency_key_sha256": row["idempotency_key_sha256"],
            "confirmation_sha256": row["confirmation_sha256"],
            "payload_sha256": row["payload_sha256"],
        }
        if hashlib.sha256(encode(request_body).encode()).hexdigest() != row["request_sha256"]:
            raise ConflictError("stored development handoff request digest mismatch")
        return FeedbackDevelopmentHandoffReceipt(
            feedback_id=feedback_id,
            provider="development_agent",
            state="confirmed",
            work_order_sha256=work_order.record_sha256,
            remote_task_id=row["remote_task_id"],
            remote_task_url=row["remote_task_url"],
            payload_sha256=row["payload_sha256"],
            response_sha256=row["response_sha256"],
            idempotency_key_sha256=row["idempotency_key_sha256"],
            confirmation_sha256=row["confirmation_sha256"],
            request_sha256=row["request_sha256"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _explicit_development_handoff_reconciliation_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in (
                "我确认核对开发交接结果",
                "我同意保存开发交接对账",
                "确认开发工单对账",
            )
        )

    def reconcile_feedback_development_handoff(
        self,
        feedback_id: str,
        request: FeedbackDevelopmentHandoffReconciliationCreate,
        idempotency_key: str | None,
        policy: DevelopmentHandoffPolicy,
        verifier: DevelopmentHandoffReconciliationVerifier,
    ) -> FeedbackDevelopmentHandoffReconciliationRecord:
        policy.validate()
        if not policy.enabled or not policy.administrator_authorized:
            raise ConflictError("development handoff reconciliation is disabled")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_development_handoff_reconciliation_confirmation(
            request.confirmation_text
        ):
            raise ConflictError("development handoff reconciliation requires explicit confirmation")
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            handoff = connection.execute(
                "SELECT * FROM feedback_development_handoffs WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if handoff is None:
            raise NotFoundError("feedback development handoff not found")
        if request.payload_sha256 != handoff["payload_sha256"]:
            raise ConflictError("development handoff reconciliation payload digest differs")
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        if idempotency_key_sha256 != handoff["idempotency_key_sha256"]:
            raise ConflictError("development handoff reconciliation idempotency key does not match")
        policy_body = {
            "schema_version": policy.schema_version,
            "enabled": policy.enabled,
            "administrator_authorized": policy.administrator_authorized,
            "provider": policy.provider,
            "endpoint": policy.endpoint,
            "max_payload_bytes": policy.max_payload_bytes,
        }
        if hashlib.sha256(encode(policy_body).encode()).hexdigest() != handoff["policy_sha256"]:
            raise ConflictError("development handoff reconciliation policy differs")
        reconciled_by, _ = self._redact_feedback_message(request.reconciled_by)
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "handoff_request_sha256": handoff["request_sha256"],
            "payload_sha256": request.payload_sha256,
            "reconciled_by": reconciled_by,
            "reconciled_at": request.reconciled_at,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                """SELECT * FROM feedback_development_handoff_reconciliations
                   WHERE feedback_id = ?""",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("development handoff already has different reconciliation")
            return self.get_feedback_development_handoff_reconciliation(feedback_id)
        if handoff["state"] not in {"submitting", "ambiguous"}:
            raise ConflictError("only an uncertain development handoff can be reconciled")

        try:
            lookup = verifier.lookup_work_order(
                endpoint=policy.endpoint,
                payload_sha256=request.payload_sha256,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            raise ConflictError(
                "development handoff reconciliation could not determine the outcome"
            ) from exc
        evidence_json = encode(lookup.evidence)
        if not lookup.evidence or len(evidence_json.encode()) > policy.max_payload_bytes:
            raise ConflictError(
                "development handoff reconciliation evidence is missing or too large"
            )
        evidence_sha256 = hashlib.sha256(evidence_json.encode()).hexdigest()
        remote_task_id: str | None = None
        remote_task_url: str | None = None
        response_json: str | None = None
        response_sha256: str | None = None
        if lookup.outcome == "found" and lookup.receipt is not None:
            receipt = lookup.receipt
            parsed = urlsplit(receipt.remote_task_url)
            if (
                not receipt.remote_task_id
                or len(receipt.remote_task_id) > 160
                or parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ConflictError(
                    "development handoff reconciliation returned an invalid receipt"
                )
            response_json = encode(
                {
                    "remote_task_id": receipt.remote_task_id,
                    "remote_task_url": receipt.remote_task_url,
                }
            )
            if len(response_json.encode()) > policy.max_payload_bytes:
                raise ConflictError("development handoff reconciliation response is too large")
            response_sha256 = hashlib.sha256(response_json.encode()).hexdigest()
            remote_task_id = receipt.remote_task_id
            remote_task_url = receipt.remote_task_url
            outcome = "confirmed"
            new_state = "confirmed"
            error = None
        elif lookup.outcome == "absent" and lookup.receipt is None:
            outcome = "verified_absent"
            new_state = "rejected"
            error = "verified_absent"
        else:
            raise ConflictError(
                "development handoff reconciliation result is internally inconsistent"
            )

        now = utc_now()
        record_body = {
            "schema_version": "nalu.feedback-development-handoff-reconciliation/v1",
            "feedback_id": feedback_id,
            "handoff_request_sha256": handoff["request_sha256"],
            "payload_sha256": request.payload_sha256,
            "outcome": outcome,
            "remote_task_id": remote_task_id,
            "remote_task_url": remote_task_url,
            "response_sha256": response_sha256,
            "verification_evidence_sha256": evidence_sha256,
            "read_only_verification_performed": True,
            "work_order_submission_retried": False,
            "external_write_performed": False,
            "reconciled_by": reconciled_by,
            "reconciled_at": request.reconciled_at,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "request_sha256": request_sha256,
            "created_at": now,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        try:
            with self.db.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                updated = connection.execute(
                    """UPDATE feedback_development_handoffs
                       SET state = ?, response_json = ?, response_sha256 = ?,
                           remote_task_id = ?, remote_task_url = ?, error = ?, updated_at = ?
                       WHERE feedback_id = ? AND state IN ('submitting', 'ambiguous')""",
                    (
                        new_state,
                        response_json,
                        response_sha256,
                        remote_task_id,
                        remote_task_url,
                        error,
                        now,
                        feedback_id,
                    ),
                )
                if updated.rowcount != 1:
                    raise ConflictError("development handoff state changed during reconciliation")
                connection.execute(
                    """INSERT INTO feedback_development_handoff_reconciliations
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        feedback_id,
                        request_sha256,
                        encode(record_body),
                        record_sha256,
                        now,
                    ),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError("development handoff was reconciled concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return FeedbackDevelopmentHandoffReconciliationRecord.model_validate(record_body)

    def get_feedback_development_handoff_reconciliation(
        self, feedback_id: str
    ) -> FeedbackDevelopmentHandoffReconciliationRecord:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT * FROM feedback_development_handoff_reconciliations
                   WHERE feedback_id = ?""",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback development handoff reconciliation not found")
        stored = decode(row["record_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored development handoff reconciliation digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return FeedbackDevelopmentHandoffReconciliationRecord.model_validate(stored)

    @staticmethod
    def _explicit_development_result_confirmation(value: str) -> bool:
        normalized = "".join(value.lower().split())
        return any(
            phrase in normalized
            for phrase in (
                "我确认只读核对开发结果",
                "我同意保存开发结果证据",
                "确认开发结果核验",
            )
        )

    def verify_feedback_development_result(
        self,
        feedback_id: str,
        request: FeedbackDevelopmentResultCreate,
        idempotency_key: str | None,
        policy: DevelopmentHandoffPolicy,
        verifier: DevelopmentResultVerifier,
    ) -> FeedbackDevelopmentResultRecord:
        policy.validate()
        if not policy.enabled or not policy.administrator_authorized:
            raise ConflictError("development result verification is disabled")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        if not self._explicit_development_result_confirmation(request.confirmation_text):
            raise ConflictError("development result verification requires confirmation")
        handoff = self.get_feedback_development_handoff(feedback_id)
        if (
            handoff.state != "confirmed"
            or not handoff.remote_task_id
            or not handoff.remote_task_url
            or not handoff.response_sha256
        ):
            raise ConflictError("development result requires a confirmed handoff")
        if request.handoff_request_sha256 != handoff.request_sha256:
            raise ConflictError("development result handoff digest does not match")
        work_order = self.get_feedback_development_work_order(feedback_id)
        verified_by, _ = self._redact_feedback_message(request.verified_by.strip())
        if not verified_by:
            raise ConflictError("development result verifier identity is required")
        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        confirmation_sha256 = hashlib.sha256(request.confirmation_text.strip().encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "handoff_request_sha256": handoff.request_sha256,
            "handoff_response_sha256": handoff.response_sha256,
            "verified_by": verified_by,
            "verified_at": request.verified_at,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM feedback_development_results WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError("feedback already has a different development result")
            return self.get_feedback_development_result(feedback_id)

        try:
            result = verifier.lookup_result(
                endpoint=policy.endpoint,
                remote_task_id=handoff.remote_task_id,
                remote_task_url=handoff.remote_task_url,
            )
        except Exception as exc:
            raise ConflictError("development result could not be independently verified") from exc
        expected_repository_url = f"https://github.com/{work_order.repository}"
        repository_url = urlsplit(result.repository_url)
        review_url = urlsplit(result.review_url)
        if (
            result.repository_url != expected_repository_url
            or repository_url.scheme != "https"
            or repository_url.hostname != "github.com"
            or repository_url.query
            or repository_url.fragment
            or review_url.scheme != "https"
            or review_url.hostname != "github.com"
            or not re.fullmatch(
                rf"/{re.escape(work_order.repository)}/pull/[1-9][0-9]*",
                review_url.path,
            )
            or review_url.query
            or review_url.fragment
            or not re.fullmatch(
                r"(?=.{1,200}$)(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+",
                result.branch_name,
            )
            or ".." in result.branch_name
            or not re.fullmatch(r"[0-9a-f]{40}", result.commit_sha)
            or not re.fullmatch(r"[0-9a-f]{64}", result.test_evidence_sha256)
        ):
            raise ConflictError("development result contains invalid bounded evidence")
        evidence_json = encode(result.evidence)
        if not result.evidence or len(evidence_json.encode()) > policy.max_payload_bytes:
            raise ConflictError("development result verification evidence is missing or too large")
        evidence_sha256 = hashlib.sha256(evidence_json.encode()).hexdigest()
        now = utc_now()
        record_body = {
            "schema_version": "nalu.feedback-development-result/v1",
            "feedback_id": feedback_id,
            "handoff_request_sha256": handoff.request_sha256,
            "handoff_response_sha256": handoff.response_sha256,
            "remote_task_id": handoff.remote_task_id,
            "repository_url": result.repository_url,
            "branch_name": result.branch_name,
            "commit_sha": result.commit_sha,
            "review_url": result.review_url,
            "test_evidence_sha256": result.test_evidence_sha256,
            "verification_evidence_sha256": evidence_sha256,
            "verified_by": verified_by,
            "verified_at": request.verified_at,
            "read_only_verification_performed": True,
            "report_text_treated_as_inert": True,
            "repository_checkout_performed": False,
            "tool_calls": [],
            "code_executed": False,
            "merge_performed": False,
            "signing_performed": False,
            "release_performed": False,
            "external_write_performed": False,
            "idempotency_key_sha256": idempotency_key_sha256,
            "confirmation_sha256": confirmation_sha256,
            "request_sha256": request_sha256,
            "created_at": now,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        try:
            with self.db.connect() as connection:
                connection.execute(
                    "INSERT INTO feedback_development_results VALUES (?, ?, ?, ?, ?)",
                    (
                        feedback_id,
                        request_sha256,
                        encode(record_body),
                        record_sha256,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError("development result was recorded concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return FeedbackDevelopmentResultRecord.model_validate(record_body)

    def get_feedback_development_result(self, feedback_id: str) -> FeedbackDevelopmentResultRecord:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM feedback_development_results WHERE feedback_id = ?",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback development result not found")
        stored = decode(row["record_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored development result digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return FeedbackDevelopmentResultRecord.model_validate(stored)

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
        try:
            development_result = self.get_feedback_development_result(feedback_id)
        except NotFoundError as exc:
            raise ConflictError(
                "release evidence requires an independently verified development result"
            ) from exc
        if (
            request.reviewed_change.repository_url != development_result.repository_url
            or request.reviewed_change.review_url != development_result.review_url
            or request.reviewed_change.commit_sha != development_result.commit_sha
            or request.reviewed_change.test_evidence_sha256
            != development_result.test_evidence_sha256
        ):
            raise ConflictError("reviewed change does not match the verified development result")

        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "idempotency_key_sha256": idempotency_key_sha256,
            "development_result_sha256": development_result.record_sha256,
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
            "development_result_sha256": development_result.record_sha256,
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

    @staticmethod
    def _explicit_release_evidence_reconciliation_confirmation(value: str) -> bool:
        normalized = " ".join(value.strip().lower().split())
        return normalized in {
            "我确认只读核验这份发布证据",
            "i confirm read-only verification of this release evidence",
        }

    def reconcile_feedback_release_evidence(
        self,
        feedback_id: str,
        request: FeedbackReleaseEvidenceReconciliationCreate,
        idempotency_key: str | None,
        verifier: ReleaseEvidenceVerifier,
    ) -> FeedbackReleaseEvidenceReconciliationRecord:
        linkage = self.get_feedback_release_linkage(feedback_id)
        if request.release_linkage_sha256 != linkage.linkage_sha256:
            raise ConflictError("release linkage digest does not match")
        if not self._explicit_release_evidence_reconciliation_confirmation(
            request.confirmation_text
        ):
            raise ConflictError("release evidence reconciliation requires confirmation")
        if idempotency_key is None or not 16 <= len(idempotency_key.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if idempotency_key != idempotency_key.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")

        idempotency_key_sha256 = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_body = {
            "feedback_id": feedback_id,
            "release_linkage_sha256": linkage.linkage_sha256,
            "idempotency_key_sha256": idempotency_key_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            existing = connection.execute(
                """SELECT * FROM feedback_release_evidence_reconciliations
                   WHERE feedback_id = ?""",
                (feedback_id,),
            ).fetchone()
        if existing is not None:
            if existing["request_sha256"] != request_sha256:
                raise ConflictError(
                    "release evidence already has different immutable reconciliation"
                )
            return self.get_feedback_release_evidence_reconciliation(feedback_id)

        try:
            verified = verifier.lookup_release_evidence(
                feedback_id=feedback_id,
                release_linkage_sha256=linkage.linkage_sha256,
                ci_run_url=linkage.ci.run_url,
                artifact_sha256=linkage.ci.artifact_sha256,
                installed_version=linkage.installed_release.version,
                installed_build=linkage.installed_release.build,
            )
        except (ReleaseEvidenceVerificationError, TypeError, ValueError) as exc:
            raise ConflictError("release evidence could not be independently verified") from exc

        expected = (
            linkage.ci.run_url,
            linkage.ci.head_sha,
            linkage.ci.conclusion,
            linkage.ci.artifact_sha256,
            linkage.ci.completed_at,
            linkage.installed_release.version,
            linkage.installed_release.build,
            linkage.installed_release.product_commit,
            linkage.installed_release.provenance_sha256,
            linkage.installed_release.developer_id_team_id,
            linkage.installed_release.notarization_submission_id,
            linkage.installed_release.code_signature_verified,
            linkage.installed_release.notarization_verified,
            linkage.installed_release.gatekeeper_accepted,
            linkage.installed_release.installed_at,
            linkage.rollback.previous_version,
            linkage.rollback.previous_build,
            linkage.rollback.evidence_sha256,
            linkage.rollback.project_data_preserved,
            linkage.rollback.verified_at,
        )
        actual = (
            verified.ci_run_url,
            verified.ci_head_sha,
            verified.ci_conclusion,
            verified.artifact_sha256,
            verified.ci_completed_at,
            verified.version,
            verified.build,
            verified.product_commit,
            verified.provenance_sha256,
            verified.developer_id_team_id,
            verified.notarization_submission_id,
            verified.code_signature_verified,
            verified.notarization_verified,
            verified.gatekeeper_accepted,
            verified.installed_at,
            verified.previous_version,
            verified.previous_build,
            verified.rollback_evidence_sha256,
            verified.project_data_preserved,
            verified.rollback_verified_at,
        )
        if actual != expected:
            raise ConflictError("independent release evidence does not match the linkage")
        if not isinstance(verified.evidence, dict) or not verified.evidence:
            raise ConflictError("independent release verification evidence is missing")
        evidence_json = encode(verified.evidence)
        if len(evidence_json.encode()) > 65536:
            raise ConflictError("independent release verification evidence is too large")

        now = utc_now()
        record_body = {
            "schema_version": "nalu.feedback-release-evidence-reconciliation/v1",
            "feedback_id": feedback_id,
            "release_linkage_sha256": linkage.linkage_sha256,
            "status": "independently_verified",
            "verification_evidence_sha256": hashlib.sha256(evidence_json.encode()).hexdigest(),
            "read_only_verification_performed": True,
            "download_performed": False,
            "installation_performed": False,
            "signing_performed": False,
            "notarization_performed": False,
            "release_performed": False,
            "external_write_performed": False,
            "release_claimed": False,
            "created_at": now,
            "idempotency_key_sha256": idempotency_key_sha256,
            "request_sha256": request_sha256,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        with self.db.connect() as connection:
            try:
                connection.execute(
                    """INSERT INTO feedback_release_evidence_reconciliations
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        feedback_id,
                        request_sha256,
                        encode(record_body),
                        record_sha256,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("release evidence was reconciled concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return FeedbackReleaseEvidenceReconciliationRecord.model_validate(record_body)

    def get_feedback_release_evidence_reconciliation(
        self, feedback_id: str
    ) -> FeedbackReleaseEvidenceReconciliationRecord:
        self.get_feedback(feedback_id)
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT * FROM feedback_release_evidence_reconciliations
                   WHERE feedback_id = ?""",
                (feedback_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError("feedback release evidence reconciliation not found")
        stored = decode(row["record_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored release evidence reconciliation digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return FeedbackReleaseEvidenceReconciliationRecord.model_validate(stored)

    def feedback_governed_release_readiness(
        self, feedback_id: str
    ) -> FeedbackGovernedReleaseReadiness:
        feedback = self.get_feedback(feedback_id)
        table_checks = (
            ("review_bundle", "feedback_review_bundles", "本地脱敏审核包已冻结", None),
            ("human_triage", "feedback_triage_records", "人工分诊已接受", "accepted"),
            ("issue_export", "feedback_external_exports", "外部问题单事务已确认", "confirmed"),
            ("development_work_order", "feedback_development_work_orders", "开发工单已批准", None),
            (
                "development_handoff",
                "feedback_development_handoffs",
                "开发交接事务已确认",
                "confirmed",
            ),
            ("development_result", "feedback_development_results", "开发结果已只读核验", None),
            (
                "release_linkage",
                "feedback_release_linkages",
                "变更、CI、安装与回滚证据已绑定",
                None,
            ),
            (
                "independent_release_reconciliation",
                "feedback_release_evidence_reconciliations",
                "发布证据已独立只读核验",
                None,
            ),
        )
        checks: list[FeedbackReleaseReadinessCheck] = []
        present: dict[str, bool] = {}
        with self.db.connect() as connection:
            for check_id, table, explanation, required_state in table_checks:
                row = connection.execute(
                    f"SELECT * FROM {table} WHERE feedback_id = ?",
                    (feedback_id,),
                ).fetchone()
                satisfied = row is not None
                if satisfied and required_state is not None:
                    if table == "feedback_triage_records":
                        satisfied = decode(row["record_json"]).get("disposition") == required_state
                    else:
                        satisfied = row["state"] == required_state
                present[check_id] = satisfied
                checks.append(
                    FeedbackReleaseReadinessCheck(
                        id=check_id,
                        status="satisfied" if satisfied else "missing",
                        explanation=(explanation if satisfied else f"仍缺少：{explanation}"),
                    )
                )
        independently_verified = present["independent_release_reconciliation"]
        for check_id, explanation, satisfied in (
            (
                "signed_notarized_installation",
                "Developer ID、Apple 公证、Gatekeeper 与安装提交已独立匹配",
                independently_verified,
            ),
            (
                "rollback_rehearsal",
                "旧版本回滚演练与项目数据保全已独立匹配",
                independently_verified,
            ),
            ("staged_rollout_authorization", "管理员尚未授权分阶段发布", False),
            ("staged_rollout_receipt", "尚无真实分阶段发布事务回执", False),
            ("post_install_health", "尚无真实安装后的健康确认", False),
        ):
            checks.append(
                FeedbackReleaseReadinessCheck(
                    id=check_id,
                    status="satisfied" if satisfied else "missing",
                    explanation=explanation,
                )
            )
        pre_rollout_ids = {item[0] for item in table_checks} | {
            "signed_notarized_installation",
            "rollback_rehearsal",
        }
        ready = all(check.status == "satisfied" for check in checks if check.id in pre_rollout_ids)
        return FeedbackGovernedReleaseReadiness(
            feedback_id=feedback_id,
            feedback_status=feedback.status,
            checks=checks,
            ready_for_authorized_rollout=ready,
        )

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
            "春天": "spring",
            "春季": "spring",
            "春": "spring",
            "夏天": "summer",
            "夏季": "summer",
            "夏": "summer",
            "秋天": "autumn",
            "秋季": "autumn",
            "秋": "autumn",
            "冬天": "winter",
            "冬季": "winter",
            "冬": "winter",
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
            if self._memory_fact_text(person.name)
            and self._canonical_relationship(person.relationship)
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
        if SCRIPT_AUTHORING_PROVENANCE_KEY in request.narrative_metadata:
            raise ConflictError("script authoring provenance is managed by Nalu")
        provenance = _seal_script_authoring_provenance(request)
        stored_metadata = {
            **request.narrative_metadata,
            SCRIPT_AUTHORING_PROVENANCE_KEY: provenance.model_dump(mode="json"),
        }
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
                    encode(stored_metadata),
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
        try:
            metadata = decode(data.pop("narrative_metadata_json"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise ConflictError("script metadata is unreadable") from exc
        if not isinstance(metadata, dict):
            raise ConflictError("script metadata is invalid")
        data["authoring_provenance"] = _verify_script_authoring_provenance(
            content=data.get("content"),
            source_transcript=data.get("source_transcript"),
            raw_provenance=metadata.pop(SCRIPT_AUTHORING_PROVENANCE_KEY, None),
        )
        data["narrative_metadata"] = metadata
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
    def _continuity_proposal_summary(state: ContinuityState, unresolved_hooks: list[str]) -> str:
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

    def continuity_extraction_proposal(self, episode_id: str) -> ContinuityExtractionProposal:
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
            hooks = [item.strip() for item in re.split(r"[、,，;；]", hooks_text) if item.strip()]
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
                raise ConflictError("this approved script already has a confirmed ending handoff")
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
    def _stable_idempotency_key(value: str | None) -> tuple[str, str]:
        if value is None or not 16 <= len(value.strip()) <= 200:
            raise ConflictError("a stable 16-200 character idempotency key is required")
        if value != value.strip():
            raise ConflictError("idempotency key must not have surrounding whitespace")
        return value, hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _publication_confirmation(value: str) -> bool:
        return " ".join(value.strip().lower().split()) in {
            "我确认只读核验这次发行",
            "i confirm read-only verification of this publication",
        }

    @staticmethod
    def _metrics_confirmation(value: str) -> bool:
        return " ".join(value.strip().lower().split()) in {
            "我确认只读同步这次发行指标",
            "i confirm read-only sync of these publication metrics",
        }

    def get_publication_reconciliation(
        self, run_id: str, platform: str
    ) -> PublicationReconciliationRecord:
        self.get_run(run_id)
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT * FROM publication_reconciliations
                   WHERE run_id = ? AND platform = ?""",
                (run_id, platform),
            ).fetchone()
        if row is None:
            raise NotFoundError("publication reconciliation not found")
        stored = decode(row["record_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["record_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored publication reconciliation digest mismatch")
        stored["record_sha256"] = row["record_sha256"]
        return PublicationReconciliationRecord.model_validate(stored)

    def reconcile_publication(
        self,
        run_id: str,
        request: PublicationReconciliationCreate,
        idempotency_key: str | None,
        verifier: PublicationLearningVerifier,
        *,
        local_release_manifest_sha256: str,
        publication_dry_run_sha256: str,
        channel_reference: str,
    ) -> PublicationReconciliationRecord:
        run = self.get_run(run_id)
        episode = self.get_episode(run.episode_id)
        project = self.get_project(run.project_id)
        if run.status != RunStatus.COMPLETED or episode.status not in {
            EpisodeStatus.READY_TO_PUBLISH,
            EpisodeStatus.PUBLISHED,
        }:
            raise ConflictError("only a completed ready-to-publish episode can be reconciled")
        if request.release_manifest_sha256 != local_release_manifest_sha256:
            raise ConflictError("publication reconciliation references another release package")
        if project.audience_mode == "child" and not request.guardian_approval:
            raise ConflictError("child publication reconciliation requires guardian approval")
        if not self._publication_confirmation(request.confirmation_text):
            raise ConflictError("publication reconciliation requires read-only confirmation")
        _, key_sha256 = self._stable_idempotency_key(idempotency_key)
        request_body = {
            "run_id": run_id,
            "platform": request.platform,
            "remote_publication_id": request.remote_publication_id,
            "release_manifest_sha256": local_release_manifest_sha256,
            "publication_dry_run_sha256": publication_dry_run_sha256,
            "channel_reference": channel_reference,
            "guardian_approval": request.guardian_approval,
            "idempotency_key_sha256": key_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            prior_key = connection.execute(
                """SELECT run_id, platform, request_sha256
                   FROM publication_reconciliations WHERE idempotency_key_sha256 = ?""",
                (key_sha256,),
            ).fetchone()
        if prior_key is not None:
            if prior_key["request_sha256"] != request_sha256:
                raise ConflictError("publication idempotency key was already used differently")
            return self.get_publication_reconciliation(prior_key["run_id"], prior_key["platform"])
        try:
            existing = self.get_publication_reconciliation(run_id, request.platform)
        except NotFoundError:
            existing = None
        if existing is not None:
            if existing.request_sha256 != request_sha256:
                raise ConflictError("publication already has a different immutable identity")
            return existing
        try:
            verified = verifier.lookup_publication(
                platform=request.platform,
                remote_publication_id=request.remote_publication_id,
                channel_reference=channel_reference,
                release_manifest_sha256=local_release_manifest_sha256,
            )
        except (PublicationVerificationError, TypeError, ValueError) as exc:
            raise ConflictError("publication identity could not be independently verified") from exc
        expected = (
            request.platform,
            request.remote_publication_id,
            "published",
            local_release_manifest_sha256,
            channel_reference,
        )
        actual = (
            verified.platform,
            verified.remote_publication_id,
            verified.remote_state,
            verified.release_manifest_sha256,
            verified.channel_reference,
        )
        if actual != expected or not verified.published_at.strip():
            raise ConflictError("verified publication identity does not match the local package")
        if not isinstance(verified.evidence, dict) or not verified.evidence:
            raise ConflictError("publication verification evidence is missing")
        evidence_json = encode(verified.evidence)
        if len(evidence_json.encode()) > 65536:
            raise ConflictError("publication verification evidence is too large")
        now = utc_now()
        record_body = {
            "schema_version": "nalu.publication-reconciliation/v1",
            "run_id": run.id,
            "project_id": run.project_id,
            "episode_id": run.episode_id,
            "platform": request.platform,
            "remote_publication_id": request.remote_publication_id,
            "remote_state": "published",
            "release_manifest_sha256": local_release_manifest_sha256,
            "publication_dry_run_sha256": publication_dry_run_sha256,
            "channel_reference": channel_reference,
            "published_at": verified.published_at,
            "verification_evidence_sha256": hashlib.sha256(evidence_json.encode()).hexdigest(),
            "read_only_verification_performed": True,
            "publication_performed": False,
            "replacement_performed": False,
            "external_write_performed": False,
            "idempotency_key_sha256": key_sha256,
            "request_sha256": request_sha256,
            "created_at": now,
        }
        record_sha256 = hashlib.sha256(encode(record_body).encode()).hexdigest()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO publication_reconciliations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run.id,
                        request.platform,
                        request.remote_publication_id,
                        request_sha256,
                        key_sha256,
                        encode(record_body),
                        record_sha256,
                        now,
                    ),
                )
                if episode.status == EpisodeStatus.READY_TO_PUBLISH:
                    connection.execute(
                        "UPDATE episodes SET status = ?, updated_at = ? WHERE id = ?",
                        (EpisodeStatus.PUBLISHED, now, episode.id),
                    )
                    sequence = connection.execute(
                        """SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
                           FROM episode_events WHERE episode_id = ?""",
                        (episode.id,),
                    ).fetchone()["sequence"]
                    connection.execute(
                        "INSERT INTO episode_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            new_id("ep_evt"),
                            episode.id,
                            sequence,
                            "publication_reconciled",
                            EpisodeStatus.READY_TO_PUBLISH,
                            EpisodeStatus.PUBLISHED,
                            "authorized verifier",
                            "远端发行身份已只读核验。",
                            now,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("publication identity was reconciled concurrently") from exc
        record_body["record_sha256"] = record_sha256
        return PublicationReconciliationRecord.model_validate(record_body)

    def get_publication_metrics_snapshot(self, metrics_id: str) -> PublicationMetricsSnapshot:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM publication_metric_snapshots WHERE id = ?", (metrics_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("publication metrics snapshot not found")
        stored = decode(row["snapshot_json"])
        if (
            hashlib.sha256(encode(stored).encode()).hexdigest() != row["snapshot_sha256"]
            or stored.get("request_sha256") != row["request_sha256"]
        ):
            raise ConflictError("stored publication metrics digest mismatch")
        stored["snapshot_sha256"] = row["snapshot_sha256"]
        return PublicationMetricsSnapshot.model_validate(stored)

    def get_director_strategy(self, strategy_id: str) -> DirectorStrategyRevision:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM director_strategy_revisions WHERE id = ?", (strategy_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("director strategy revision not found")
        stored = decode(row["strategy_json"])
        if hashlib.sha256(encode(stored).encode()).hexdigest() != row["strategy_sha256"]:
            raise ConflictError("stored director strategy digest mismatch")
        stored["strategy_sha256"] = row["strategy_sha256"]
        return DirectorStrategyRevision.model_validate(stored)

    def sync_publication_metrics(
        self,
        run_id: str,
        request: PublicationMetricsSyncCreate,
        idempotency_key: str | None,
        verifier: PublicationLearningVerifier,
    ) -> PublicationMetricsLearningResult:
        run = self.get_run(run_id)
        publication = None
        for platform in ("youtube", "bilibili"):
            try:
                candidate = self.get_publication_reconciliation(run_id, platform)
            except NotFoundError:
                continue
            if candidate.record_sha256 == request.publication_record_sha256:
                publication = candidate
                break
        if publication is None:
            raise ConflictError("publication reconciliation digest does not match")
        if not self._metrics_confirmation(request.confirmation_text):
            raise ConflictError("publication metrics sync requires read-only confirmation")
        try:
            window_start = datetime.fromisoformat(request.window_start)
            window_end = datetime.fromisoformat(request.window_end)
        except ValueError as exc:
            raise ConflictError("publication metrics window must use ISO-8601 timestamps") from exc
        if window_start.utcoffset() is None or window_end.utcoffset() is None:
            raise ConflictError("publication metrics window must include a UTC offset")
        if window_start >= window_end:
            raise ConflictError("publication metrics window must end after it starts")
        _, key_sha256 = self._stable_idempotency_key(idempotency_key)
        request_body = {
            "run_id": run_id,
            "publication_record_sha256": publication.record_sha256,
            "window_start": request.window_start,
            "window_end": request.window_end,
            "idempotency_key_sha256": key_sha256,
        }
        request_sha256 = hashlib.sha256(encode(request_body).encode()).hexdigest()
        with self.db.connect() as connection:
            prior_key = connection.execute(
                """SELECT id, request_sha256 FROM publication_metric_snapshots
                   WHERE idempotency_key_sha256 = ?""",
                (key_sha256,),
            ).fetchone()
            if prior_key is not None:
                if prior_key["request_sha256"] != request_sha256:
                    raise ConflictError("metrics idempotency key was already used differently")
                metrics = self.get_publication_metrics_snapshot(prior_key["id"])
                strategy_row = connection.execute(
                    "SELECT id FROM director_strategy_revisions WHERE source_metrics_id = ?",
                    (metrics.id,),
                ).fetchone()
                return PublicationMetricsLearningResult(
                    metrics=metrics,
                    strategy=self.get_director_strategy(strategy_row["id"]),
                )
            existing = connection.execute(
                """SELECT id, request_sha256 FROM publication_metric_snapshots
                   WHERE run_id = ? AND platform = ? AND window_start = ? AND window_end = ?""",
                (run_id, publication.platform, request.window_start, request.window_end),
            ).fetchone()
            if existing is not None:
                if existing["request_sha256"] != request_sha256:
                    raise ConflictError("metrics window already has a different immutable request")
                metrics = self.get_publication_metrics_snapshot(existing["id"])
                strategy_row = connection.execute(
                    "SELECT id FROM director_strategy_revisions WHERE source_metrics_id = ?",
                    (metrics.id,),
                ).fetchone()
                return PublicationMetricsLearningResult(
                    metrics=metrics,
                    strategy=self.get_director_strategy(strategy_row["id"]),
                )
        try:
            verified = verifier.lookup_metrics(
                platform=publication.platform,
                remote_publication_id=publication.remote_publication_id,
                window_start=request.window_start,
                window_end=request.window_end,
            )
        except (PublicationVerificationError, TypeError, ValueError) as exc:
            raise ConflictError("publication metrics could not be independently verified") from exc
        if (
            verified.platform != publication.platform
            or verified.remote_publication_id != publication.remote_publication_id
            or verified.window_start != request.window_start
            or verified.window_end != request.window_end
        ):
            raise ConflictError("verified metrics do not match the reconciled publication")
        integer_values = (
            verified.views,
            verified.unique_viewers,
            verified.watch_time_seconds,
            verified.likes,
            verified.comments,
            verified.shares,
            verified.followers_gained,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in integer_values):
            raise ConflictError("verified publication metrics contain invalid values")
        numeric_values = (*integer_values, verified.average_view_duration_seconds)
        try:
            invalid_numeric = any(
                not math.isfinite(float(value)) or float(value) < 0 for value in numeric_values
            )
            invalid_completion = not math.isfinite(float(verified.completion_rate)) or not (
                0 <= float(verified.completion_rate) <= 1
            )
        except (TypeError, ValueError):
            invalid_numeric = invalid_completion = True
        if invalid_numeric or invalid_completion:
            raise ConflictError("verified publication metrics contain invalid values")
        if not isinstance(verified.evidence, dict) or not verified.evidence:
            raise ConflictError("publication metrics verification evidence is missing")
        evidence_json = encode(verified.evidence)
        if len(evidence_json.encode()) > 65536:
            raise ConflictError("publication metrics evidence is too large")
        with self.db.connect() as connection:
            current_episode = connection.execute(
                """SELECT e.episode_number, s.season_number
                   FROM episodes e JOIN seasons s ON s.id = e.season_id
                   WHERE e.id = ?""",
                (run.episode_id,),
            ).fetchone()
            target = connection.execute(
                """SELECT e.id, e.status FROM episodes e
                   JOIN seasons s ON s.id = e.season_id
                   WHERE s.project_id = ? AND (
                     s.season_number > ? OR
                     (s.season_number = ? AND e.episode_number > ?)
                   )
                   ORDER BY s.season_number, e.episode_number LIMIT 1""",
                (
                    run.project_id,
                    current_episode["season_number"],
                    current_episode["season_number"],
                    current_episode["episode_number"],
                ),
            ).fetchone()
        if target is None:
            raise ConflictError("metrics learning requires a later episode in the project")
        if EpisodeStatus(target["status"]) not in EDITABLE_EPISODE_PLAN_STATUSES:
            raise ConflictError("next-episode strategy cannot target a locked or produced episode")
        metrics_id, now = new_id("metrics"), utc_now()
        metrics_body = {
            "schema_version": "nalu.publication-metrics/v1",
            "id": metrics_id,
            "run_id": run.id,
            "project_id": run.project_id,
            "episode_id": run.episode_id,
            "platform": publication.platform,
            "remote_publication_id": publication.remote_publication_id,
            "publication_record_sha256": publication.record_sha256,
            "window_start": request.window_start,
            "window_end": request.window_end,
            "views": verified.views,
            "unique_viewers": verified.unique_viewers,
            "watch_time_seconds": verified.watch_time_seconds,
            "average_view_duration_seconds": verified.average_view_duration_seconds,
            "completion_rate": verified.completion_rate,
            "likes": verified.likes,
            "comments": verified.comments,
            "shares": verified.shares,
            "followers_gained": verified.followers_gained,
            "verification_evidence_sha256": hashlib.sha256(evidence_json.encode()).hexdigest(),
            "read_only_sync_performed": True,
            "publication_performed": False,
            "production_performed": False,
            "external_write_performed": False,
            "idempotency_key_sha256": key_sha256,
            "request_sha256": request_sha256,
            "created_at": now,
        }
        metrics_sha256 = hashlib.sha256(encode(metrics_body).encode()).hexdigest()
        observations, directives = self._director_strategy_content(verified)
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            revision = int(
                connection.execute(
                    """SELECT COALESCE(MAX(revision), 0) + 1 AS revision
                   FROM director_strategy_revisions WHERE project_id = ?""",
                    (run.project_id,),
                ).fetchone()["revision"]
            )
            strategy_id = new_id("strategy")
            strategy_body = {
                "schema_version": "nalu.director-strategy/v1",
                "id": strategy_id,
                "project_id": run.project_id,
                "target_episode_id": target["id"],
                "source_metrics_id": metrics_id,
                "source_metrics_sha256": metrics_sha256,
                "revision": revision,
                "observations": observations,
                "directives": directives,
                "immutable_constraints": [
                    "不得改写已确认的角色、场景、道具、声音和连续性事实",
                    "任何建议必须形成新的剧本修订并再次由用户确认",
                    "这份策略不能启动生产、付费调用或发行",
                ],
                "requires_script_revision_and_approval": True,
                "production_started": False,
                "publication_performed": False,
                "created_at": now,
            }
            strategy_sha256 = hashlib.sha256(encode(strategy_body).encode()).hexdigest()
            try:
                connection.execute(
                    "INSERT INTO publication_metric_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        metrics_id,
                        run.id,
                        publication.platform,
                        publication.remote_publication_id,
                        request.window_start,
                        request.window_end,
                        request_sha256,
                        key_sha256,
                        encode(metrics_body),
                        metrics_sha256,
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO director_strategy_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        strategy_id,
                        run.project_id,
                        target["id"],
                        metrics_id,
                        revision,
                        encode(strategy_body),
                        strategy_sha256,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("publication metrics were synchronized concurrently") from exc
        metrics_body["snapshot_sha256"] = metrics_sha256
        strategy_body["strategy_sha256"] = strategy_sha256
        return PublicationMetricsLearningResult(
            metrics=PublicationMetricsSnapshot.model_validate(metrics_body),
            strategy=DirectorStrategyRevision.model_validate(strategy_body),
        )

    def list_director_strategies(self, project_id: str) -> list[DirectorStrategyRevision]:
        self.get_project(project_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT id FROM director_strategy_revisions
                   WHERE project_id = ? ORDER BY revision""",
                (project_id,),
            ).fetchall()
        return [self.get_director_strategy(row["id"]) for row in rows]

    @staticmethod
    def _director_strategy_content(verified: Any) -> tuple[list[str], list[str]]:
        observations = [f"本次核验窗口完播率为 {verified.completion_rate:.1%}。"]
        directives: list[str] = []
        if verified.completion_rate < 0.6:
            observations.append("完播率低于 60%，开场和中段节奏需要优先复核。")
            directives.append("下一集前 15 秒更快交代人物目标与核心冲突。")
            directives.append("缩短不推动故事的解释段，并保留老人和儿童容易理解的表达。")
        share_rate = verified.shares / verified.views if verified.views else 0
        comment_rate = verified.comments / verified.views if verified.views else 0
        if share_rate >= 0.03:
            observations.append("分享率达到 3%，当前情感主题具有传播信号。")
            directives.append("延续本集最受分享的情感主题，但不得复制既有镜头。")
        if comment_rate >= 0.02:
            observations.append("评论率达到 2%，观众有明确讨论意愿。")
            directives.append("从已确认的故事素材中增加一个可讨论但不误导的选择时刻。")
        if not directives:
            directives.append("保持当前结构，只对下一集开场钩子做一个可回退的小修订。")
        return observations, directives

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
        if target_state == RemoteTaskState.ZERO_CHARGE_FAILED and actual_charged_credits != 0:
            raise ConflictError("zero-charge failures require an exact zero-credit receipt")
        if target_state == RemoteTaskState.AMBIGUOUS_CHARGE and actual_charged_credits is not None:
            raise ConflictError("ambiguous-charge tasks cannot claim a reconciled credit total")
        if (
            target_state
            in {
                RemoteTaskState.AMBIGUOUS_CHARGE,
                RemoteTaskState.ZERO_CHARGE_FAILED,
            }
            and not charge_classification.strip()
        ):
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
