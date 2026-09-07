import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.image_download import ImageDownloadError
from nalu_runtime.image_submission import ImageSubmissionService
from test_giggle_image_transport import request
from test_image_download import png
from test_paid_submitter_boundary import paid_run


@pytest.mark.parametrize("case", ["completed", "pending", "processing", "failed", "error", "uncertain",
                                  "query_error", "download_error", "multiple", "changed_file", "cancelled",
                                  "cancel_during_query", "cancel_during_download", "archived", "damaged_observation"])
def test_saved_image_advances_to_review_without_regeneration(tmp_path, monkeypatch, case):
    posts, gets, downloads = [], [], []
    def submit(incoming):
        posts.append(incoming)
        return httpx.Response(503 if case == "uncertain" else 200,
                              json={"code": 200, "data": {"task_id": "fixture-image"}})
    def query(incoming):
        gets.append(incoming)
        assert incoming.method == "GET"
        if case == "cancel_during_query":
            with repo.db.connect() as db:
                db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        return httpx.Response(503 if case == "query_error" else 200, json={"code": 200, "data": {
            "task_id": "fixture-image", "status": case if case in {"pending", "processing", "failed", "error"} else "completed",
            "urls": ["https://example.org/frame.png"] * (2 if case == "multiple" else 1)}})
    def download(url):
        downloads.append(url)
        if case == "download_error" and len(downloads) == 1:
            raise ImageDownloadError("synthetic download interruption")
        if case == "cancel_during_download":
            with repo.db.connect() as db:
                db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        return png()
    monkeypatch.setattr("nalu_runtime.image_materialization.download_image", download)
    db_path, root = tmp_path / "db", tmp_path / "data"
    def client():
        return TestClient(create_app(db_path, root, task_query_http_transport=httpx.MockTransport(query)))
    api = client()
    repo = api.app.state.repository
    run = paid_run(api, tmp_path, run_id="run_image_progress", model="seedance-2.0-pro")
    binding = ImageSubmissionService(repo).submit(run.id, "E01-U01-entry", request(), secret=lambda: "synthetic-key",
        authorize=lambda *args: None, transport=httpx.MockTransport(submit))  # synthetic authority, no paid provider
    with repo.db.connect() as db:
        if case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        if case == "archived":
            db.execute("UPDATE projects SET archived_at='2026-09-07' WHERE id=?", (run.project_id,))
    endpoint = f"/v1/production-runs/{run.id}/image-tasks/{binding.id}/advance"
    headers = {"X-Nalu-Provider-Key": "synthetic-key"}
    assert api.post(endpoint).status_code == 403
    assert api.post(endpoint, headers={**headers, "Origin": "https://example.org"}).status_code == 403
    result = api.post(endpoint, headers=headers)
    assert "synthetic-key" not in result.text and "example.org" not in result.text
    if case in {"uncertain", "cancelled", "archived", "cancel_during_query", "multiple"}:
        assert result.status_code == 409, result.text
        assert not downloads
    elif case == "query_error":
        assert result.status_code == 502 and not downloads
    elif case == "cancel_during_download":
        assert result.status_code == 409 and len(downloads) == 1
        assert client().post(endpoint, headers=headers).status_code == 409
        assert len(downloads) == 1 and len(gets) == 1
    else:
        if case == "download_error":
            assert result.status_code == 502
            result = client().post(endpoint, headers=headers)
            assert len(gets) == 1  # Resume saved completion; don't query or submit again.
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["generation_performed"] is False and data["billing_verified"] is False
        assert data["visual_semantics_verified"] is False
        if case in {"pending", "processing"}:
            assert data["phase"] == "waiting" and data["materialization_id"] is None and not downloads
        elif case in {"failed", "error"}:
            assert data["phase"] == "provider_failed" and not downloads
        else:
            assert data["phase"] == "ready_for_review"
            event = repo.get_run_event(data["materialization_id"])
            if case == "changed_file":
                (root / "runs" / run.id / "generated-images" / event.payload["filename"]).write_bytes(b"altered fixture")
            if case == "damaged_observation":
                with repo.db.connect() as db:
                    db.execute("UPDATE run_events SET payload_json=json_set(payload_json,'$.observation_sha256','bad') WHERE id=?",
                               (data["observation_id"],))
        previous_downloads = len(downloads)
        repeated = client().post(endpoint, headers=headers)
        if case in {"changed_file", "damaged_observation"}:
            assert repeated.status_code == 409
        else:
            assert repeated.status_code == 200 and repeated.json() == data
        assert len(downloads) == previous_downloads
        assert len(gets) == (2 if case in {"pending", "processing"} else 1)
    assert len(posts) == 1  # The advance service never reaches a generation POST.
