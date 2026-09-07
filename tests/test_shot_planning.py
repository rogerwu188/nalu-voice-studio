import json

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RunStatus
from nalu_runtime.repository import ConflictError, utc_now
from nalu_runtime.video_preparation import VideoPreparationRequest, VideoPreparationService, digest
from test_director_draft import director_fixture


@pytest.mark.parametrize("case", ["ok", "duration", "source", "asset", "authority", "http_failure", "continuity",
                                  "continuous_ok", "blank", "package_changed", "missing_designs", "missing_director", "director_scope",
                                  "refresh", "refresh_rewrite", "refresh_failure", "refresh_race", "refresh_recover"])
def test_approved_script_to_durable_shot_plan(tmp_path, monkeypatch, case):
    calls = []
    shot = {"source_excerpt": "外婆看海。", "scene": "海边", "duration_seconds": 12,
            "entry_state": "外婆站在岸边", "action": "抬头看海", "exit_state": "面朝海面",
            "camera": "中景缓推", "dialogue_or_narration": "我又回来了。", "sound": "连续海浪声",
            "image_prompt": "横向构图，外婆站在岸边，尚未抬头。", "video_prompt": "外婆抬头看海，保持人物和光线一致。",
            "reference_asset_ids": [], "visual_asset_keys": ["grandma", "beach"], "transition": "scene_start",
            "director": director_fixture()}
    designs = [
        {"key": "grandma", "kind": "character_image", "name": "外婆", "description": "外貌和服装待确认",
         "source_excerpt": "外婆看海。", "existing_asset_id": None},
        {"key": "beach", "kind": "scene_reference", "name": "海边", "description": "空旷的岸边，时段待确认",
         "source_excerpt": "外婆看海。", "existing_asset_id": None},
    ]
    if case == "missing_designs":
        designs = []
    if case == "missing_director":
        shot["director"] = None
    if case == "director_scope":
        shot["director"]["visible_character_counts"] = {"invented-person": 1}
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
        if "current_plan" in context:
            enriched = context["current_plan"]
            for item in enriched["shots"]:
                if item["director"] is None:
                    item["director"] = director_fixture()
            if case == "refresh_rewrite":
                enriched["shots"][0]["camera"] = "AI擅自覆盖用户选择"
            if case == "refresh_race":
                race_plan = json.loads(json.dumps(modified["payload"]["plan"]))
                race_plan["shots"][0]["camera"] = "用户在等待时又改了机位"
                assert restarted.post(endpoint + f"/{modified['id']}/review", json={
                    **edit, "plan": race_plan, "expected_plan_sha256": modified["payload"]["plan_sha256"]
                }).status_code == 200
            return httpx.Response(401 if case == "refresh_failure" else 200, json={
                "id": "synthetic-director-refresh", "model": "fixture-model", "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(enriched)}}]})
        if case == "package_changed":
            path.write_text("broken package")
        return httpx.Response(401 if case == "http_failure" else 200, json={
            "id": "synthetic-planner-task", "model": "fixture-model", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"summary": "回到海边", "shots": [shot, second_shot], "visual_assets": designs})}}]})
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
               "episode": episode, "approved_script": script, "inherited_assets": [],
               "resolved_library": [{"entity_id": "person-grandma", "kind": "character", "stable_name": "外婆",
                   "confirmed_revision": 1, "revision": {"entity_id": "person-grandma", "revision": 1,
                       "name": "外婆", "source_asset_ids": []}}]}
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
    if case in {"ok", "continuous_ok"} or case.startswith("refresh"):
        assert first.status_code == 200, first.text
        assert first.json()["payload"]["approved"] is False
        assert first.json()["payload"]["frames_generated"] is False
        assert [task["task_key"] for task in first.json()["payload"]["tasks"]] == ["E01-U01", "E01-U02"]
        assert first.json()["payload"]["tasks"][-1]["end_seconds"] == 24
        assert first.json()["payload"]["tasks"][0]["reference_designs_to_create"] == ["grandma", "beach"]
        assert "synthetic-key" not in first.text
        if case == "continuous_ok":
            assert first.json()["payload"]["tasks"][1]["previous_task_key"] == "E01-U01"
            assert first.json()["payload"]["tasks"][1]["previous_final_frame_required"] is True
    else:
        assert first.status_code in {409, 502}, first.text
    restarted = TestClient(create_app(db_path, tmp_path / "data", writer_http_transport=httpx.MockTransport(serve)))
    second = restarted.post(endpoint, json={"model": "fixture-model"}, headers=headers)
    assert len(calls) == 1
    if case in {"ok", "continuous_ok"} or case.startswith("refresh"):
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
        lost_designs = json.loads(json.dumps(edit))
        lost_designs["plan"].pop("visual_assets")
        for item in lost_designs["plan"]["shots"]:
            item.pop("visual_asset_keys")
        assert restarted.post(review_url, json=lost_designs).status_code == 409
        modified = restarted.post(review_url, json=edit)
        assert modified.status_code == 200, modified.text
        modified = modified.json()
        assert modified["payload"]["approved"] is False
        assert modified["payload"]["source_event_id"] == source["id"]
        assert restarted.post(review_url, json=edit).json()["id"] == modified["id"]
        assert restarted.post(endpoint + f"/{modified['id']}/character-cards", json={
            "expected_plan_sha256": modified["payload"]["plan_sha256"]}).status_code == 409
        if case.startswith("refresh"):
            refresh_url = endpoint + f"/{modified['id']}/director-refresh"
            refresh_body = {"model": "fixture-model", "expected_plan_sha256": modified["payload"]["plan_sha256"]}
            assert restarted.post(refresh_url, json=refresh_body).status_code == 403
            repo = restarted.app.state.repository
            repo.append_run_event_once(run.id, "image_submit_intent", dedupe_key="test_id",
                dedupe_value="synthetic-refresh-lock", message="Synthetic lock", payload={"test_id": "synthetic-refresh-lock"})
            assert restarted.post(refresh_url, json=refresh_body, headers=headers).status_code == 409
            assert len(calls) == 1
            with repo.db.connect() as db:
                db.execute("DELETE FROM run_events WHERE run_id=? AND event_type='image_submit_intent'", (run.id,))
            if case == "refresh_recover":
                from nalu_runtime.shot_review import ShotReviewService
                original_review = ShotReviewService.review
                def interrupted_save(*args, **kwargs):
                    raise ConflictError("synthetic interruption after durable writer result")
                monkeypatch.setattr(ShotReviewService, "review", interrupted_save)
                assert restarted.post(refresh_url, json=refresh_body, headers=headers).status_code == 409
                monkeypatch.setattr(ShotReviewService, "review", original_review)
            result = restarted.post(refresh_url, json=refresh_body, headers=headers)
            reopened = TestClient(create_app(db_path, tmp_path / "data", writer_http_transport=httpx.MockTransport(serve)))
            replay = reopened.post(refresh_url, json=refresh_body, headers=headers)
            assert len(calls) == 2  # One initial plan, one enrichment; no repeat after restart/failure.
            if case in {"refresh", "refresh_recover"}:
                assert result.status_code == 200, result.text
                assert replay.json()["id"] == result.json()["id"]
                refreshed = result.json()["payload"]
                assert refreshed["plan"]["shots"][0]["camera"] == plan["shots"][0]["camera"]
                assert refreshed["plan"]["shots"][0]["director"] is not None
                assert refreshed["approved"] is False and refreshed["paid_approved"] is False
                assert refreshed["director_derivation"]["response_id"] == "synthetic-director-refresh"
            else:
                assert result.status_code in {409, 502}, result.text
                assert replay.status_code in {409, 502}, replay.text
                current = reopened.get(current_url).json()
                assert current["payload"]["plan"]["shots"][0]["director"] is None
                if case == "refresh_race":
                    assert current["payload"]["plan"]["shots"][0]["camera"] == "用户在等待时又改了机位"
                else:
                    assert current["id"] == modified["id"]
            assert reopened.post(refresh_url, json={**refresh_body, "model": "different-model"}, headers=headers).status_code == 409
            assert len(calls) == 2
            return
        confirm = {"expected_plan_sha256": modified["payload"]["plan_sha256"], "action": "approve",
                   "reviewed_by": "QA", "confirmation": "就按修改后的分镜继续"}
        confirm_url = endpoint + f"/{modified['id']}/review"
        assert restarted.post(confirm_url, json={**confirm, "plan": plan}).status_code == 422
        approved = restarted.post(confirm_url, json=confirm)
        assert approved.status_code == 200, approved.text
        approved = approved.json()
        assert approved["payload"]["approved"] is True
        assert approved["payload"]["plan"]["visual_assets"] == designs
        assert approved["payload"]["paid_approved"] is False
        assert approved["payload"]["tasks"][0]["state"] == "awaiting_entry_frame"
        assert approved["payload"]["plan"]["shots"][0]["camera"] == plan["shots"][0]["camera"]
        assert approved["payload"]["plan"]["shots"][0]["director"] is None  # Camera edit invalidates stale technical choices.
        assert restarted.post(review_url, json=edit).status_code == 409
        reopened = TestClient(create_app(db_path, tmp_path / "data", writer_http_transport=httpx.MockTransport(serve)))
        assert reopened.get(current_url).json()["id"] == approved["id"]
        assert reopened.post(confirm_url, json=confirm).json()["id"] == approved["id"]
        cards_url = endpoint + f"/{approved['id']}/character-cards"
        if case == "continuous_ok":
            existing_person = reopened.post(f"/v1/projects/{run.project_id}/library-entities", json={
                "kind": "character", "name": "外婆", "description": "用户原来讲过的家庭事实，不能覆盖",
                "source_channel": "voice", "change_summary": "合成测试的既有人物"})
            assert existing_person.status_code == 201, existing_person.text
        package_before = path.read_bytes()
        cards_request = {"expected_plan_sha256": approved["payload"]["plan_sha256"]}
        assert reopened.post(cards_url, json={"expected_plan_sha256": "0" * 64}).status_code == 409
        cards = reopened.post(cards_url, json=cards_request)
        assert cards.status_code == 200, cards.text
        assert reopened.post(cards_url, json=cards_request).json()["id"] == cards.json()["id"]
        card_payload = cards.json()["payload"]
        assert card_payload["characters_auto_confirmed"] is False
        assert ("沿用" if case == "continuous_ok" else "草稿") in card_payload["readback"]
        assert len(card_payload["bindings"]) == 1
        entity = reopened.app.state.repository.get_library_entity(card_payload["bindings"][0]["entity_id"])
        assert entity.current.name == "外婆" and entity.confirmed_revision is None
        if case == "continuous_ok":
            assert entity.id == existing_person.json()["id"]
            assert entity.current.description == "用户原来讲过的家庭事实，不能覆盖"
        assert len(reopened.app.state.repository.list_library_entities(run.project_id)) == 1
        assert path.read_bytes() == package_before
        # The real preparation path derives technical fields from the exact
        # approved shot instead of asking the native user to build a contract.
        incoming = VideoPreparationRequest(task_key="E01-U02", request={
            "prompt": plan["shots"][1]["video_prompt"], "duration_seconds": 12},
            approved_plan_event_id=approved["id"], approved_plan_sha256=approved["payload"]["plan_sha256"])
        preparation_service = VideoPreparationService(reopened.app.state.repository)
        if case == "continuous_ok":
            with pytest.raises(ConflictError, match="preceding accepted tail"):
                preparation_service._plan_binding(run.id, incoming, package["package_sha256"], package)
            # This test exercises plan/director compilation only. Actual tail
            # validation is covered by the two-shot image/video integration test.
            incoming.approved_tail_id = "synthetic-plan-only-tail"
        binding = preparation_service._plan_binding(run.id, incoming, package["package_sha256"], package)
        assert binding["approved_shot_index"] == 1
        assert incoming.request["camera_plan"] == plan["shots"][1]["director"]["camera"]
        assert incoming.request["camera_authority"]["selection_mode"] == "LOCKED"
        assert incoming.request["provider_scope_projection"]["visible_character_ids"] == ["person-grandma"]
        assert "opening_anchor" not in incoming.request
        incoming.request["camera_plan"]["camera_side"] = "偷偷换了机位"
        with pytest.raises(ConflictError):
            preparation_service._plan_binding(run.id, incoming, package["package_sha256"], package)
        frame = reopened.post(endpoint + f"/{approved['id']}/opening-frame-preparations", json={"shot_index": 0})
        assert frame.status_code == 200, frame.text
        assert frame.json()["payload"]["reference_design_plan"] == designs
        assert frame.json()["payload"]["unmaterialized_visual_asset_keys"] == ["grandma", "beach"]
        assert frame.json()["payload"]["reference_designs_materialized"] is False
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
