#!/usr/bin/env python3
"""Create new temporary native story-review QA data; no provider or approval."""

import hashlib
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def main():
    root = Path(tempfile.mkdtemp(prefix="nalu-native-story-"))
    with TestClient(create_app(root / "nalu.sqlite3", root / "data")) as api:
        plan = api.post("/v1/project-plans", json={"project": {
            "title": "【合成 QA】分集草稿采用", "planned_episode_count": 2}}).json()
        project = plan["project"]["id"]
        route = f"/v1/projects/{project}/interactive-story"
        turn = api.post(route + "/turns", json={"turn_id": "synthetic-review",
            "expected_revision": 0, "text": "【合成 QA】不是模型生成，请检查两集审阅。",
            "source_mode": "narrated_story"})
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
            "provider_execution_verified": False, "approved": False}))


if __name__ == "__main__":
    main()
