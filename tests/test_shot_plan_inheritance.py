import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun
from nalu_runtime.qingshan_adapter import QingshanAdapterError
from nalu_runtime.shot_planning import ShotPlan
from nalu_runtime.video_preparation import digest


@pytest.mark.parametrize("case", ["ok", "script", "assets", "policy", "continuity", "stale_library",
                                  "stale_plan", "tampered", "prepared", "target_plan", "origin", "hash",
                                  "refresh", "refresh_recover", "refresh_prepared", "refresh_stale"])
def test_library_snapshot_inherits_only_reviewed_creative_work(tmp_path, monkeypatch, case):
    db_path = tmp_path / "nalu.sqlite3"
    api = TestClient(create_app(db_path, tmp_path / "data"))
    repo = api.app.state.repository
    project = api.post("/v1/projects", json={"title": "本地继承测试"}).json()
    season = api.post(f"/v1/projects/{project['id']}/seasons", json={"title": "第一季", "season_number": 1}).json()
    episode = api.post(f"/v1/seasons/{season['id']}/episodes", json={"title": "回忆", "episode_number": 1, "target_seconds": 24}).json()
    api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": "外婆看海。", "source_transcript": "外婆看海。",
        "summary_for_voice_review": "外婆看海。"})
    script = api.post(f"/v1/episodes/{episode['id']}/scripts/1/approve", json={"approved_by": "QA"}).json()
    old = {"project": project, "episode": episode, "approved_script": script, "inherited_assets": [], "resolved_library": []}
    old["package_sha256"] = digest(old)
    new = deepcopy(old)
    entity = api.post(f"/v1/projects/{project['id']}/library-entities", json={"kind": "character", "name": "外婆",
        "description": "外婆穿蓝色外套", "source_channel": "voice", "change_summary": "讲述人物"})
    assert entity.status_code == 201, entity.text
    entity_id = entity.json()["id"]
    # Confirm through the public API, never invent a confirmed catalog fixture.
    confirmation = api.post(f"/v1/library-entities/{entity_id}/confirmations", json={"reviewed_revision": 1,
        "confirmed_by": "QA", "review_channel": "voice", "spoken_confirmation": "我确认人物描述正确"})
    assert confirmation.status_code == 201, confirmation.text
    new["resolved_library"] = repo.resolved_project_library(project["id"])
    if case == "script":
        new["approved_script"]["content"] = "剧本已改变"
    if case == "assets":
        new["inherited_assets"] = [{"id": "unexpected"}]
    if case == "policy":
        new["production_policy"] = {"paid_generation_approved": True}
    if case == "continuity":
        new["continuity"] = {"changed": True}
    if case == "stale_library":
        new["resolved_library"] = []
    new["package_sha256"] = digest({k: v for k, v in new.items() if k != "package_sha256"})
    paths = []
    for identity, package, created in [("source", old, "2026-09-01T00:00:00Z"), ("target", new, "2026-09-02T00:00:00Z")]:
        if case.startswith("refresh") and identity == "target":
            continue
        path = tmp_path / f"{identity}.json"
        path.write_text(json.dumps(package))
        paths.append(path)
        repo.save_run(ProductionRun(id=identity, project_id=project["id"], season_id=season["id"], episode_id=episode["id"],
            status="preflight", dry_run=True, requested_model="seedance-2.0-pro", estimated_budget_credits=None,
            package_path=str(path), created_at=created, updated_at=created))
    shot = {"source_excerpt": "外婆看海。", "scene": "海边", "duration_seconds": 12,
            "entry_state": "站在岸边", "action": "抬头", "exit_state": "面向海面", "camera": "中景",
            "dialogue_or_narration": "我回来了", "sound": "海浪", "image_prompt": "站在岸边",
            "video_prompt": "外婆抬头看海", "reference_asset_ids": [], "transition": "scene_start"}
    plan = ShotPlan.model_validate({"summary": "回忆", "shots": [shot, shot]}).model_dump()
    record = {"plan": plan, "approved": True, "production_package_sha256": old["package_sha256"], "script_revision": 1,
              "reviewed_by": "QA", "confirmation": "就按这个拍"}
    record["plan_sha256"] = digest(record)
    if case == "tampered":
        record["confirmation"] = "被篡改"
    source = repo.append_run_event("source", "shot_plan_approved", payload=record)
    if case == "stale_plan":
        repo.append_run_event("source", "shot_plan_revised", payload={})
    if case == "prepared":
        repo.append_run_event("source", "image_task_prepared", payload={})
    if case == "target_plan":
        repo.append_run_event("target", "shot_plan_drafted", payload={})
    original_bytes = [path.read_bytes() for path in paths]
    if case.startswith("refresh"):
        production = api.app.state.production
        calls = []
        def preflight(path, workspace):
            calls.append(path)
            assert json.loads(path.read_text())["resolved_library"] == new["resolved_library"]
            if case == "refresh_recover" and len(calls) == 1:
                raise QingshanAdapterError("synthetic interrupted preflight")
        monkeypatch.setattr(production.adapter, "materialize_workspace", lambda path: path.parent)
        monkeypatch.setattr(production.adapter, "preflight", preflight)
        body = {"source_event_id": source.id, "expected_plan_sha256": record["plan_sha256"],
                "expected_package_sha256": old["package_sha256"],
                "expected_library_sha256": digest(new["resolved_library"]) if case != "refresh_stale" else "0" * 64}
        endpoint = "/v1/production-runs/source/library-snapshot-refresh"
        if case == "refresh_prepared":
            repo.append_run_event("source", "image_task_prepared", payload={})
        if case == "refresh_recover":
            assert api.post(endpoint, json=body).status_code == 409
            assert repo.get_run("source").package_path == str(paths[0])
            assert len(repo.list_run_events("source")) == 1
        if case == "refresh":
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: api.post(endpoint, json=body), range(2)))
            assert all(result.status_code == 200 for result in results)
            assert results[0].json()["id"] == results[1].json()["id"]
            response = results[0]
        else:
            response = api.post(endpoint, json=body)
        if case in {"refresh_prepared", "refresh_stale"}:
            assert response.status_code == 409, response.text
            assert calls == []
        else:
            assert response.status_code == 200, response.text
            assert response.json()["payload"]["plan"] == plan
            assert response.json()["payload"]["paid_approved"] is False
            assert repo.get_run("source").package_path != str(paths[0])
            from pathlib import Path
            refreshed = json.loads(Path(repo.get_run("source").package_path).read_text())
            assert refreshed == new
            restarted = TestClient(create_app(db_path, tmp_path / "data"))
            # Successful replay must not need the adapter, a key or another preflight.
            monkeypatch.setattr(restarted.app.state.production.adapter, "preflight",
                                lambda *_: pytest.fail("replay must not rerun preflight"))
            assert restarted.post(endpoint, json=body).json()["id"] == response.json()["id"]
            assert len(set(calls)) == 1
            assert len(repo.list_run_events("source")) == 2
        assert [path.read_bytes() for path in paths] == original_bytes
        with repo.db.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM production_runs").fetchone()[0] == 1
        return
    body = {"source_run_id": "source", "source_event_id": source.id, "expected_plan_sha256": record["plan_sha256"],
            "expected_package_sha256": new["package_sha256"] if case != "hash" else "0" * 64}
    endpoint = "/v1/production-runs/target/shot-plan-inheritance"
    if case == "ok":
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: api.post(endpoint, json=body), range(2)))
        assert all(result.status_code == 200 for result in responses)
        assert responses[0].json()["id"] == responses[1].json()["id"]
        response = responses[0]
    else:
        response = api.post(endpoint, json=body, headers={"Origin": "https://untrusted.test"} if case == "origin" else {})
    if case == "ok":
        assert response.status_code == 200, response.text
        payload = response.json()["payload"]
        assert payload["plan"] == plan
        assert payload["approved"] is True and payload["paid_approved"] is False
        assert payload["generation_performed"] is False
        assert payload["tasks"][0]["task_key"] == "E01-U01"
        assert payload["source_event_id"] == source.id
        restarted = TestClient(create_app(db_path, tmp_path / "data"))
        assert restarted.post(endpoint, json=body).json()["id"] == response.json()["id"]
        assert len(repo.list_run_events("target")) == 1
    else:
        assert response.status_code == (403 if case == "origin" else 409), response.text
    assert [path.read_bytes() for path in paths] == original_bytes
    with repo.db.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM production_runs").fetchone()[0] == 2
