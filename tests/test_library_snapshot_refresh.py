import json
from pathlib import Path

from nalu_runtime.shot_planning import ShotPlan
from nalu_runtime.video_preparation import digest
from test_project_library import client, confirm, create_and_approve_script, library_payload


def test_library_refresh_uses_real_qingshan_preflight_without_resetting_episode(tmp_path):
    api = client(tmp_path)
    repo = api.app.state.repository
    planning = api.post("/v1/project-plans", json={"project": {"title": "讲述到制作", "planned_episode_count": 1}}).json()
    episode = planning["episodes"][0]
    create_and_approve_script(api, episode["id"])
    started = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True},
                       headers={"Idempotency-Key": "local-refresh-fixture"})
    assert started.status_code == 201, started.text
    run = started.json()
    original = Path(run["package_path"])
    original_bytes = original.read_bytes()
    package = json.loads(original_bytes)
    script = package["approved_script"]
    duration = episode["target_seconds"]
    assert duration % 15 == 0
    shot = {"source_excerpt": script["content"], "scene": "家里", "duration_seconds": 15,
            "entry_state": "坐着", "action": "讲述旅程", "exit_state": "微笑", "camera": "中景",
            "dialogue_or_narration": "旅程", "sound": "安静", "image_prompt": "坐着",
            "video_prompt": "老人讲述旅程", "reference_asset_ids": [], "transition": "scene_start"}
    plan = ShotPlan.model_validate({"summary": "已确认旅程", "shots": [shot] * (duration // 15)})
    payload = {"plan": plan.model_dump(), "tasks": [], "approved": True, "script_revision": script["revision"],
               "production_package_sha256": package["package_sha256"], "reviewed_by": "local-user", "confirmation": "我确认按这个拍"}
    payload["plan_sha256"] = digest(payload)
    event = repo.append_run_event(run["id"], "shot_plan_approved", payload=payload)
    entity = api.post(f"/v1/projects/{run['project_id']}/library-entities", json=library_payload("character", "林叔")).json()
    confirm(api, entity["id"], 1)
    body = {"source_event_id": event.id, "expected_plan_sha256": payload["plan_sha256"],
            "expected_package_sha256": package["package_sha256"],
            "expected_library_sha256": digest(repo.resolved_project_library(run["project_id"]))}
    before_status = repo.get_episode(episode["id"]).status
    preview = api.get(f"/v1/production-runs/{run['id']}/library-snapshot-refresh")
    assert preview.status_code == 200, preview.text
    assert preview.json()["refresh_required"] is True
    assert preview.json()["request"] == body
    response = api.post(f"/v1/production-runs/{run['id']}/library-snapshot-refresh", json=body)
    assert response.status_code == 200, response.text
    updated = repo.get_run(run["id"])
    target = Path(updated.package_path)
    assert target != original and original.read_bytes() == original_bytes
    assert repo.get_episode(episode["id"]).status == before_status == "preproduction"
    assert response.json()["payload"]["plan"] == plan.model_dump()
    assert len(response.json()["payload"]["tasks"]) == duration // 15
    assert api.get(f"/v1/production-runs/{run['id']}/library-snapshot-refresh").json()["refresh_required"] is False
    manifest = json.loads((target.parent / "qingshan-workspace/workspace-manifest.json").read_text())
    assert manifest["production_package_sha256"] == json.loads(target.read_text())["package_sha256"]
    assert (original.parent / "qingshan-workspace").is_dir()
    with repo.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM production_runs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM remote_task_bindings").fetchone()[0] == 0
