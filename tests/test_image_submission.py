from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.image_submission import ImageSubmissionService
from nalu_runtime.repository import ConflictError
from test_giggle_image_transport import request
from test_paid_submitter_boundary import paid_run


@pytest.mark.parametrize("case", ["accepted", "uncertain", "unauthorized", "concurrent", "cancel_before_http", "crash_after_http"])
def test_image_intent_survives_restart_and_never_reposts(tmp_path, case, monkeypatch):
    db_path = tmp_path / "image.sqlite3"
    api = TestClient(create_app(db_path, tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_image", model="seedance-2.0-pro")
    repo = api.app.state.repository
    service = ImageSubmissionService(repo)
    posts, approvals = [], []
    def authorize(run_id, task_key, request_sha):
        assert run_id == run.id and task_key == "E01-U01-entry" and len(request_sha) == 64
        approvals.append(request_sha)
        if case == "unauthorized":
            raise ConflictError("synthetic denial")
        if case == "cancel_before_http" and len(approvals) == 2:
            raise ConflictError("synthetic revoked approval")
    def provider(incoming):
        posts.append(incoming)
        events = repo.list_run_events(run.id)
        assert events[-1].event_type == "image_submit_intent"  # committed before HTTP
        assert events[-1].payload["request_sha256"] == approvals[-1]
        assert incoming.headers["Idempotency-Key"] == events[-1].payload["intent_id"]
        return httpx.Response(503 if case == "uncertain" else 200,
                              json={"code": 200, "data": {"task_id": "synthetic-image-task"}})
    transport = httpx.MockTransport(provider)
    arguments = {"secret": lambda: "synthetic-image-secret", "authorize": authorize, "transport": transport}
    if case == "crash_after_http":
        original = service._append
        def lose_receipt(db, run_id, kind, payload):
            if kind == "image_task_submitted":
                raise SystemExit("synthetic crash before receipt persistence")
            return original(db, run_id, kind, payload)
        monkeypatch.setattr(service, "_append", lose_receipt)
        with pytest.raises(SystemExit):
            service.submit(run.id, "E01-U01-entry", request(), **arguments)
    elif case == "unauthorized":
        with pytest.raises(ConflictError):
            service.submit(run.id, "E01-U01-entry", request(), **arguments)
        assert not posts
        assert not any(e.event_type.startswith("image_") for e in repo.list_run_events(run.id))
        return
    elif case == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: service.submit(run.id, "E01-U01-entry", request(), **arguments), range(2)))
        assert any(e.event_type == "image_task_submitted" for e in results)
    else:
        first = service.submit(run.id, "E01-U01-entry", request(), **arguments)
        assert first.payload["state"] == ("submitted" if case == "accepted" else "submission_unconfirmed")
    reopened = TestClient(create_app(db_path, tmp_path / "data"))
    recovered = ImageSubmissionService(reopened.app.state.repository)
    before = len(posts)
    saved = recovered.submit(run.id, "E01-U01-entry", request(), **arguments)
    assert len(posts) == before == (0 if case == "cancel_before_http" else 1)
    assert saved.payload["automatic_resubmit"] is False
    assert saved.payload["image_generated"] is False
    assert "synthetic-image-secret" not in saved.model_dump_json()
    if case in {"accepted", "concurrent"}:
        assert saved.payload["provider_task_id"] == "synthetic-image-task"
    else:
        assert saved.payload["state"] == "submission_unconfirmed"
    with pytest.raises(ConflictError):
        recovered.submit(run.id, "E01-U01-entry", {**request(), "prompt": "new prompt"}, **arguments)
    assert len(posts) == before


@pytest.mark.parametrize("state", ["dry_run", "cancelled", "archived"])
def test_ineligible_run_never_creates_image_intent(tmp_path, state):
    api = TestClient(create_app(tmp_path / "blocked.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_blocked_image", model="seedance-2.0-pro")
    repo = api.app.state.repository
    with repo.db.connect() as db:
        if state == "dry_run":
            db.execute("UPDATE production_runs SET dry_run=1 WHERE id=?", (run.id,))
        elif state == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        else:
            db.execute("UPDATE projects SET archived_at='2026-09-06' WHERE id=?", (run.project_id,))
    calls = []
    with pytest.raises(ConflictError):
        ImageSubmissionService(repo).submit(run.id, "E01-entry", request(), secret=lambda: "fixture",
            authorize=lambda *args: calls.append(args), transport=httpx.MockTransport(lambda _: pytest.fail("no HTTP allowed")))
    assert not calls
    assert not any(event.event_type.startswith("image_") for event in repo.list_run_events(run.id))
