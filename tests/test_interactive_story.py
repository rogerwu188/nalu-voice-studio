import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


@pytest.mark.parametrize("source_mode", ["narrated_story", "web_source"])
def test_supplements_persist_without_superseding_inflight_answer(tmp_path, source_mode):
    database, data = tmp_path / "db", tmp_path / "data"
    with TestClient(create_app(database, data)) as client:
        project = client.post("/v1/projects", json={"title": "连续讲述"}).json()["id"]
        path = f"/v1/projects/{project}/interactive-story"
        client.post(path + "/turns", json={"turn_id": "first", "expected_revision": 0,
            "text": "外婆带我看海", "source_mode": "narrated_story"})
        supplement = {"turn_id": "supplement", "expected_revision": 0,
            "text": "还有，我当时六岁", "source_mode": source_mode, "queue_only": True}
        for _ in range(2):
            queued = client.post(path + "/turns", json=supplement).json()
            assert queued["revision"] == 1
            assert queued["turns"][-1]["status"] == "pending"
            assert len(queued["queued_inputs"]) == 1
        assert client.post(path + "/turns", json={**supplement, "text": "错的补充"}).status_code == 409
        result = client.post(path + "/turns/first/answer", json={
            "expected_revision": 1, "reply": "第一句已处理"})
        assert result.status_code == 200
        assert result.json()["queued_inputs"][0]["text"] == supplement["text"]
    with TestClient(create_app(database, data)) as client:
        state = client.get(path).json()
        assert len(state["queued_inputs"]) == 1
        promoted = {**supplement, "expected_revision": state["revision"], "queue_only": False}
        for _ in range(2):
            state = client.post(path + "/turns", json=promoted).json()
            assert len(state["turns"]) == 2
            assert state["queued_inputs"] == []
            assert state["turns"][-1]["text"] == supplement["text"]
            assert state["turns"][-1]["source_mode"] == source_mode


