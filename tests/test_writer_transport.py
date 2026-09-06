import json

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.repository import ConflictError
from nalu_runtime.writer_execution import WriterExecution
from nalu_runtime.writer_transport import (
    HopsWriterTransport,
    WriterTransportError,
    validate_writer_response,
)


def request_body():
    return json.dumps({"model": "fixture-writer", "store": False, "max_completion_tokens": 8000,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": "synthetic story"}]}).encode()


def response_body():
    return {"id": "fixture-task", "model": "fixture-writer", "choices": [{
        "finish_reason": "stop", "message": {"content": json.dumps({
            "reply": "请核对", "summary": "合成测试", "episode_drafts": [{
                "episode_number": 1, "title": "海边", "outline": "合成场景", "script": "合成剧本"}],
            "outcome": "answered"})}}]}


def test_authenticated_transport_is_ledger_bound_and_not_resent(tmp_path):
    calls = []
    def serve(request):
        calls.append(request)
        assert str(request.url) == HopsWriterTransport.endpoint
        assert request.headers["Authorization"] == "Bearer fixture-secret"
        assert json.loads(request.content)["store"] is False
        return httpx.Response(200, json=response_body())
    transport = HopsWriterTransport(lambda: "fixture-secret", transport=httpx.MockTransport(serve))
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "synthetic transport"}).json()["id"]
        ledger = WriterExecution(app.state.repository.db)
        for _ in range(2):
            raw = ledger.execute(project, "turn", request_body(),
                                 destination=transport.endpoint, transport=transport)
            assert json.loads(raw)["id"] == "fixture-task"
        assert len(calls) == 1


@pytest.mark.parametrize("status", [301, 401, 429, 500])
def test_failed_http_is_redacted_and_not_retried(tmp_path, status):
    calls = []
    def serve(request):
        calls.append(request)
        return httpx.Response(status, text="fixture-secret", headers={"Location": "https://other.invalid"})
    transport = HopsWriterTransport(lambda: "fixture-secret", transport=httpx.MockTransport(serve))
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "synthetic failure"}).json()["id"]
        ledger = WriterExecution(app.state.repository.db)
        with pytest.raises(WriterTransportError, match=f"writer_http_{status}"):
            ledger.execute(project, "turn", request_body(), destination=transport.endpoint, transport=transport)
        with pytest.raises(ConflictError):
            ledger.execute(project, "turn", request_body(), destination=transport.endpoint, transport=transport)
        assert len(calls) == 1


@pytest.mark.parametrize("change", ["length", "missing_id", "duplicate", "empty_script"])
def test_incomplete_or_invalid_writer_answers_are_rejected(change):
    body = response_body()
    if change == "length":
        body["choices"][0]["finish_reason"] = "length"
    elif change == "missing_id":
        del body["id"]
    elif change == "duplicate":
        body["choices"][0]["message"]["content"] = '{"reply":"yes","reply":"no"}'
    else:
        answer = json.loads(body["choices"][0]["message"]["content"])
        answer["episode_drafts"][0]["script"] = "  "
        body["choices"][0]["message"]["content"] = json.dumps(answer)
    with pytest.raises(WriterTransportError):
        validate_writer_response(json.dumps(body).encode())
