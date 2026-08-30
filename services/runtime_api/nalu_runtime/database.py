from __future__ import annotations

import sqlite3
from pathlib import Path

from .secure_files import secure_directory, secure_file

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  audience_mode TEXT NOT NULL,
  visual_style TEXT NOT NULL,
  aspect_ratio TEXT NOT NULL,
  planned_episode_count INTEGER NOT NULL,
  target_episode_seconds INTEGER NOT NULL,
  project_bible_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seasons (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  season_number INTEGER NOT NULL,
  planned_episode_count INTEGER NOT NULL,
  season_arc_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(project_id, season_number)
);

CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY,
  season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  episode_number INTEGER NOT NULL,
  logline TEXT NOT NULL,
  outline_json TEXT NOT NULL,
  target_seconds INTEGER NOT NULL,
  status TEXT NOT NULL,
  approved_script_revision INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(season_id, episode_number)
);

CREATE TABLE IF NOT EXISTS script_revisions (
  episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  content TEXT NOT NULL,
  summary_for_voice_review TEXT NOT NULL,
  source_transcript TEXT NOT NULL,
  narrative_metadata_json TEXT NOT NULL,
  approved_at TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY(episode_id, revision)
);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  episode_id TEXT REFERENCES episodes(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  local_uri TEXT NOT NULL,
  subject_name TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  consent_granted INTEGER NOT NULL,
  consent_scope TEXT NOT NULL,
  guardian_approved INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS continuity_snapshots (
  id TEXT PRIMARY KEY,
  episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
  source_episode_id TEXT REFERENCES episodes(id),
  state_json TEXT NOT NULL,
  unresolved_hooks_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS production_runs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  season_id TEXT NOT NULL REFERENCES seasons(id),
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  status TEXT NOT NULL,
  dry_run INTEGER NOT NULL,
  requested_model TEXT NOT NULL,
  estimated_budget_credits INTEGER,
  package_path TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES production_runs(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  message TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  applied_at TEXT NOT NULL
);
"""

MIGRATIONS = (
    (
        1,
        "approval_audit_records",
        """
        CREATE TABLE approval_records (
          id TEXT PRIMARY KEY,
          action_type TEXT NOT NULL,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
          script_revision INTEGER NOT NULL,
          approved_by TEXT NOT NULL,
          spoken_confirmation TEXT NOT NULL,
          guardian_approval INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(episode_id, script_revision)
            REFERENCES script_revisions(episode_id, revision)
        );
        CREATE INDEX approval_records_episode_idx
          ON approval_records(episode_id, created_at);
        """,
    ),
    (
        2,
        "episode_events_and_idempotency",
        """
        CREATE TABLE episode_events (
          id TEXT PRIMARY KEY,
          episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
          sequence INTEGER NOT NULL,
          event_type TEXT NOT NULL,
          from_status TEXT NOT NULL,
          to_status TEXT NOT NULL,
          requested_by TEXT NOT NULL,
          reason TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(episode_id, sequence)
        );
        CREATE TABLE idempotency_records (
          scope TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          request_sha256 TEXT NOT NULL,
          response_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(scope, idempotency_key)
        );
        """,
    ),
    (
        3,
        "idempotent_operations",
        """
        CREATE TABLE idempotent_operations (
          scope TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          request_sha256 TEXT NOT NULL,
          resource_id TEXT NOT NULL,
          status TEXT NOT NULL,
          error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(scope, idempotency_key)
        );
        """,
    ),
    (
        4,
        "project_archival",
        """
        ALTER TABLE projects ADD COLUMN archived_at TEXT;
        """,
    ),
    (
        5,
        "season_plan_revisions",
        """
        CREATE TABLE IF NOT EXISTS season_plan_revisions (
          season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
          revision INTEGER NOT NULL,
          plan_json TEXT NOT NULL,
          source_transcript TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(season_id, revision)
        );
        CREATE TABLE IF NOT EXISTS season_plan_approval_records (
          id TEXT PRIMARY KEY,
          season_id TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
          plan_revision INTEGER NOT NULL,
          approved_by TEXT NOT NULL,
          spoken_confirmation TEXT NOT NULL,
          review_channel TEXT NOT NULL,
          guardian_approval INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(season_id, plan_revision)
            REFERENCES season_plan_revisions(season_id, revision)
        );
        CREATE INDEX IF NOT EXISTS season_plan_approvals_idx
          ON season_plan_approval_records(season_id, created_at);
        """,
    ),
    (
        6,
        "asset_consent_and_run_dependencies",
        """
        CREATE TABLE IF NOT EXISTS asset_consent_records (
          id TEXT PRIMARY KEY,
          asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
          action_type TEXT NOT NULL,
          consent_scope TEXT NOT NULL,
          recorded_by TEXT NOT NULL,
          statement TEXT NOT NULL,
          guardian_approved INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS asset_consent_records_asset_idx
          ON asset_consent_records(asset_id, created_at);
        CREATE TABLE IF NOT EXISTS production_run_assets (
          run_id TEXT NOT NULL REFERENCES production_runs(id) ON DELETE CASCADE,
          asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE RESTRICT,
          asset_sha256 TEXT NOT NULL,
          PRIMARY KEY(run_id, asset_id)
        );
        """,
    ),
    (
        7,
        "season_scoped_assets",
        """
        ALTER TABLE assets ADD COLUMN season_id TEXT REFERENCES seasons(id) ON DELETE CASCADE;
        CREATE INDEX IF NOT EXISTS assets_scope_idx
          ON assets(project_id, season_id, episode_id, created_at);
        """,
    ),
    (
        8,
        "creative_format_and_pipeline_route",
        """
        ALTER TABLE projects ADD COLUMN creative_format TEXT NOT NULL
          DEFAULT 'short_drama_series';
        ALTER TABLE projects ADD COLUMN production_pipeline TEXT NOT NULL
          DEFAULT 'qingshan-short-drama';
        """,
    ),
    (
        9,
        "privacy_safe_feedback_queue",
        """
        CREATE TABLE IF NOT EXISTS feedback_items (
          id TEXT PRIMARY KEY,
          project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
          category TEXT NOT NULL,
          message TEXT NOT NULL,
          source TEXT NOT NULL,
          screen TEXT NOT NULL,
          share_authorized INTEGER NOT NULL,
          guardian_approval INTEGER NOT NULL,
          status TEXT NOT NULL,
          redaction_applied INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS feedback_project_created_idx
          ON feedback_items(project_id, created_at);
        """,
    ),
    (
        10,
        "project_memory_cards",
        """
        CREATE TABLE IF NOT EXISTS memory_cards (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          asset_id TEXT NOT NULL UNIQUE REFERENCES assets(id) ON DELETE CASCADE,
          title TEXT NOT NULL,
          description TEXT NOT NULL,
          ocr_text TEXT NOT NULL,
          spoken_context TEXT NOT NULL,
          approximate_date TEXT NOT NULL,
          place TEXT NOT NULL,
          people_json TEXT NOT NULL,
          story_relevance TEXT NOT NULL,
          allowed_use TEXT NOT NULL,
          current_revision INTEGER NOT NULL,
          confirmation_status TEXT NOT NULL,
          confirmed_by TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS memory_cards_project_status_idx
          ON memory_cards(project_id, confirmation_status, created_at);
        CREATE TABLE IF NOT EXISTS memory_card_revisions (
          memory_id TEXT NOT NULL REFERENCES memory_cards(id) ON DELETE CASCADE,
          revision INTEGER NOT NULL,
          content_json TEXT NOT NULL,
          source_channel TEXT NOT NULL,
          change_summary TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(memory_id, revision)
        );
        CREATE TABLE IF NOT EXISTS memory_card_confirmation_records (
          id TEXT PRIMARY KEY,
          memory_id TEXT NOT NULL REFERENCES memory_cards(id) ON DELETE CASCADE,
          reviewed_revision INTEGER NOT NULL,
          confirmed_by TEXT NOT NULL,
          spoken_confirmation TEXT NOT NULL,
          review_channel TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(memory_id, reviewed_revision),
          FOREIGN KEY(memory_id, reviewed_revision)
            REFERENCES memory_card_revisions(memory_id, revision)
        );
        """,
    ),
    (
        11,
        "versioned_project_libraries",
        """
        CREATE TABLE IF NOT EXISTS library_entities (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          stable_name TEXT NOT NULL,
          current_revision INTEGER NOT NULL,
          confirmed_revision INTEGER,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(project_id, kind, stable_name)
        );
        CREATE INDEX IF NOT EXISTS library_entities_project_kind_idx
          ON library_entities(project_id, kind, stable_name);
        CREATE TABLE IF NOT EXISTS library_entity_revisions (
          entity_id TEXT NOT NULL REFERENCES library_entities(id) ON DELETE CASCADE,
          revision INTEGER NOT NULL,
          name TEXT NOT NULL,
          description TEXT NOT NULL,
          attributes_json TEXT NOT NULL,
          source_asset_ids_json TEXT NOT NULL,
          source_memory_ids_json TEXT NOT NULL,
          source_channel TEXT NOT NULL,
          change_summary TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(entity_id, revision)
        );
        CREATE TABLE IF NOT EXISTS library_entity_confirmation_records (
          id TEXT PRIMARY KEY,
          entity_id TEXT NOT NULL REFERENCES library_entities(id) ON DELETE CASCADE,
          reviewed_revision INTEGER NOT NULL,
          confirmed_by TEXT NOT NULL,
          spoken_confirmation TEXT NOT NULL,
          review_channel TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(entity_id, reviewed_revision),
          FOREIGN KEY(entity_id, reviewed_revision)
            REFERENCES library_entity_revisions(entity_id, revision)
        );
        """,
    ),
)


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        secure_directory(self.path.parent)
        connection = sqlite3.connect(self.path)
        secure_file(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            applied = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for version, name, sql in MIGRATIONS:
                if version in applied:
                    continue
                # A process can be interrupted after SQLite commits an ALTER TABLE
                # but before Nalu records the migration. Reconcile that state rather
                # than failing every subsequent launch with a duplicate-column error.
                if version == 4:
                    project_columns = {
                        row["name"]
                        for row in connection.execute("PRAGMA table_info(projects)")
                    }
                    if "archived_at" in project_columns:
                        connection.execute(
                            "INSERT INTO schema_migrations VALUES (?, ?, datetime('now'))",
                            (version, name),
                        )
                        continue
                if version == 7:
                    asset_columns = {
                        row["name"]
                        for row in connection.execute("PRAGMA table_info(assets)")
                    }
                    if "season_id" in asset_columns:
                        connection.execute(
                            "INSERT INTO schema_migrations VALUES (?, ?, datetime('now'))",
                            (version, name),
                        )
                        continue
                if version == 8:
                    project_columns = {
                        row["name"]
                        for row in connection.execute("PRAGMA table_info(projects)")
                    }
                    if "creative_format" not in project_columns:
                        connection.execute(
                            """ALTER TABLE projects ADD COLUMN creative_format TEXT NOT NULL
                               DEFAULT 'short_drama_series'"""
                        )
                    if "production_pipeline" not in project_columns:
                        connection.execute(
                            """ALTER TABLE projects ADD COLUMN production_pipeline TEXT NOT NULL
                               DEFAULT 'qingshan-short-drama'"""
                        )
                    connection.execute(
                        "INSERT INTO schema_migrations VALUES (?, ?, datetime('now'))",
                        (version, name),
                    )
                    continue
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, datetime('now'))",
                    (version, name),
                )

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()
        return int(row["version"])
