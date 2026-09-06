import json

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RunStatus
from nalu_runtime.repository import utc_now
from nalu_runtime.video_preparation import digest


@pytest.mark.parametrize("case", ["ok", "duration", "source", "asset", "authority", "http_failure", "continuity",
                                  "continuous_ok", "blank", "package_changed"])
def test_approved_script_to_durable_shot_plan(tmp_path, case):
    calls = []
    shot = {"source_excerpt": "外婆看海。", "scene": "海边", "duration_seconds": 12,
            "entry_state": "外婆站在岸边", "action": "抬头看海", "exit_state": "面朝海面",
            "camera": "中景缓推", "dialogue_or_narration": "我又回来了。", "sound": "连续海浪声",
            "image_prompt": "横向构图，外婆站在岸边，尚未抬头。", "video_prompt": "外婆抬头看海，保持人物和光线一致。",
            "reference_asset_ids": [], "transition": "scene_start"}
    if case == "duration":
        shot["duration_seconds"] = 11
    if case == "source":
        shot["source_excerpt"] = "不存在的原文"
    if case == "asset":
        shot["reference_asset_ids"] = ["invented-photo"]
    if case == "authority":
        shot["qa_passed"] = True
    if case == "continuity":
        shot["transition"] = "continuous"
    if case == "blank":
        shot["image_prompt"] = "   "
    second_shot = dict(shot)
    if case == "continuous_ok":
        second_shot.update(transition="continuous", entry_state=shot["exit_state"])
    def serve(request):
        calls.append(request)
        body = json.loads(request.content)
        context = json.loads(body["messages"][1]["content"])
        assert context["approved_script"] == "外婆看海。"
        assert "private-unapproved-memory" not in request.content.decode()
        if case == "package_changed":
            path.write_text("broken package")
        return httpx.Response(401 if case == "http_failure" else 200, json={
            "id": "synthetic-planner-task", "model": "fixture-model", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"summary": "回到海边", "shots": [shot, second_shot]})}}]})
    db_path = tmp_path / "planner.sqlite3"
    api = TestClient(create_app(db_path, tmp_path / "data", writer_http_transport=httpx.MockTransport(serve)))
    project = api.post("/v1/projects", json={"title": "合成分镜测试"}).json()
    season = api.post(f"/v1/projects/{project['id']}/seasons", json={"title": "第一季", "season_number": 1}).json()
    episode_response = api.post(f"/v1/seasons/{season['id']}/episodes", json={"title": "海边", "episode_number": 1, "target_seconds": 24})
    assert episode_response.status_code == 201, episode_response.text
    episode = episode_response.json()
    api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": "外婆看海。", "source_transcript": "外婆看海。",
                                                          "summary_for_voice_review": "海边"})
    script = api.post(f"/v1/episodes/{episode['id']}/scripts/1/approve", json={"approved_by": "QA"}).json()
    package = {"project": {**project, "project_bible": {"private": "private-unapproved-memory"}},
               "episode": episode, "approved_script": script, "inherited_assets": []}
    package["package_sha256"] = digest(package)
    path = tmp_path / "package.json"
    path.write_text(json.dumps(package))
    now = utc_now()
    run = ProductionRun(id="run_planner", project_id=project["id"], season_id=season["id"], episode_id=episode["id"],
                        status=RunStatus.PREFLIGHT, dry_run=True, requested_model="seedance-2.0-pro", estimated_budget_credits=None,
                        package_path=str(path), created_at=now, updated_at=now)
    api.app.state.repository.save_run(run)
    endpoint = f"/v1/production-runs/{run.id}/shot-plans"
    headers = {"X-Nalu-Writer-Key": "synthetic-key"}
    assert api.post(endpoint, json={"model": "fixture-model"}).status_code == 403
    first = api.post(endpoint, json={"model": "fixture-model"}, headers=headers)
    if case in {"ok", "continuous_ok"}:
        assert first.status_code == 200, first.text
        assert first.json()["payload"]["approved"] is False
        assert first.json()["payload"]["frames_generated"] is False
        assert [task["task_key"] for task in first.json()["payload"]["tasks"]] == ["E01-U01", "E01-U02"]
        assert first.json()["payload"]["tasks"][-1]["end_seconds"] == 24
        assert "synthetic-key" not in first.text
        if case == "continuous_ok":
            assert first.json()["payload"]["tasks"][1]["previous_task_key"] == "E01-U01"
            assert first.json()["payload"]["tasks"][1]["previous_final_frame_required"] is True
    else:
        assert first.status_code in {409, 502}, first.text
    restarted = TestClient(create_app(db_path, tmp_path / "data", writer_http_transport=httpx.MockTransport(serve)))
    second = restarted.post(endpoint, json={"model": "fixture-model"}, headers=headers)
    assert len(calls) == 1
    if case in {"ok", "continuous_ok"}:
        assert second.json()["id"] == first.json()["id"]
        source = first.json()
        current_url = endpoint + "/current"
        assert restarted.get(current_url).json()["id"] == source["id"]
        review_url = endpoint + f"/{source['id']}/review"
        plan = source["payload"]["plan"]
        plan["shots"][0]["camera"] = "老人提出修改：从手部特写开始，慢慢拉远"
        edit = {"expected_plan_sha256": source["payload"]["plan_sha256"], "action": "revise", "plan": plan,
                "reviewed_by": "QA", "confirmation": "先改第一个镜头"}
        invalid = json.loads(json.dumps(edit))
        invalid["plan"]["shots"][0]["source_excerpt"] = "不是本集剧本的内容"
        assert restarted.post(review_url, json=invalid).status_code == 409
        modified = restarted.post(review_url, json=edit)
        assert modified.status_code == 200, modified.text
        modified = modified.json()
        assert modified["payload"]["approved"] is False
        assert modified["payload"]["source_event_id"] == source["id"]
        assert restarted.post(review_url, json=edit).json()["id"] == modified["id"]
        confirm = {"expected_plan_sha256": modified["payload"]["plan_sha256"], "action": "approve",
                   "reviewed_by": "QA", "confirmation": "就按修改后的分镜继续"}
        confirm_url = endpoint + f"/{modified['id']}/review"
        assert restarted.post(confirm_url, json={**confirm, "plan": plan}).status_code == 422
        approved = restarted.post(confirm_url, json=confirm)
        assert approved.status_code == 200, approved.text
        approved = approved.json()
        assert approved["payload"]["approved"] is True
        assert approved["payload"]["paid_approved"] is False
        assert approved["payload"]["tasks"][0]["state"] == "awaiting_entry_frame"
        assert approved["payload"]["plan"]["shots"][0]["camera"] == plan["shots"][0]["camera"]
        assert restarted.post(review_url, json=edit).status_code == 409
        reopened = TestClient(create_app(db_path, tmp_path / "data", writer_http_transport=httpx.MockTransport(serve)))
        assert reopened.get(current_url).json()["id"] == approved["id"]
        assert reopened.post(confirm_url, json=confirm).json()["id"] == approved["id"]
        for kind in ("video_task_prepared", "image_submit_intent", "image_submit_unconfirmed", "image_task_submitted"):
            reopened.app.state.repository.append_run_event_once(run.id, kind, dedupe_key="test_id",
                dedupe_value="synthetic-downstream", message="Synthetic downstream lock", payload={"test_id": "synthetic-downstream"})
            assert reopened.post(endpoint + f"/{approved['id']}/review", json={
                **edit, "expected_plan_sha256": approved["payload"]["plan_sha256"]}).status_code == 409
            assert reopened.get(current_url).json()["id"] == approved["id"]
            # Remove only this synthetic fixture so each downstream state is checked independently.
            with reopened.app.state.repository.db.connect() as db:
                db.execute("DELETE FROM run_events WHERE run_id=? AND event_type=?", (run.id, kind))
        assert len(calls) == 1  # All local review/edit/confirmation operations are model-free.
    else:
        assert second.status_code in {409, 502}
