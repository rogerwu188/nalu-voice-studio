import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.asset_service import AssetService
from nalu_runtime.giggle_task_query import GiggleTaskObservation
from nalu_runtime.image_observation import ImageObservationService
from nalu_runtime.image_preparation import ImagePreparationRequest, ImagePreparationService
from nalu_runtime.image_submission import ImageSubmissionService
from nalu_runtime.models import ProductionRun, RunStatus
from nalu_runtime.repository import ConflictError, utc_now
from nalu_runtime.video_preparation import VideoPreparationRequest, VideoPreparationService, digest
from test_director_draft import director_fixture
from test_image_download import png


@pytest.mark.parametrize("case", ["accept", "reject", "stale_image", "changed_file", "changed_plan", "downstream", "restart",
                                  "other_shot_prepared", "same_shot_prepared", "other_shot_budget", "same_shot_budget",
                                  "other_shot_remote", "same_shot_remote", "video_assemble", "video_missing_director", "video_unknown_prior", "video_wrong_index",
                                  "video_script_changed", "video_frame_rejected"])
def test_exact_saved_frame_preview_and_versioned_user_review(tmp_path, monkeypatch, case):
    db_path, root = tmp_path / "db", tmp_path / "data"
    api = TestClient(create_app(db_path, root))
    repo = api.app.state.repository
    project = api.post("/v1/projects", json={"title": "合成首帧确认", "aspect_ratio": "1:1"}).json()
    season = api.post(f"/v1/projects/{project['id']}/seasons", json={"title": "第一季", "season_number": 1}).json()
    episode_response = api.post(f"/v1/seasons/{season['id']}/episodes", json={"title": "海边", "episode_number": 1, "target_seconds": 15})
    assert episode_response.status_code == 201, episode_response.text
    episode = episode_response.json()
    story = "海浪拍岸。" if case.startswith("video_") else "外婆看海。"
    api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": story, "source_transcript": story,
        "summary_for_voice_review": "海边"})
    script = api.post(f"/v1/episodes/{episode['id']}/scripts/1/approve", json={"approved_by": "QA"}).json()
    package = {"project": project, "episode": episode, "approved_script": script, "inherited_assets": []}
    if case.startswith("video_"):
        package["production_policy"] = {"requested_model": "seedance-2.0-pro"}
        package["resolved_library"] = []
    package["package_sha256"] = digest(package)
    path = tmp_path / "package.json"
    path.write_text(json.dumps(package))
    now = utc_now()
    run = ProductionRun(id="run_frame_review", project_id=project["id"], season_id=season["id"], episode_id=episode["id"],
        status=RunStatus.WAITING_FOR_APPROVAL, dry_run=False, requested_model="seedance-2.0-pro", estimated_budget_credits=None,
        package_path=str(path), created_at=now, updated_at=now)
    repo.save_run(run)
    shot = {"source_excerpt": "外婆看海。", "scene": "海边", "duration_seconds": 15, "entry_state": "外婆站在岸边",
        "action": "抬头看海", "exit_state": "面朝海面", "camera": "中景", "dialogue_or_narration": "我又回来了。",
        "sound": "海浪", "image_prompt": "外婆尚未抬头", "video_prompt": "外婆抬头看海",
        "reference_asset_ids": [], "transition": "scene_start"}
    if case.startswith("video_"):
        # Synthetic contract assembly fixture, not semantic approval of this image.
        shot.update(source_excerpt=story, entry_state="海浪尚未抵岸", action="海浪前进", exit_state="海浪抵岸",
                    dialogue_or_narration="", image_prompt="海浪尚未抵岸，无人物", video_prompt="海浪拍岸，无人物")
        shot["director"] = {**director_fixture(), "visible_character_counts": {}, "prior_event_relation": "RESOLVED"}
        shot["director"]["state_delta"] = {"mode": "CHANGE", "dimensions": [{"dimension": "POSITION", "entry": "离岸", "exit": "抵岸"}]}
        if case == "video_missing_director":
            shot["director"] = None
        if case == "video_unknown_prior":
            shot["director"]["prior_event_relation"] = "UNKNOWN"
    plan = {"plan": {"summary": "海边", "shots": [shot]}, "approved": True,
        "production_package_sha256": package["package_sha256"]}
    if case.startswith("video_"):
        plan["tasks"] = [{"task_key": "E01-U01", "shot_index": 0}]
        plan["script_revision"] = script["revision"]
    if case == "video_assemble":
        shot["duration_seconds"] = 8
        continuation = {**shot, "duration_seconds": 7, "transition": "continuous", "entry_state": shot["exit_state"]}
        plan["plan"]["shots"].append(continuation)
        plan["tasks"].append({"task_key": "E01-U02", "shot_index": 1})
    plan["plan_sha256"] = digest(plan)
    plan_event = repo.append_run_event_once(run.id, "shot_plan_approved", dedupe_key="plan_sha256",
        dedupe_value=plan["plan_sha256"], message="Synthetic confirmed shot fixture", payload=plan)
    source = ImagePreparationRequest(task_key="E01-U01", approved_plan_event_id=plan_event.id,
        approved_plan_sha256=plan["plan_sha256"])
    preparer = ImagePreparationService(repo, AssetService(repo, root))
    prepared = preparer.prepare(run.id, source)
    assert prepared.payload["resolution"] == "1K"
    assert prepared.payload["documented_dimensions"] == {"width": 1024, "height": 1024}
    _, request = preparer.materialize(run.id, source)
    binding = ImageSubmissionService(repo).submit(run.id, "E01-U01-entry", request, secret=lambda: "synthetic-key",
        authorize=lambda *args: None, transport=httpx.MockTransport(lambda _: httpx.Response(200,
            json={"code": 200, "data": {"task_id": "fixture-task"}})))  # synthetic authority only
    observation = ImageObservationService(repo).refresh(run.id, binding.id, SimpleNamespace(query=lambda _: GiggleTaskObservation(
        "fixture-task", "completed", ("https://example.org/image.png",), "0" * 64)))
    monkeypatch.setattr("nalu_runtime.image_materialization.download_image", lambda _: png())
    materialized = api.post(f"/v1/production-runs/{run.id}/image-observations/{observation.id}/materialize").json()
    endpoint = f"/v1/production-runs/{run.id}/image-results/{materialized['id']}"
    preview = api.get(endpoint + "/content")
    assert preview.status_code == 200 and preview.content == png()
    assert preview.headers["Cache-Control"] == "no-store" and preview.headers["X-Content-Type-Options"] == "nosniff"
    assert api.get(endpoint + "/content", headers={"Origin": "https://example.org"}).status_code == 403
    incoming = {"preparation_id": prepared.id, "expected_materialization_sha256": materialized["payload"]["materialization_sha256"],
        "decision": "reject" if case == "reject" else "accept", "reviewed_by": "QA", "confirmation": "合成画面已查看"}
    if case == "stale_image":
        incoming["expected_materialization_sha256"] = "0" * 64
    elif case == "changed_file":
        (root / "runs" / run.id / "generated-images" / materialized["payload"]["filename"]).write_bytes(b"changed fixture")
        assert api.get(endpoint + "/content").status_code == 409
    elif case in {"changed_plan", "downstream"}:
        repo.append_run_event_once(run.id, "shot_plan_revised" if case == "changed_plan" else "video_task_prepared",
            dedupe_key="fixture", dedupe_value=case, message="Synthetic changed context", payload={"fixture": case})
    elif case in {"other_shot_prepared", "same_shot_prepared", "other_shot_budget", "same_shot_budget"}:
        repo.append_run_event(run.id, "video_estimate_reserved" if case.endswith("budget") else "video_task_prepared",
                              payload={"task_key": "E01-U02" if case.startswith("other") else "E01-U01"})
    elif case in {"other_shot_remote", "same_shot_remote"}:
        with repo.db.connect() as db:
            db.execute("INSERT INTO remote_task_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("synthetic-video", run.id, "E01-U02" if case.startswith("other") else "E01-U01",
                        "giggle", run.requested_model, "0" * 64, "1" * 64, "submitted",
                        "synthetic-video-id", None, None, "{}", "unknown", None, now, now))
    result = api.post(endpoint + "/review", json=incoming)
    if case in {"stale_image", "changed_file", "changed_plan", "downstream", "same_shot_prepared", "same_shot_budget", "same_shot_remote"}:
        assert result.status_code == 409, result.text
        return
    assert result.status_code == 200, result.text
    record = result.json()["payload"]
    assert record["user_approved"] == (case != "reject")
    assert record["image_sha256"] == materialized["payload"]["image"]["sha256"]
    assert record["visual_semantics_verified"] is False and record["paid_approved"] is False
    if case.startswith("video_"):
        request = {"expected_plan_sha256": plan["plan_sha256"], "shot_index": 1 if case == "video_wrong_index" else 0,
                   "approved_frame_review_id": result.json()["id"]}
        url = f"/v1/production-runs/{run.id}/shot-plans/{plan_event.id}/video-preparations"
        assert api.post(url, json=request, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
        if case == "video_script_changed":
            revision = api.post(f"/v1/episodes/{episode['id']}/scripts", json={
                "content": "改成傍晚的海浪。", "summary_for_voice_review": "改成傍晚"})
            assert revision.status_code == 201, revision.text
            assert api.post(f"/v1/episodes/{episode['id']}/scripts/{revision.json()['revision']}/approve",
                            json={"approved_by": "QA"}).status_code == 200
        if case == "video_frame_rejected":
            assert api.post(endpoint + "/review", json={**incoming, "decision": "reject",
                "expected_review_event_id": result.json()["id"]}).status_code == 200
        prepared_video = api.post(url, json=request)
        if case != "video_assemble":
            assert prepared_video.status_code == 409, prepared_video.text
            assert not any(event.event_type == "video_task_prepared" for event in repo.list_run_events(run.id))
            return
        assert prepared_video.status_code == 200, prepared_video.text
        video_record = prepared_video.json()["payload"]
        assert video_record["request"]["prompt"] == shot["video_prompt"]
        assert video_record["request"]["camera_plan"] == shot["director"]["camera"]
        assert video_record["frame"]["sha256"] == record["image_sha256"]
        assert video_record["generation_performed"] is False and video_record["paid_approved"] is False
        reopened = TestClient(create_app(db_path, root))
        assert reopened.post(url, json=request).json()["id"] == prepared_video.json()["id"]
        assert len([event for event in repo.list_run_events(run.id) if event.event_type == "video_task_prepared"]) == 1
        # Synthetic provider observation, but real plan/frame/video validation:
        # no monkeypatch of VideoPreparationService for this acceptance chain.
        from nalu_runtime.task_observation_service import TaskObservationService
        from test_video_download import mp4
        with repo.db.connect() as db:
            db.execute("INSERT INTO remote_task_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("review-video", run.id, video_record["task_key"], "giggle", run.requested_model,
                        "0" * 64, video_record["request_sha256"], "submitted", "synthetic-video-id",
                        None, None, "{}", "unknown", None, now, now))
        observation = TaskObservationService(repo).refresh(run.id, "review-video", SimpleNamespace(query=lambda _: GiggleTaskObservation(
            "synthetic-video-id", "completed", ("https://example.org/video.mp4",), "d" * 64)))
        video_bytes = mp4(frames=12 * shot["duration_seconds"])
        monkeypatch.setattr("nalu_runtime.video_materialization.download_video", lambda _: video_bytes)
        candidate = api.post(f"/v1/production-runs/{run.id}/video-observations/{observation.id}/materialize")
        assert candidate.status_code == 200, candidate.text
        receipt = candidate.json()
        accepted = api.post(f"/v1/production-runs/{run.id}/video-results/{receipt['id']}/reviews", json={
            "preparation_id": prepared_video.json()["id"],
            "expected_materialization_sha256": receipt["payload"]["materialization_sha256"],
            "decision": "accept", "reviewed_by": "synthetic-qa", "confirmation": "采用这个镜头"})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["payload"]["approved_plan_event_id"] == plan_event.id
        assert accepted.json()["payload"]["master_accepted"] is False
        tail = api.post(f"/v1/production-runs/{run.id}/video-reviews/{accepted.json()['id']}/tail-frame")
        assert tail.status_code == 200, tail.text
        assert tail.json()["payload"]["frame_index"] == 12 * shot["duration_seconds"] - 1
        next_request = {"expected_plan_sha256": plan["plan_sha256"], "shot_index": 1, "approved_tail_id": tail.json()["id"]}
        following = api.post(url, json=next_request)
        assert following.status_code == 200, following.text
        assert following.json()["payload"]["request"]["shot_role"] == "SAME_SCENE_CONTINUATION"
        assert following.json()["payload"]["frame"]["sha256"] == tail.json()["payload"]["frame_sha256"]
        assert reopened.post(url, json=next_request).json()["id"] == following.json()["id"]
        auto_url = f"/v1/production-runs/{run.id}/shot-plans/{plan_event.id}/continuation-preparations"
        auto_request = {"expected_plan_sha256": plan["plan_sha256"], "shot_index": 1}
        assert api.post(auto_url, json=auto_request, headers={"Origin": "https://example.org"}).status_code == 403
        assert api.post(auto_url, json=auto_request).json()["id"] == following.json()["id"]
        assert reopened.post(auto_url, json=auto_request).json()["id"] == following.json()["id"]
        assert api.post(auto_url, json={**auto_request, "expected_plan_sha256": "0" * 64}).status_code == 409
        assert api.post(auto_url, json={**auto_request, "shot_index": 2}).status_code == 409
        assert api.post(url, json={**next_request, "approved_tail_id": None,
                                  "approved_frame_review_id": result.json()["id"]}).status_code == 409
        assert api.post(url, json={**next_request, "shot_index": 0}).status_code == 409
        revoked = api.post(f"/v1/production-runs/{run.id}/video-results/{receipt['id']}/reviews", json={
            "preparation_id": prepared_video.json()["id"],
            "expected_materialization_sha256": receipt["payload"]["materialization_sha256"],
            "expected_review_event_id": accepted.json()["id"],
            "decision": "reject", "reviewed_by": "synthetic-qa", "confirmation": "不采用这个镜头"})
        assert revoked.status_code == 200, revoked.text
        assert reopened.post(url, json=next_request).status_code == 409
        assert reopened.post(auto_url, json=auto_request).status_code == 409
        return
    video = VideoPreparationRequest(task_key="E01-U01", request={}, approved_plan_event_id=plan_event.id,
        approved_plan_sha256=plan["plan_sha256"], approved_frame_review_id=result.json()["id"])
    boundary = VideoPreparationService(repo)
    frame_sha = materialized["payload"]["image"]["sha256"]
    if case == "reject":
        with pytest.raises(ConflictError):
            boundary._frame_binding(run.id, video, frame_sha)
    else:
        assert boundary._frame_binding(run.id, video, frame_sha)["frame_materialization_id"] == materialized["id"]
        with pytest.raises(ConflictError):
            boundary._frame_binding(run.id, video, "0" * 64)
        with pytest.raises(ConflictError):
            boundary._frame_binding(run.id, video.model_copy(update={"approved_frame_review_id": None}), frame_sha)
    reopened = TestClient(create_app(db_path, root))
    assert reopened.post(endpoint + "/review", json=incoming).json()["id"] == result.json()["id"]
    changed = {**incoming, "decision": "reject" if incoming["decision"] == "accept" else "accept"}
    assert reopened.post(endpoint + "/review", json=changed).status_code == 409
    changed["expected_review_event_id"] = result.json()["id"]
    assert reopened.post(endpoint + "/review", json=changed).status_code == 200
    assert reopened.post(endpoint + "/review", json=incoming).status_code == 409
    with pytest.raises(ConflictError):
        boundary._frame_binding(run.id, video, frame_sha)
