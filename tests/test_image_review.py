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
from test_image_download import png


@pytest.mark.parametrize("case", ["accept", "reject", "stale_image", "changed_file", "changed_plan", "downstream", "restart"])
def test_exact_saved_frame_preview_and_versioned_user_review(tmp_path, monkeypatch, case):
    db_path, root = tmp_path / "db", tmp_path / "data"
    api = TestClient(create_app(db_path, root))
    repo = api.app.state.repository
    project = api.post("/v1/projects", json={"title": "合成首帧确认", "aspect_ratio": "1:1"}).json()
    season = api.post(f"/v1/projects/{project['id']}/seasons", json={"title": "第一季", "season_number": 1}).json()
    episode_response = api.post(f"/v1/seasons/{season['id']}/episodes", json={"title": "海边", "episode_number": 1, "target_seconds": 15})
    assert episode_response.status_code == 201, episode_response.text
    episode = episode_response.json()
    api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": "外婆看海。", "source_transcript": "外婆看海。",
        "summary_for_voice_review": "海边"})
    script = api.post(f"/v1/episodes/{episode['id']}/scripts/1/approve", json={"approved_by": "QA"}).json()
    package = {"project": project, "episode": episode, "approved_script": script, "inherited_assets": []}
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
    plan = {"plan": {"summary": "海边", "shots": [shot]}, "approved": True,
        "production_package_sha256": package["package_sha256"]}
    plan["plan_sha256"] = digest(plan)
    plan_event = repo.append_run_event_once(run.id, "shot_plan_approved", dedupe_key="plan_sha256",
        dedupe_value=plan["plan_sha256"], message="Synthetic confirmed shot fixture", payload=plan)
    source = ImagePreparationRequest(task_key="E01-U01", approved_plan_event_id=plan_event.id,
        approved_plan_sha256=plan["plan_sha256"])
    preparer = ImagePreparationService(repo, AssetService(repo, root))
    prepared = preparer.prepare(run.id, source)
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
    result = api.post(endpoint + "/review", json=incoming)
    if case in {"stale_image", "changed_file", "changed_plan", "downstream"}:
        assert result.status_code == 409, result.text
        return
    assert result.status_code == 200, result.text
    record = result.json()["payload"]
    assert record["user_approved"] == (case != "reject")
    assert record["image_sha256"] == materialized["payload"]["image"]["sha256"]
    assert record["visual_semantics_verified"] is False and record["paid_approved"] is False
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
