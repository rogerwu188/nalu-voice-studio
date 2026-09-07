import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from test_image_budget import prepared_image


def test_video_preparation_holds_snapshot_lock_through_validation_and_replay(tmp_path, monkeypatch):
    import sqlite3

    from nalu_runtime.video_preparation import VideoPreparationRequest, VideoPreparationService
    api, run, _ = prepared_image(tmp_path)
    repo = api.app.state.repository
    service = VideoPreparationService(repo)
    def validate(*_):
        with repo.db.connect() as other:
            other.execute("PRAGMA busy_timeout=1")
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("UPDATE production_runs SET package_path='wrong' WHERE id=?", (run.id,))
        return {"preparation_sha256": "a" * 64, "task_key": "E01-U01", "generation_performed": False}
    monkeypatch.setattr(service, "validate", validate)
    request = VideoPreparationRequest(task_key="E01-U01", request={})
    first = service.prepare(run.id, request)
    assert service.prepare(run.id, request).id == first.id
    assert repo.get_run(run.id).package_path == run.package_path
    assert len([event for event in repo.list_run_events(run.id) if event.event_type == "video_task_prepared"]) == 1


@pytest.mark.parametrize("case", ["ok", "unknown_shot", "wrong_plan", "changed_plan", "cancelled", "extra_fields", "boolean_index"])
def test_native_shot_selection_resolves_preparation_without_technical_inputs(tmp_path, case):
    api, run, previous = prepared_image(tmp_path)
    repo = api.app.state.repository
    plan_id = previous["payload"]["approved_plan_event_id"]
    # Remove only the test's initial preparation to exercise the empty entry.
    with repo.db.connect() as db:
        db.execute("DELETE FROM run_events WHERE id=?", (previous["id"],))
        if case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
    if case == "changed_plan":
        repo.append_run_event(run.id, "shot_plan_revised", payload={"synthetic": True})
    if case == "wrong_plan":
        plan_id = "old-plan"
    endpoint = f"/v1/production-runs/{run.id}/shot-plans/{plan_id}/opening-frame-preparations"
    body = {"shot_index": 1 if case == "unknown_shot" else 0}
    if case == "extra_fields":
        body["paid_approved"] = True
    if case == "boolean_index":
        body["shot_index"] = False
    assert api.post(endpoint, json=body, headers={"Origin": "https://example.org"}).status_code in {403, 422}
    result = api.post(endpoint, json=body)
    if case in {"extra_fields", "boolean_index"}:
        assert result.status_code == 422
    elif case != "ok":
        assert result.status_code == 409, result.text
    else:
        assert result.status_code == 200, result.text
        record = result.json()["payload"]
        assert record["image_task_key"] == "E01-U01-entry"
        assert record["approved_plan_sha256"] == previous["payload"]["approved_plan_sha256"]
        assert record["generation_performed"] is False and record["paid_approved"] is False
        assert record["preparation_sha256"] == previous["payload"]["preparation_sha256"]
        reopened = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
        assert reopened.post(endpoint, json=body).json()["id"] == result.json()["id"]
    assert not any(e.event_type in {"image_submit_intent", "image_task_submitted"} for e in repo.list_run_events(run.id))
