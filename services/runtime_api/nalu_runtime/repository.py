from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

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
    ContinuitySnapshot,
    ContinuitySnapshotCreate,
    Episode,
    EpisodeCreate,
    EpisodeEvent,
    EpisodePlanUpdate,
    EpisodeStatus,
    EpisodeTransitionRequest,
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

    def create_project(self, request: ProjectCreate) -> Project:
        project_id, now = new_id("prj"), utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO projects (
                   id, title, description, audience_mode, visual_style, aspect_ratio,
                   planned_episode_count, target_episode_seconds, project_bible_json,
                   created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        """Create a project, its first season and episode slots atomically."""
        canonical_request = request.model_dump_json(exclude_none=True)
        request_sha = hashlib.sha256(canonical_request.encode()).hexdigest()
        project_id, season_id, now = new_id("prj"), new_id("sea"), utc_now()
        episode_count = request.project.planned_episode_count
        titles = request.episode_titles or [f"第{number}集" for number in range(1, episode_count + 1)]
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
            connection.execute(
                """INSERT INTO projects (
                   id, title, description, audience_mode, visual_style, aspect_ratio,
                   planned_episode_count, target_episode_seconds, project_bible_json,
                   created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    created_at=now,
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
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
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

    def archive_project(
        self, project_id: str, request: ProjectArchiveRequest
    ) -> Project:
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
                "id", "title", "description", "audience_mode", "visual_style",
                "aspect_ratio", "planned_episode_count", "target_episode_seconds",
                "project_bible_json", "created_at", "updated_at", "archived_at",
            ),
            "seasons": (
                "id", "project_id", "title", "season_number", "planned_episode_count",
                "season_arc_json", "created_at", "updated_at",
            ),
            "episodes": (
                "id", "season_id", "title", "episode_number", "logline", "outline_json",
                "target_seconds", "status", "approved_script_revision", "created_at", "updated_at",
            ),
            "season_plan_revisions": (
                "season_id", "revision", "plan_json", "source_transcript", "created_at",
            ),
            "season_plan_approval_records": (
                "id", "season_id", "plan_revision", "approved_by",
                "spoken_confirmation", "review_channel", "guardian_approval", "created_at",
            ),
            "script_revisions": (
                "episode_id", "revision", "content", "summary_for_voice_review",
                "source_transcript", "narrative_metadata_json", "approved_at", "created_at",
            ),
            "assets": (
                "id", "project_id", "episode_id", "kind", "name", "local_uri",
                "subject_name", "metadata_json", "consent_granted", "consent_scope",
                "guardian_approved", "created_at",
            ),
            "asset_consent_records": (
                "id", "asset_id", "action_type", "consent_scope", "recorded_by",
                "statement", "guardian_approved", "created_at",
            ),
            "continuity_snapshots": (
                "id", "episode_id", "source_episode_id", "state_json",
                "unresolved_hooks_json", "created_at",
            ),
            "approval_records": (
                "id", "action_type", "project_id", "episode_id", "script_revision",
                "approved_by", "spoken_confirmation", "guardian_approval", "created_at",
            ),
        }
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
            row.get("episode_id") not in episode_ids
            for row in backup.payload["script_revisions"]
        ):
            raise ConflictError("project export contains a script from another project")
        if any(
            row.get("project_id") != project_id
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
            connection.execute(
                "DELETE FROM production_runs WHERE project_id = ?", (project_id,)
            )
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
        season = connection.execute(
            "SELECT * FROM seasons WHERE id = ?", (season_id,)
        ).fetchone()
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
                    "SELECT id FROM seasons WHERE project_id = ? ORDER BY season_number", (project_id,)
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
            connection.execute(
                f"UPDATE episodes SET {', '.join(updates)} WHERE id = ?", values
            )
            self._snapshot_season_plan(
                connection, current["season_id"], request.source_transcript
            )
        return self.get_episode(episode_id)

    def get_episode(self, episode_id: str) -> Episode:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
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
                    "SELECT id FROM episodes WHERE season_id = ? ORDER BY episode_number", (season_id,)
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

    def transition_episode(
        self, episode_id: str, request: EpisodeTransitionRequest
    ) -> Episode:
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
        if EpisodeStatus.SCRIPT_REVIEW not in EPISODE_TRANSITIONS[episode.status] and episode.status != EpisodeStatus.SCRIPT_REVIEW:
            raise ConflictError(f"cannot create a script revision while episode is {episode.status}")
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
        if request.episode_id:
            episode = self.get_episode(request.episode_id)
            season = self.get_season(episode.season_id)
            if season.project_id != project_id:
                raise ConflictError("asset episode belongs to another project")
        asset_id, now = asset_id or new_id("ast"), utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset_id,
                    project_id,
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

    def list_assets(self, project_id: str, episode_id: str | None = None) -> list[Asset]:
        self.get_project(project_id)
        sql = "SELECT id FROM assets WHERE project_id = ?"
        params: tuple[Any, ...] = (project_id,)
        if episode_id:
            sql += " AND (episode_id IS NULL OR episode_id = ?)"
            params += (episode_id,)
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
            connection.execute(
                "UPDATE assets SET consent_granted = 0 WHERE id = ?", (asset_id,)
            )
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

    def create_continuity_snapshot(
        self, episode_id: str, request: ContinuitySnapshotCreate
    ) -> ContinuitySnapshot:
        self.get_episode(episode_id)
        snapshot_id, now = new_id("con"), utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO continuity_snapshots VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    episode_id,
                    request.source_episode_id,
                    encode(request.state),
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

    def get_run(self, run_id: str) -> ProductionRun:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM production_runs WHERE id = ?", (run_id,)).fetchone()
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

    def get_run_event(self, event_id: str) -> RunEvent:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM run_events WHERE id = ?", (event_id,)).fetchone()
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