def test_two_episode_writer_drafts_enter_review_with_distinct_bound_receipts(tmp_path):
    with TestClient(create_app(tmp_path / "db", tmp_path / "data")) as client:
        plan = client.post("/v1/project-plans", json={"project": {
            "title": "合成两集故事", "planned_episode_count": 2}}).json()
        path = f"/v1/projects/{plan['project']['id']}/interactive-story"
        client.post(path + "/turns", json={"turn_id": "story", "expected_revision": 0,
            "text": "合成故事写两集", "source_mode": "narrated_story"})
        drafts = [{"episode_number": n, "title": f"第{n}集", "outline": "合成场景",
                   "script": f"合成第{n}集：海边，相认。"} for n in (1, 2)]
        raw = json.dumps({"id": "fixture-multiple", "model": "fixture-writer-1", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({"episode_drafts": drafts})}}]})
        declaration = {"provider": "fixture-provider", "model_id": "fixture-writer-1",
            "session_or_task_id": "fixture-multiple", "input_bundle_sha256": "a" * 64,
            "writer_rules_sha256": "b" * 64, "receipt_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "started_at": "2026-09-06T20:00:00Z", "completed_at": "2026-09-06T20:00:01Z"}
        response = client.post(path + "/turns/story/answer", json={"expected_revision": 1,
            "reply": "请审阅两集", "episode_drafts": drafts,
            "external_writer": declaration, "writer_response_json": raw})
        assert response.status_code == 200
        state = response.json()
        for number, episode in enumerate(plan["episodes"], 1):
            script = client.post(f"/v1/episodes/{episode['id']}/scripts", json={
                "content": drafts[number - 1]["script"], "summary_for_voice_review": "合成审阅",
                "authoring": {"origin": "external_ai_generated",
                              "external_writer": state["draft_writers"][str(number)]}}).json()
            url = f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/writer-receipt-reconciliations"
            for _ in range(2):
                bound = client.post(url, content=state["draft_receipts"][str(number)].encode(),
                    headers={"Content-Type": "application/octet-stream"}, params={"reconciled_by": "synthetic QA"})
                assert bound.status_code == 201, bound.text
                assert bound.json()["artifact_binding_verified"] is True
                assert bound.json()["provider_execution_verified"] is False
            assert script["approved_at"] is None


def test_writer_declaration_tracks_revised_episode_and_retains_response(tmp_path):
    with TestClient(create_app(tmp_path / "db", tmp_path / "data")) as client:
        project = client.post("/v1/projects", json={"title": "故事"}).json()["id"]
        path = f"/v1/projects/{project}/interactive-story"
        declaration = {
            "provider": "fixture-provider", "model_id": "fixture-model",
            "session_or_task_id": "fixture-task", "input_bundle_sha256": "a" * 64,
            "writer_rules_sha256": "b" * 64, "receipt_sha256": "c" * 64,
            "started_at": "2026-09-06T20:00:00Z", "completed_at": "2026-09-06T20:00:01Z",
        }
        for index in range(2):
            client.post(path + "/turns", json={"turn_id": str(index),
                "expected_revision": index * 2, "text": "修改第一集", "source_mode": "narrated_story"})
            payload = {"expected_revision": index * 2 + 1, "reply": "草稿待审阅",
                "episode_drafts": [{"episode_number": 1, "title": "童年", "outline": "海边",
                                    "script": f"第{index}版"}]}
            if index == 0:
                raw = json.dumps({"id": "fixture-task", "model": "fixture-model", "choices": [{
                    "finish_reason": "stop", "message": {"content": json.dumps({
                        "episode_drafts": payload["episode_drafts"]})}}]})
                declaration["receipt_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
                payload.update(external_writer=declaration, writer_response_json=raw)
                rejected = client.post(path + f"/turns/{index}/answer",
                    json={**payload, "writer_response_json": raw + " "})
                assert rejected.status_code == 409
                assert client.get(path).json()["turns"][-1]["status"] == "pending"
            saved = client.post(path + f"/turns/{index}/answer", json=payload)
            assert saved.status_code == 200
            if index == 0:
                assert saved.json()["draft_writers"]["1"]["session_or_task_id"] == "fixture-task"
                assert saved.json()["draft_writers"]["1"]["receipt_sha256"] != declaration["receipt_sha256"]
                assert saved.json()["draft_receipts"]["1"]
        state = client.get(path).json()
        assert state["draft_writers"]["1"] is None  # never inherit old writer identity
        assert state["turns"][0]["answer"]["writer_response_json"] == raw
        assert state["draft_receipts"]["1"] is None
        assert state["turns"][0]["answer"]["episode_drafts"][0]["script"] == "第0版"
        assert state["episode_drafts"][0]["script"] == "第1版"


def test_two_sources_continue_same_story_and_survive_restart(tmp_path):
    database = tmp_path / "nalu.sqlite3"
    data = tmp_path / "data"
    with TestClient(create_app(database, data)) as client:
        project = client.post("/v1/projects", json={
            "title": "爷爷的故事", "project_bible": {"existing_character": "爷爷"},
        }).json()
        path = f"/v1/projects/{project['id']}/interactive-story"
        first = {"turn_id": "first", "expected_revision": 0,
                 "text": "我小时候和外婆在海边生活", "source_mode": "narrated_story"}
        assert client.post(path + "/turns", json=first).json()["revision"] == 1
        answer = {"expected_revision": 1, "reply": "那天发生了什么？",
                  "summary": "外婆和海边童年", "episode_drafts": [
                      {"episode_number": 1, "title": "海边", "outline": "祖孙相伴", "script": "第一场：码头。"},
                  ]}
        assert client.post(path + "/turns/first/answer", json=answer).json()["revision"] == 2
        # HTTP retry must not duplicate a user turn or response.
        assert client.post(path + "/turns", json=first).json()["revision"] == 2
        assert client.post(path + "/turns/first/answer", json=answer).json()["revision"] == 2
        assert client.post(path + "/turns", json={
            "turn_id": "source", "expected_revision": 2,
            "text": "再帮我找这个村子的历史网址", "source_mode": "web_source",
        }).status_code == 200
        failed = client.post(path + "/turns/source/answer", json={
            "expected_revision": 3, "reply": "查找暂时失败，可以继续讲故事。",
            "outcome": "lookup_failed", "summary": "不应覆盖",
        }).json()
        assert failed["summary"] == "外婆和海边童年"
        assert failed["episode_drafts"][0]["script"] == "第一场：码头。"
        assert len(failed["turns"]) == 2
        saved = client.get(f"/v1/projects/{project['id']}").json()
        assert saved["project_bible"]["existing_character"] == "爷爷"
    with TestClient(create_app(database, data)) as restarted:
        assert restarted.get(path).json() == failed


def test_stale_answer_and_wrong_project_cannot_replace_story(tmp_path):
    with TestClient(create_app(tmp_path / "db", tmp_path / "data")) as client:
        one = client.post("/v1/projects", json={"title": "一"}).json()["id"]
        two = client.post("/v1/projects", json={"title": "二"}).json()["id"]
        path = f"/v1/projects/{one}/interactive-story"
        for revision, turn in enumerate(["a", "b"]):
            assert client.post(path + "/turns", json={
                "turn_id": turn, "expected_revision": revision, "text": turn,
                "source_mode": "narrated_story",
            }).status_code == 200
        response = {"expected_revision": 1, "reply": "迟到的回答"}
        assert client.post(path + "/turns/a/answer", json=response).status_code == 409
        assert client.post(f"/v1/projects/{two}/interactive-story/turns/b/answer", json=response).status_code == 409
        assert client.get(path).json()["turns"][0]["status"] == "superseded"
        assert client.get(f"/v1/projects/{two}/interactive-story").json()["turns"] == []
