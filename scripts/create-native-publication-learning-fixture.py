#!/usr/bin/env python3
"""Create an isolated local-only data root for native publication-learning UI QA.

The fixture never contacts a provider and refuses every path outside the operating
system temporary directory. It creates a new SQLite database only; existing directories
with content are rejected so a user's Nalu library cannot be replaced accidentally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = REPOSITORY_ROOT / "services/runtime_api"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require_empty_temporary_root(raw_root: Path) -> Path:
    temporary_root = Path(tempfile.gettempdir()).resolve()
    root = raw_root.expanduser().resolve()
    if root == temporary_root or temporary_root not in root.parents:
        raise ValueError("QA root must be a child of the operating system temporary directory")
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("QA root must be empty; refusing to replace existing data")
    return root


def build_fixture(raw_root: Path) -> dict[str, Any]:
    root = require_empty_temporary_root(raw_root)
    sys.path.insert(0, str(RUNTIME_SOURCE))
    from nalu_runtime.database import Database
    from nalu_runtime.models import EpisodeCreate, ProjectCreate, SeasonCreate
    from nalu_runtime.repository import Repository, new_id, utc_now

    database_path = root / "nalu.sqlite3"
    data_root = root / "data"
    data_root.mkdir(mode=0o700)
    database = Database(database_path)
    database.initialize()
    repository = Repository(database)

    project = repository.create_project(
        ProjectCreate(
            title="【QA 临时】老照片里的团圆饭",
            description="只用于验证大字、朗读和 VoiceOver 的本地临时项目。",
            audience_mode="older_adult",
            planned_episode_count=2,
            target_episode_seconds=180,
            project_bible={"qa_fixture": True, "external_network": False},
        )
    )
    season = repository.create_season(
        project.id,
        SeasonCreate(
            title="第一季",
            season_number=1,
            planned_episode_count=2,
            season_arc={"summary": "从一张旧照片讲到一家人的再次团聚。"},
        ),
    )
    source_episode = repository.create_episode(
        season.id,
        EpisodeCreate(
            title="第一集 · 那张旧照片",
            episode_number=1,
            logline="林爷爷从一张旧照片讲起。",
            target_seconds=180,
        ),
    )
    target_episode = repository.create_episode(
        season.id,
        EpisodeCreate(
            title="第二集 · 回家的路",
            episode_number=2,
            logline="一家人沿着回忆找到旧居。",
            target_seconds=180,
        ),
    )

    now = utc_now()
    run_id = new_id("run")
    package_path = data_root / "qa-completed-package.json"
    package_path.write_text(
        canonical({"qa_fixture": True, "network_call_performed": False}),
        encoding="utf-8",
    )
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO production_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                project.id,
                season.id,
                source_episode.id,
                "completed",
                1,
                "local-qa-fixture",
                0,
                str(package_path),
                None,
                now,
                now,
            ),
        )

    metrics_id = new_id("metrics")
    request_sha256 = hashlib.sha256(b"native-publication-learning-fixture-request").hexdigest()
    key_sha256 = hashlib.sha256(uuid4().hex.encode()).hexdigest()
    metrics_body = {
        "schema_version": "nalu.publication-metrics/v1",
        "id": metrics_id,
        "run_id": run_id,
        "project_id": project.id,
        "episode_id": source_episode.id,
        "platform": "bilibili",
        "remote_publication_id": "local_qa_not_published",
        "publication_record_sha256": "1" * 64,
        "window_start": "2026-08-01T00:00:00+00:00",
        "window_end": "2026-08-08T00:00:00+00:00",
        "views": 1280,
        "unique_viewers": 1042,
        "watch_time_seconds": 92160,
        "average_view_duration_seconds": 72.0,
        "completion_rate": 0.52,
        "likes": 186,
        "comments": 34,
        "shares": 48,
        "followers_gained": 21,
        "verification_evidence_sha256": "2" * 64,
        "read_only_sync_performed": True,
        "publication_performed": False,
        "production_performed": False,
        "external_write_performed": False,
        "idempotency_key_sha256": key_sha256,
        "request_sha256": request_sha256,
        "created_at": now,
    }
    metrics_sha256 = digest(metrics_body)
    strategy_id = new_id("strategy")
    strategy_body = {
        "schema_version": "nalu.director-strategy/v1",
        "id": strategy_id,
        "project_id": project.id,
        "target_episode_id": target_episode.id,
        "source_metrics_id": metrics_id,
        "source_metrics_sha256": metrics_sha256,
        "revision": 1,
        "observations": [
            "本次核验窗口完播率为 52.0%。",
            "观众愿意分享家庭团聚的段落，但开场进入回忆稍慢。",
        ],
        "directives": [
            "下一集前 15 秒先说清楚一家人为什么要回旧居。",
            "保留团圆饭的真实细节，并继续使用老人容易听懂的短句。",
            "任何调整都先形成新的分集剧本，再请用户朗读确认。",
        ],
        "immutable_constraints": [
            "不得改写已确认的人物、照片和家庭关系",
            "不能自动启动制作、付费调用或发行",
        ],
        "requires_script_revision_and_approval": True,
        "production_started": False,
        "publication_performed": False,
        "created_at": now,
    }
    strategy_sha256 = digest(strategy_body)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO publication_metric_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metrics_id,
                run_id,
                metrics_body["platform"],
                metrics_body["remote_publication_id"],
                metrics_body["window_start"],
                metrics_body["window_end"],
                request_sha256,
                key_sha256,
                canonical(metrics_body),
                metrics_sha256,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO director_strategy_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id,
                project.id,
                target_episode.id,
                metrics_id,
                1,
                canonical(strategy_body),
                strategy_sha256,
                now,
            ),
        )

    return {
        "schema_version": "nalu.native-publication-learning-fixture/v1",
        "status": "READY",
        "application_support": str(root),
        "database_path": str(database_path),
        "project_id": project.id,
        "strategy_id": strategy_id,
        "metrics_id": metrics_id,
        "environment": {
            "NALU_ENABLE_LOCAL_QA": "1",
            "NALU_LOCAL_QA_APPLICATION_SUPPORT": str(root),
        },
        "network_scope": "none; fixture creation performs no provider, paid or publication call",
        "production_data_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    result = build_fixture(args.root)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.evidence:
        args.evidence.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
