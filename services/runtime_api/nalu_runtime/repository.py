from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .database import Database
from .models import (
    ApprovalCreate,
    ApprovalRecord,
    Asset,
    AssetCreate,
    ContinuitySnapshot,
    ContinuitySnapshotCreate,
    Episode,
    EpisodeCreate,
    EpisodeStatus,
    ProductionRun,
    Project,
    ProjectCreate,
    RunEvent,
    RunStatus,
    ScriptRevision,
    ScriptRevisionCreate,
    Season,
    SeasonCreate,
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


class Repository:
    def __init__(self, database: Database):
        self.db = database

    def create_project(self, request: ProjectCreate) -> Project:
        project_id, now = new_id("prj"), utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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

    def get_project(self, project_id: str) -> Project:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError("project not found")
        data = dict(row)
        data["project_bible"] = decode(data.pop("project_bible_json"))
        return Project.model_validate(data)

    def list_projects(self) -> list[Project]:
        with self.db.connect() as connection:
            ids = [row["id"] for row in connection.execute("SELECT id FROM projects ORDER BY created_at")]
        return [self.get_project(project_id) for project_id in ids]

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
        except Exception as exc:
            raise ConflictError("season number already exists") from exc
        return self.get_season(season_id)

    def get_season(self, season_id: str) -> Season:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM seasons WHERE id = ?", (season_id,)).fetchone()
        if row is None:
            raise NotFoundError("season not found")
        data = dict(row)
        data["season_arc"] = decode(data.pop("season_arc_json"))
        return Season.model_validate(data)

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
        except Exception as exc:
            raise ConflictError("episode number already exists") from exc
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

    def create_script(self, episode_id: str, request: ScriptRevisionCreate) -> ScriptRevision:
        episode = self.get_episode(episode_id)
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

    def approve_script(
        self, episode_id: str, revision: int, approval: ApprovalCreate
    ) -> ScriptRevision:
        self.get_script(episode_id, revision)
        episode = self.get_episode(episode_id)
        season = self.get_season(episode.season_id)
        now = utc_now()
        approval_id = new_id("apr")
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE script_revisions SET approved_at = NULL WHERE episode_id = ?", (episode_id,)
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

    def create_asset(self, project_id: str, request: AssetCreate) -> Asset:
        self.get_project(project_id)
        if request.episode_id:
            self.get_episode(request.episode_id)
        asset_id, now = new_id("ast"), utc_now()
        with self.db.connect() as connection:
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
