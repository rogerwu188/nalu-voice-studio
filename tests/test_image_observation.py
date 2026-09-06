import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.image_submission import ImageSubmissionService
from test_giggle_image_transport import request
from test_paid_submitter_boundary import paid_run


@pytest.mark.parametrize("case", ["pending", "processing", "completed", "failed", "error", "uncertain",
                                  "query_error", "wrong_identity", "archived", "cancelled", "archive_during_query",
                                  "secret_url", "damaged_receipt"])
def test_saved_image_query_does_not_generate_or_claim_media_qa(tmp_path, case):
    posts, gets = [], []
    def submit(incoming):
        posts.append(incoming)
        return httpx.Response(503 if case == "uncertain" else 200,
                             json={"code": 200, "data": {"task_id": "synthetic-image-task"}})
    def query(incoming):
        gets.append(incoming)
        assert incoming.method == "GET" and incoming.url.params["task_id"] == "synthetic-image-task"
        assert incoming.headers["x-auth"] == "fixture-image-secret"
        if case == "archive_during_query":
            with repo.db.connect() as db:
                db.execute("UPDATE projects SET archived_at='2026-09-07' WHERE id=?", (run.project_id,))
        return httpx.Response(503 if case == "query_error" else 200, json={"code": 200, "data": {
            "task_id": "wrong-image-task" if case == "wrong_identity" else "synthetic-image-task",
            "status": case if case in {"pending", "processing", "failed", "error"} else "completed",
            "urls": ["https://example.org/fixture-image-secret.png" if case == "secret_url" else "https://example.org/image.png"]}})
    db_path = tmp_path / "image-query.sqlite3"
    api = TestClient(create_app(db_path, tmp_path / "data", task_query_http_transport=httpx.MockTransport(query)))
    repo = api.app.state.repository
    run = paid_run(api, tmp_path, run_id="run_image_query", model="seedance-2.0-pro")
    binding = ImageSubmissionService(repo).submit(run.id, "E01-U01-entry", request(), secret=lambda: "fixture-image-secret",
        authorize=lambda *args: None, transport=httpx.MockTransport(submit))  # synthetic authority, not a paid approval
    with repo.db.connect() as db:
        if case == "archived":
            db.execute("UPDATE projects SET archived_at='2026-09-07' WHERE id=?", (run.project_id,))
        elif case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        elif case == "damaged_receipt":
            db.execute("UPDATE run_events SET payload_json='{}' WHERE id=?", (binding.id,))
    endpoint = f"/v1/production-runs/{run.id}/image-tasks/{binding.id}/refresh"
    headers = {"X-Nalu-Provider-Key": "fixture-image-secret"}
    assert api.post(endpoint).status_code == 403
    assert api.post(endpoint, headers={**headers, "Origin": "https://example.org"}).status_code == 403
    result = api.post(endpoint, headers=headers)
    assert len(posts) == 1
    assert "fixture-image-secret" not in result.text
    if case in {"uncertain", "archived", "damaged_receipt"}:
        assert result.status_code == 409 and not gets
    elif case in {"query_error", "wrong_identity", "secret_url", "archive_during_query"}:
        assert result.status_code in {409, 502} and len(gets) == 1
        assert not any(e.event_type == "image_task_observed" for e in repo.list_run_events(run.id))
    else:
        assert result.status_code == 200, result.text
        observation = result.json()["payload"]
        assert observation["billing_verified"] is False
        assert observation["image_downloaded"] is False and observation["visual_semantics_verified"] is False
        assert observation["master_accepted"] is False
        assert observation["request_sha256"] == binding.payload["request_sha256"]
        assert observation["submission_id"] == binding.id
        restarted = TestClient(create_app(db_path, tmp_path / "data", task_query_http_transport=httpx.MockTransport(query)))
        assert restarted.post(endpoint, headers=headers).json()["id"] == result.json()["id"]
        assert len(posts) == 1 and len(gets) == 2
        assert repo.get_run(run.id).status == ("cancelled" if case == "cancelled" else "waiting_for_approval")
