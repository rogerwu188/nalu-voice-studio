import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.repository import ConflictError
from nalu_runtime.writer_observation import writer_observation


def test_observed_writer_response_binds_approved_episode_package(tmp_path):
    def serve(request):
        return httpx.Response(200, json={"id": "fixture-observed", "model": "fixture-model", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({
                "reply": "请审阅", "summary": "合成故事", "episode_drafts": [{
                    "episode_number": 1, "title": "海边", "outline": "合成场景", "script": "外婆看海。"}],
                "outcome": "answered"})}}]})
    app = create_app(tmp_path / "db", tmp_path / "data", writer_http_transport=httpx.MockTransport(serve))
    with TestClient(app) as client:
        plan = client.post("/v1/project-plans", json={"project": {
            "title": "合成观察绑定", "planned_episode_count": 1}, "season_title": "第一季"}).json()
        project, episode = plan["project"]["id"], plan["episodes"][0]["id"]
        path = f"/v1/projects/{project}/interactive-story"
        client.post(path + "/turns", json={"turn_id": "story", "expected_revision": 0,
                    "text": "合成故事", "source_mode": "narrated_story"})
        response = client.post(path + "/turns/story/generate",
            json={"expected_revision": 1, "model": "fixture-model"},
            headers={"X-Nalu-Writer-Key": "fixture-key"})
        assert response.status_code == 200, response.text
        state = response.json()
        scripts = f"/v1/episodes/{episode}/scripts"
        created = client.post(scripts, json={"content": "外婆看海。", "summary_for_voice_review": "请审阅",
            "authoring": {"origin": "external_ai_generated", "external_writer": state["draft_writers"]["1"]}})
        assert created.status_code == 201, created.text
        bound = client.post(scripts + "/1/writer-receipt-reconciliations",
            content=state["draft_receipts"]["1"].encode(),
            headers={"Content-Type": "application/octet-stream"}, params={"reconciled_by": "fixture QA"})
        assert bound.status_code == 201, bound.text
        receipt = app.state.repository.get_writer_receipt_reconciliation(episode, 1)
        evidence = writer_observation(app.state.repository.db, project, receipt)
        assert evidence["runtime_response_observed"] is True
        assert evidence["remote_lookup_performed"] is False
        assert evidence["production_authorized"] is False
        assert writer_observation(app.state.repository.db, "another-project", receipt) is None
        with pytest.raises(ConflictError):
            writer_observation(app.state.repository.db, project,
                               receipt.model_copy(update={"model_id": "wrong-model"}))
        client.post(scripts + "/1/approve", json={"approved_by": "fixture QA"})
        run = client.post(f"/v1/episodes/{episode}/production-runs", json={"dry_run": True})
        assert run.status_code == 201, run.text
        package = json.loads(Path(run.json()["package_path"]).read_text())
        assert package["runtime_writer_observation"] == evidence
        assert package["writer_provider_reconciliation"] is None
        with app.state.repository.db.connect() as connection:
            connection.execute("UPDATE writer_executions SET response_json='{}'")
        with pytest.raises(ConflictError, match="integrity"):
            writer_observation(app.state.repository.db, project, receipt)
        # Imported/uncertain executions cannot be upgraded by matching receipts.
        with app.state.repository.db.connect() as connection:
            connection.execute("UPDATE writer_executions SET state='ambiguous'")
        assert writer_observation(app.state.repository.db, project, receipt) is None
