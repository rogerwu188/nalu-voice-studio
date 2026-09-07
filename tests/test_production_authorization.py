import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from nalu_runtime.shot_planning import ShotPlan, ShotPlanningService
from nalu_runtime.video_preparation import digest
from test_project_library import client


def setup(tmp_path, audience="general"):
    api = client(tmp_path)
    repo = api.app.state.repository
    planning = api.post("/v1/project-plans", json={"project": {
        "title": "讲述后继续制作", "planned_episode_count": 1, "audience_mode": audience}})
    assert planning.status_code == 201, planning.text
    episode = planning.json()["episodes"][0]
    script = api.post(f"/v1/episodes/{episode['id']}/scripts", json={
        "content": "经过用户确认的剧本", "summary_for_voice_review": "讲述旅程"}).json()
    approval = api.post(f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve", json={
        "approved_by": "tester", "spoken_confirmation": "我确认当前剧本", "guardian_approval": audience == "child"})
    assert approval.status_code == 200, approval.text
    result = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True},
                      headers={"Idempotency-Key": "authorization-test"})
    assert result.status_code == 201, result.text
    run = result.json()
    package = json.loads(Path(run["package_path"]).read_text())
    shot = {"source_excerpt": script["content"], "scene": "家里", "duration_seconds": 15,
            "entry_state": "坐着", "action": "讲述旅程", "exit_state": "微笑", "camera": "中景",
            "dialogue_or_narration": "旅程", "sound": "安静", "image_prompt": "坐着",
            "video_prompt": "老人讲述旅程", "reference_asset_ids": [], "transition": "scene_start"}
    plan = ShotPlan.model_validate({"summary": "用户已确认的拍摄安排", "shots": [shot] * (episode["target_seconds"] // 15)})
    payload = {"approved": True, "script_revision": package["approved_script"]["revision"],
               "production_package_sha256": package["package_sha256"],
               "plan": plan.model_dump(), "tasks": ShotPlanningService.tasks_for_plan(
                   plan, repo.get_episode(episode["id"]), package["approved_script"], [])}
    payload["plan_sha256"] = digest(payload)
    event = repo.append_run_event(run["id"], "shot_plan_approved", payload=payload)
    body = {"source_event_id": event.id, "expected_plan_sha256": payload["plan_sha256"],
            "expected_package_sha256": package["package_sha256"], "confirmed_run_budget_credits": 1000,
            "approved_by": "local-user", "confirmation": "我确认本集预计预算一千积分，按确认的分镜继续"}
    return api, run, body


def endpoint(run):
    return f"/v1/production-runs/{run['id']}/production-authorization"


def test_authorization_preserves_run_script_plan_and_requires_separate_task_cost(tmp_path):
    api, run, body = setup(tmp_path)
    repo = api.app.state.repository
    old_path = Path(run["package_path"])
    old_bytes = old_path.read_bytes()
    # Opening the frame pane creates a local preparation, not a paid attempt.
    repo.append_run_event(run["id"], "image_task_prepared", payload={"generation_performed": False})
    result = api.post(endpoint(run), json=body)
    assert result.status_code == 200, result.text
    approved = result.json()
    updated = repo.get_run(run["id"])
    assert updated.dry_run is False and updated.status == "waiting_for_approval"
    assert updated.estimated_budget_credits == 1000
    assert repo.get_episode(run["episode_id"]).status == "preproduction"
    assert old_path.read_bytes() == old_bytes
    package = json.loads(Path(updated.package_path).read_text())
    original = json.loads(old_bytes)
    assert {k: v for k, v in package.items() if k not in {"package_sha256", "production_policy"}} == {
        k: v for k, v in original.items() if k not in {"package_sha256", "production_policy"}}
    assert package["production_policy"]["paid_generation_approved"] is True
    payload = approved["payload"]
    assert payload["paid_approved"] is False and payload["generation_performed"] is False
    assert payload["production_package_sha256"] == package["package_sha256"]
    assert payload["plan"] == repo.get_run_event(body["source_event_id"]).payload["plan"]
    assert payload["tasks"] == repo.get_run_event(body["source_event_id"]).payload["tasks"]
    assert (Path(updated.package_path).parent / "qingshan-workspace/workspace-manifest.json").is_file()
    restarted = client(tmp_path)
    assert restarted.post(endpoint(run), json=body).json()["id"] == approved["id"]
    assert restarted.post(endpoint(run), json={**body, "confirmed_run_budget_credits": 2000}).status_code == 409
    with repo.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM production_runs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM remote_task_bindings").fetchone()[0] == 0
    assert not any(e.event_type in {"image_estimate_reserved", "video_estimate_reserved", "image_submit_intent"}
                   for e in repo.list_run_events(run["id"]))


@pytest.mark.parametrize("event", ["image_submit_intent", "image_submit_unconfirmed", "image_estimate_reserved",
                                      "video_task_prepared", "image_frame_reviewed", "unknown_future_effect"])
def test_existing_downstream_activity_cannot_be_reset(tmp_path, event):
    api, run, body = setup(tmp_path)
    api.app.state.repository.append_run_event(run["id"], event, payload={})
    assert api.post(endpoint(run), json=body).status_code == 409
    assert api.app.state.repository.get_run(run["id"]).dry_run is True


def test_exact_binding_guardian_and_native_confirmation_required(tmp_path):
    api, run, body = setup(tmp_path, "child")
    assert api.post(endpoint(run), json=body).status_code == 409
    body["guardian_approval"] = True
    assert api.post(endpoint(run), json={**body, "expected_plan_sha256": "0" * 64}).status_code == 409
    for change in ({"confirmation": " "}, {"approved_by": " "}, {"confirmed_run_budget_credits": 0},
                   {"confirmed_run_budget_credits": True}, {"guardian_approval": "true"}):
        assert api.post(endpoint(run), json={**body, **change}).status_code == 422
    assert api.post(endpoint(run), json=body, headers={"Origin": "https://example.com"}).status_code == 403
    assert api.post(endpoint(run), json=body).status_code == 200


def test_concurrent_identical_authorization_has_one_receipt(tmp_path):
    api, run, body = setup(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: api.post(endpoint(run), json=body), range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json()["id"] == results[1].json()["id"]


def test_failed_materialization_retains_original_then_reuses_snapshot(tmp_path, monkeypatch):
    api, run, body = setup(tmp_path)
    from nalu_runtime.qingshan_adapter import QingshanAdapter
    original = QingshanAdapter.preflight

    def fail(*args, **kwargs):
        raise ValueError("local preflight unavailable")

    monkeypatch.setattr(QingshanAdapter, "preflight", fail)
    assert api.post(endpoint(run), json=body).status_code == 409
    saved = api.app.state.repository.get_run(run["id"])
    assert saved.package_path == run["package_path"] and saved.dry_run
    monkeypatch.setattr(QingshanAdapter, "preflight", original)
    result = api.post(endpoint(run), json=body)
    assert result.status_code == 200, result.text


def test_local_frame_preparation_is_rebound_not_silently_reused(tmp_path):
    api, run, body = setup(tmp_path)
    repo = api.app.state.repository
    task_key = repo.get_run_event(body["source_event_id"]).payload["tasks"][0]["task_key"]
    frame_body = {"task_key": task_key, "approved_plan_event_id": body["source_event_id"],
                  "approved_plan_sha256": body["expected_plan_sha256"]}
    frames = f"/v1/production-runs/{run['id']}/image-task-preparations"
    old = api.post(frames, json=frame_body)
    assert old.status_code == 200, old.text
    authorization = api.post(endpoint(run), json=body)
    assert authorization.status_code == 200, authorization.text
    assert api.post(frames, json=frame_body).status_code == 409
    approved = authorization.json()
    new = api.post(frames, json={**frame_body, "approved_plan_event_id": approved["id"],
                                "approved_plan_sha256": approved["payload"]["plan_sha256"]})
    assert new.status_code == 200, new.text
    assert new.json()["id"] != old.json()["id"]
    assert new.json()["payload"]["production_package_sha256"] == approved["payload"]["production_package_sha256"]
    assert api.post(endpoint(run), json=body).json()["id"] == approved["id"]
