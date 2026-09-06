import json

import httpx
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def test_native_generation_endpoint_owns_prompt_and_saves_drafts_without_key(tmp_path):
    calls = []
    def serve(request):
        calls.append(request)
        body = json.loads(request.content)
        assert "合成故事" in body["messages"][1]["content"]
        assert body["store"] is False
        return httpx.Response(200, json={"id": "fixture-native", "model": "fixture-model", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({
                "reply": "请审阅", "summary": "合成故事", "episode_drafts": [{
                    "episode_number": 1, "title": "海边", "outline": "合成场景", "script": "外婆看海。"}],
                "outcome": "answered"})}}]})
    app = create_app(tmp_path / "db", tmp_path / "data", writer_http_transport=httpx.MockTransport(serve))
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "native API fixture"}).json()["id"]
        path = f"/v1/projects/{project}/interactive-story"
        client.post(path + "/turns", json={"turn_id": "turn", "expected_revision": 0,
                    "text": "合成故事", "source_mode": "narrated_story"})
        url = path + "/turns/turn/generate"
        body = {"expected_revision": 1, "model": "fixture-model"}
        headers = {"X-Nalu-Writer-Key": "fixture-private-key"}
        assert client.post(url, json=body).status_code == 403
        assert client.post(url, json=body, headers={**headers, "Origin": "https://untrusted.invalid"}).status_code == 403
        assert client.post(url, json={**body, "url": "https://other.invalid"}, headers=headers).status_code == 422
        assert calls == []
        response = client.post(url, json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["episode_drafts"][0]["script"] == "外婆看海。"
        assert response.json()["draft_receipts"]["1"]
        assert client.post(url, json=body, headers=headers).status_code == 409
        assert len(calls) == 1
        with app.state.repository.db.connect() as connection:
            row = dict(connection.execute("SELECT * FROM writer_executions").fetchone())
        assert row["state"] == "completed"
        assert "fixture-private-key" not in str(row)


def test_generation_failure_keeps_story_and_quarantines_retry(tmp_path):
    calls = []
    def serve(request):
        calls.append(request)
        return httpx.Response(401, text="private-key-provider-error")
    app = create_app(tmp_path / "db", tmp_path / "data", writer_http_transport=httpx.MockTransport(serve))
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "failure fixture"}).json()["id"]
        path = f"/v1/projects/{project}/interactive-story"
        client.post(path + "/turns", json={"turn_id": "turn", "expected_revision": 0,
                    "text": "合成故事保留", "source_mode": "narrated_story"})
        url = path + "/turns/turn/generate"
        kwargs = {"json": {"expected_revision": 1, "model": "fixture-model"},
                  "headers": {"X-Nalu-Writer-Key": "fixture-private-key"}}
        first = client.post(url, **kwargs)
        assert first.status_code == 502
        assert first.json() == {"detail": "writer_http_401"}
        assert client.post(url, **kwargs).status_code == 409
        assert len(calls) == 1
        assert client.get(path).json()["turns"][0]["text"] == "合成故事保留"
