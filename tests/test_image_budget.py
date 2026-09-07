import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RunStatus
from nalu_runtime.repository import utc_now
from nalu_runtime.video_preparation import digest


def prepared_image(tmp_path):
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    repo = api.app.state.repository
    project = api.post("/v1/projects", json={"title": "合成图像预算测试"}).json()
    season = api.post(f"/v1/projects/{project['id']}/seasons", json={"title": "第一季", "season_number": 1}).json()
    episode = api.post(f"/v1/seasons/{season['id']}/episodes", json={"title": "海边", "episode_number": 1, "target_seconds": 15}).json()
    api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": "外婆看海。", "source_transcript": "外婆看海。",
        "summary_for_voice_review": "海边"})
    script = api.post(f"/v1/episodes/{episode['id']}/scripts/1/approve", json={"approved_by": "QA"}).json()
    package = {"project": project, "episode": episode, "approved_script": script, "inherited_assets": []}
    package["package_sha256"] = digest(package)
    path = tmp_path / "package.json"
    path.write_text(json.dumps(package))
    now = utc_now()
    run = ProductionRun(id="run_image_budget", project_id=project["id"], season_id=season["id"], episode_id=episode["id"],
        status=RunStatus.WAITING_FOR_APPROVAL, dry_run=False, requested_model="seedance-2.0-pro", estimated_budget_credits=100,
        package_path=str(path), created_at=now, updated_at=now)
    repo.save_run(run)
    shot = {"source_excerpt": "外婆看海。", "scene": "海边", "duration_seconds": 15, "entry_state": "外婆站在岸边",
        "action": "抬头看海", "exit_state": "面朝海面", "camera": "中景", "dialogue_or_narration": "我又回来了。",
        "sound": "海浪", "image_prompt": "外婆尚未抬头", "video_prompt": "外婆抬头看海",
        "reference_asset_ids": [], "transition": "scene_start"}
    plan = {"plan": {"summary": "海边", "shots": [shot]}, "approved": True,
        "production_package_sha256": package["package_sha256"]}
    plan["plan_sha256"] = digest(plan)
    event = repo.append_run_event_once(run.id, "shot_plan_approved", dedupe_key="plan_sha256",
        dedupe_value=plan["plan_sha256"], message="Synthetic confirmed plan, not provider output", payload=plan)
    prepared = api.post(f"/v1/production-runs/{run.id}/image-task-preparations", json={"task_key": "E01-U01",
        "approved_plan_event_id": event.id, "approved_plan_sha256": plan["plan_sha256"]})
    assert prepared.status_code == 200, prepared.text
    return api, run, prepared.json()


def reserve_synthetic_video(api, run, credits):
    # Isolates the shared estimate envelope, not production contract acceptance.
    record = {"task_key": "E01-U01", "request": {"synthetic": True}, "request_sha256": digest({"synthetic": True}),
              "production_package_sha256": "0" * 64}
    record["preparation_sha256"] = digest(record)
    event = api.app.state.repository.append_run_event(run.id, "video_task_prepared", payload=record)
    return api.post(f"/v1/production-runs/{run.id}/video-task-preparations/{event.id}/estimate-approvals", json={
        "preparation_sha256": record["preparation_sha256"], "estimated_credits": credits,
        "confirmed_run_budget_credits": 100, "approved_by": "QA", "confirmation": "Synthetic estimate only"})


@pytest.mark.parametrize("case", ["ok", "child", "guardian", "cancelled", "stale", "changed_plan", "over_budget",
                                  "video_first", "image_first", "exact_total", "concurrent", "changed_estimate", "reduced_budget"])
def test_image_estimates_bind_current_frame_and_share_video_envelope(tmp_path, case):
    api, run, prepared = prepared_image(tmp_path)
    repo = api.app.state.repository
    approval = {"preparation_sha256": prepared["payload"]["preparation_sha256"], "estimated_credits": 30,
        "confirmed_run_budget_credits": 100, "approved_by": "QA", "confirmation": "Synthetic estimate only",
        "guardian_approval": case == "guardian"}
    with repo.db.connect() as db:
        if case in {"child", "guardian"}:
            db.execute("UPDATE projects SET audience_mode='child' WHERE id=?", (run.project_id,))
        if case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
    if case == "stale":
        approval["preparation_sha256"] = "0" * 64
    if case == "over_budget":
        approval["estimated_credits"] = 101
    if case == "changed_plan":
        repo.append_run_event(run.id, "shot_plan_revised", payload={"synthetic": True})
    if case == "video_first":
        assert reserve_synthetic_video(api, run, 80).status_code == 200
    endpoint = f"/v1/production-runs/{run.id}/image-task-preparations/{prepared['id']}/estimate-approvals"
    assert api.post(endpoint, json=approval, headers={"Origin": "https://example.org"}).status_code == 403
    if case == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: api.post(endpoint, json=approval), range(2)))
        assert results[0].json() == results[1].json()
        result = results[0]
    else:
        result = api.post(endpoint, json=approval)
    if case in {"child", "cancelled", "stale", "changed_plan", "over_budget", "video_first"}:
        assert result.status_code == 409, result.text
        assert not any(e.event_type == "image_estimate_reserved" for e in repo.list_run_events(run.id))
        return
    assert result.status_code == 200, result.text
    record = result.json()["payload"]
    assert record["request_sha256"] == prepared["payload"]["request_sha256"]
    assert record["provider_price_verified"] is False and record["upstream_image_contract_verified"] is False
    assert record["generation_performed"] is False and record["provider_charge_cap_guaranteed"] is False
    reopened = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    assert reopened.post(endpoint, json=approval).json() == result.json()
    if case == "changed_estimate":
        assert api.post(endpoint, json={**approval, "estimated_credits": 31}).status_code == 409
    if case in {"image_first", "exact_total", "reduced_budget"}:
        video = reserve_synthetic_video(api, run, 80 if case == "image_first" else 70)
        assert video.status_code == (409 if case == "image_first" else 200), video.text
        if case == "reduced_budget":
            with repo.db.connect() as db:
                db.execute("UPDATE production_runs SET estimated_budget_credits=50 WHERE id=?", (run.id,))
            assert api.post(endpoint, json={**approval, "confirmed_run_budget_credits": 50}).status_code == 409
            reservation = video.json()["payload"]
            video_endpoint = f"/v1/production-runs/{run.id}/video-task-preparations/{reservation['preparation_id']}/estimate-approvals"
            assert api.post(video_endpoint, json={"preparation_sha256": reservation["preparation_sha256"],
                "estimated_credits": 70, "confirmed_run_budget_credits": 50,
                "approved_by": "QA", "confirmation": "Synthetic changed budget"}).status_code == 409
