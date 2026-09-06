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
    else:
        assert second.status_code in {409, 502}
