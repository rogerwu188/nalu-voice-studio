#!/usr/bin/env python3
"""Create new temporary native story-review QA data; no provider or approval."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.novel_import import NovelImport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-mode", choices=["narrated_story", "web_source"], default="narrated_story")
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="nalu-native-story-"))
    with TestClient(create_app(root / "nalu.sqlite3", root / "data")) as api:
        plan = api.post("/v1/project-plans", json={"project": {
            "title": "【合成 QA】分集草稿采用", "planned_episode_count": 2}}).json()
        project = plan["project"]["id"]
        if args.source_mode == "web_source":
            importer = NovelImport(api.app.state.repository.db, reader=lambda url: {
                "url": url, "text": "【合成小说 QA】小夏在码头举起红桶，外婆陪着她。", "truncated": False})
            importer.create(project, "https://example.com/qa-novel", [
                {"url": "https://example.com/qa-novel/1", "title": "第一章 码头"}])
            importer.fetch_next(project)
        route = f"/v1/projects/{project}/interactive-story"
        turn = api.post(route + "/turns", json={"turn_id": "synthetic-review",
            "expected_revision": 0, "text": "【合成 QA】不是模型生成，请检查两集审阅。",
            "source_mode": args.source_mode})
        assert turn.status_code == 200, turn.text
        drafts = [{"episode_number": n, "title": f"【合成 QA】第{n}集", "outline": "虚构码头场景",
            "script": f"【合成 QA 第{n}集】外景，码头。小夏举起红桶。外婆：慢慢走，我陪着你。"}
            for n in (1, 2)]
        raw = json.dumps({"id": "fixture-native-two-episodes", "model": "fixture-writer",
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"episode_drafts": drafts}, ensure_ascii=False)}}]})
        declaration = {"provider": "fixture-provider", "model_id": "fixture-writer",
            "session_or_task_id": "fixture-native-two-episodes", "input_bundle_sha256": "a" * 64,
            "writer_rules_sha256": "b" * 64, "receipt_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "started_at": "2026-09-08T20:00:00Z", "completed_at": "2026-09-08T20:00:01Z"}
        saved = api.post(route + "/turns/synthetic-review/answer", json={
            "expected_revision": 1, "reply": "【合成 QA】两集测试草稿，请说采用第1集草稿。",
            "episode_drafts": drafts, "external_writer": declaration, "writer_response_json": raw})
        assert saved.status_code == 200, saved.text
        print(json.dumps({"application_support": str(root), "project_id": project,
            "episodes": [item["id"] for item in plan["episodes"]],
            "source_mode": args.source_mode, "provider_execution_verified": False, "approved": False}))


if __name__ == "__main__":
    main()
