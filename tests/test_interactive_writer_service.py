import json

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.interactive_story import StoryInput
from nalu_runtime.interactive_writer_service import InteractiveWriterService, writer_request
from nalu_runtime.repository import ConflictError
from nalu_runtime.writer_transport import HopsWriterTransport


def test_saved_response_finishes_story_after_interrupted_answer_save(tmp_path, monkeypatch):
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "synthetic writer bridge"}).json()["id"]
        service = InteractiveWriterService(app.state.repository.db)
        service.story.append(project, StoryInput(turn_id="story", expected_revision=0,
                             text="合成故事：外婆看海", source_mode="narrated_story"))
        calls = []
        def serve(request):
            calls.append(request)
            return httpx.Response(200, json={"id": "fixture-task", "model": "fixture-model", "choices": [{
                "finish_reason": "stop", "message": {"content": json.dumps({"reply": "请核对",
                "summary": "合成回忆", "outcome": "answered", "episode_drafts": [{
                    "episode_number": 1, "title": "海边", "outline": "合成场景", "script": "外婆望着大海。"}]})}}]})
        transport = HopsWriterTransport(lambda: "fixture-key", transport=httpx.MockTransport(serve))
        def interrupted(*args, **kwargs):
            raise OSError("synthetic disk interruption")
        monkeypatch.setattr(service.story, "answer", interrupted)
        with pytest.raises(OSError):
            service.generate(project, "story", 1, model="fixture-model", transport=transport)
        # New queued input cannot change the request being recovered.
        restored = InteractiveWriterService(app.state.repository.db)
        restored.story.append(project, StoryInput(turn_id="later", expected_revision=1,
                              text="补充：蓝雨伞", source_mode="narrated_story", queue_only=True))
        state = restored.generate(project, "story", 1, model="fixture-model", transport=transport)
        assert len(calls) == 1
        assert state["episode_drafts"][0]["script"] == "外婆望着大海。"
        assert state["draft_writers"]["1"]["session_or_task_id"] == "fixture-task"
        assert state["draft_receipts"]["1"]
        assert state["queued_inputs"][0]["turn_id"] == "later"
        # Completed requests are recovered by reading story, not re-generating.
        with pytest.raises(ConflictError):
            restored.generate(project, "story", 1, model="fixture-model", transport=transport)
        assert len(calls) == 1


def test_request_excludes_unclaimed_queue_and_nested_raw_responses():
    state = {"turns": [{"answer": {"reply": "hello", "external_writer": {"secret": "metadata"},
                                  "writer_response_json": "raw output"}}],
             "queued_inputs": [{"text": "not claimed"}], "draft_receipts": {"1": "receipt"}}
    before = json.dumps(state)
    body = json.loads(writer_request(state, "fixture-model"))
    context = json.loads(body["messages"][1]["content"])
    assert context == {"turns": [{"answer": {"reply": "hello"}}]}
    assert body["store"] is False
    assert json.dumps(state) == before
