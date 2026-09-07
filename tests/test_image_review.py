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
                                  "other_shot_remote", "same_shot_remote", "video_assemble", "video_assemble_stage", "video_missing_director", "video_unknown_prior", "video_wrong_index",
                                  "video_script_changed", "video_frame_rejected", "video_sound", "video_sound_empty",
                                  "video_sound_changed", "video_sound_script", "video_sound_archive", "video_sound_hash"])
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
    if case == "video_assemble_stage":
        path = root / "runs/run_frame_review/production-package.json"
        path.parent.mkdir(parents=True)
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
    if case in {"video_assemble", "video_assemble_stage"} or case.startswith("video_sound"):
        shot["duration_seconds"] = 8
        continuation = {**shot, "duration_seconds": 7, "transition": "continuous", "entry_state": shot["exit_state"]}
        plan["plan"]["shots"].append(continuation)
        plan["tasks"].append({"task_key": "E01-U02", "shot_index": 1})
    if case.startswith("video_sound") and case != "video_sound_empty":
        shot["dialogue_or_narration"] = "第一句：<不是字幕标签>。"
        continuation["dialogue_or_narration"] = "第二句：海浪拍岸。"
    plan["plan_sha256"] = digest(plan)
    plan_event = repo.append_run_event_once(run.id, "shot_plan_approved", dedupe_key="plan_sha256",
        dedupe_value=plan["plan_sha256"], message="Synthetic confirmed shot fixture", payload=plan)
    if case.startswith("video_sound"):
        endpoint = f"/v1/production-runs/{run.id}/sound-plan-drafts"
        incoming = {"expected_plan_sha256": plan["plan_sha256"]}
        assert api.post(endpoint, json=incoming, headers={"Origin": "https://example.org"}).status_code == 403
        assert api.post(endpoint, json={**incoming, "api_key": "must-not-send"}).status_code == 422
        assert api.post(endpoint, json={"expected_plan_sha256": "bad"}).status_code == 422
        if case == "video_sound_changed":
            repo.append_run_event(run.id, "shot_plan_revised", payload={"fixture": "newer"})
        elif case == "video_sound_script":
            api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": "新的故事。", "source_transcript": "新的故事。",
                "summary_for_voice_review": "新故事"})
            assert api.post(f"/v1/episodes/{episode['id']}/scripts/2/approve", json={"approved_by": "QA"}).status_code == 200
        elif case == "video_sound_archive":
            assert api.post(f"/v1/projects/{project['id']}/archive", json={"archived": True}).status_code == 200
        elif case == "video_sound_hash":
            incoming["expected_plan_sha256"] = "0" * 64
        response = api.post(endpoint, json=incoming)
        if case not in {"video_sound", "video_sound_empty"}:
            assert response.status_code == 409, response.text
            assert not any(e.event_type == "episode_sound_plan_drafted" for e in repo.list_run_events(run.id))
            return
        assert response.status_code == 200, response.text
        result = response.json()
        payload = result["payload"]
        assert payload["duration_seconds"] == 15
        assert [(c["start_seconds"], c["end_seconds"]) for c in payload["cues"]] == [(0, 8), (8, 15)]
        assert payload["required_audio_layers"] == ["dialogue", "ambience", "foley", "music", "sfx"]
        for key in ("audio_generated", "voice_authorized", "speech_alignment_verified", "captions_approved", "master_accepted", "generation_performed"):
            assert payload[key] is False
        assert all(c["recorded_audio_sha256"] is None and not c["voice_authorized"] for c in payload["cues"])
        if case == "video_sound_empty":
            assert payload["caption_srt_draft"] == ""
        else:
            assert payload["caption_srt_draft"] == (
                "1\n00:00:00,000 --> 00:00:08,000\n第一句：&lt;不是字幕标签&gt;。\n\n"
                "2\n00:00:08,000 --> 00:00:15,000\n第二句：海浪拍岸。\n")
        restarted = TestClient(create_app(db_path, root))
        assert restarted.post(endpoint, json=incoming).json()["id"] == result["id"]
        from concurrent.futures import ThreadPoolExecutor

        from nalu_runtime.episode_sound_plan import EpisodeSoundPlanService
        with ThreadPoolExecutor(max_workers=2) as pool:
            repeated = list(pool.map(lambda _: EpisodeSoundPlanService(repo).prepare(run.id, plan["plan_sha256"]).id, range(2)))
        assert repeated == [result["id"], result["id"]]
        assert len([e for e in repo.list_run_events(run.id) if e.event_type == "episode_sound_plan_drafted"]) == 1
        assert repo.get_run(run.id).status == RunStatus.WAITING_FOR_APPROVAL
        return
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
        if case not in {"video_assemble", "video_assemble_stage"}:
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
        if case == "video_assemble_stage":
            staging = f"/v1/production-runs/{run.id}/accepted-episode-inputs"
            assert api.post(staging).status_code == 409  # Second video still missing.
            second_record = following.json()["payload"]
            with repo.db.connect() as db:
                db.execute("INSERT INTO remote_task_bindings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           ("second-video", run.id, second_record["task_key"], "giggle", run.requested_model,
                            "0" * 64, second_record["request_sha256"], "submitted", "synthetic-second-video",
                            None, None, "{}", "unknown", None, now, now))
            observed2 = TaskObservationService(repo).refresh(run.id, "second-video", SimpleNamespace(query=lambda _: GiggleTaskObservation(
                "synthetic-second-video", "completed", ("https://example.org/second.mp4",), "e" * 64)))
            second_bytes = mp4(frames=12 * 7)
            monkeypatch.setattr("nalu_runtime.video_materialization.download_video", lambda _: second_bytes)
            second = api.post(f"/v1/production-runs/{run.id}/video-observations/{observed2.id}/materialize").json()
            adopted2 = api.post(f"/v1/production-runs/{run.id}/video-results/{second['id']}/reviews", json={
                "preparation_id": following.json()["id"],
                "expected_materialization_sha256": second["payload"]["materialization_sha256"],
                "decision": "accept", "reviewed_by": "synthetic-qa", "confirmation": "采用第二镜头"})
            assert adopted2.status_code == 200, adopted2.text
            assert api.post(staging, headers={"Origin": "https://example.org"}).status_code == 403
            staged = api.post(staging)
            assert staged.status_code == 200, staged.text
            payload = staged.json()["payload"]
            assert [s["shot_id"] for s in payload["shots"]] == ["E01-U01", "E01-U02"]
            assert [s["source_out_seconds"] for s in payload["shots"]] == [8, 7]
            assert payload["master_accepted"] is False and payload["audio_complete"] is False
            assert payload["editorial_selection_complete"] is False and payload["source_windows_are_unedited"] is True
            files = [path.parent / "qingshan-workspace/exports" / s["source_relative_path"] for s in payload["shots"]]
            assert [file.read_bytes() for file in files] == [video_bytes, second_bytes]
            assert all(file.stat().st_mode & 0o777 == 0o600 for file in files)
            assert reopened.post(staging).json()["id"] == staged.json()["id"]
            edit_url = f"/v1/production-runs/{run.id}/episode-edit-drafts"
            cuts = [{"shot_index": 0, "source_in_seconds": 0.5, "source_out_seconds": 7.5},
                    {"shot_index": 1, "source_in_seconds": 0.5, "source_out_seconds": 6.5}]
            edit_request = {"expected_input_sha256": payload["input_sha256"], "cuts": cuts}
            assert api.post(edit_url, json=edit_request, headers={"Origin": "https://example.org"}).status_code == 403
            assert api.post(edit_url, json={**edit_request, "expected_input_sha256": "0" * 64}).status_code == 409
            for invalid_cuts in (cuts[:1], cuts[::-1], [cuts[0], cuts[0]],
                    [{**cuts[0], "source_in_seconds": 0, "source_out_seconds": 8}, cuts[1]],
                    [{**cuts[0], "source_out_seconds": 9}, cuts[1]],
                    [{**cuts[0], "source_out_seconds": 0.501}, cuts[1]]):
                assert api.post(edit_url, json={**edit_request, "cuts": invalid_cuts}).status_code == 409
            edit = api.post(edit_url, json=edit_request)
            assert edit.status_code == 200, edit.text
            editing = edit.json()["payload"]
            assert editing["edited_duration_seconds"] == 13 and editing["planned_duration_seconds"] == 15
            assert [s["source_in_seconds"] for s in editing["shots"]] == [0.5, 0.5]
            assert [s["start_seconds"] for s in editing["timeline"]] == [0, 7]
            assert editing["editorial_selection_complete"] is True and editing["edit_approved"] is False
            assert editing["captions_require_retiming"] is True and editing["master_accepted"] is False
            from nalu_runtime.postproduction_materializer import _selected_frames
            # Exercise the actual renderer's source-window decoder, not a mocked edit.
            for file, cut, timing in zip(files, cuts, editing["timeline"], strict=True):
                decoded = sum(1 for _ in _selected_frames(file, start_seconds=cut["source_in_seconds"],
                    duration_seconds=timing["duration_seconds"], frame_rate=24, width=128, height=128,
                    pixel_format="yuv420p"))
                assert decoded == timing["frame_count"]
            assert reopened.post(edit_url, json=edit_request).json()["id"] == edit.json()["id"]
            preview_url = f"{edit_url}/{edit.json()['id']}/picture-preview"
            preview_request = {"expected_edit_sha256": editing["edit_sha256"]}
            assert api.post(preview_url, json=preview_request, headers={"Origin": "https://example.org"}).status_code == 403
            assert api.post(preview_url, json={"expected_edit_sha256": "0" * 64}).status_code == 409
            from nalu_runtime.episode_preview import PREVIEW_SLOT
            with PREVIEW_SLOT:
                assert api.post(preview_url, json=preview_request).status_code == 409
            picture = api.post(preview_url, json=preview_request)
            assert picture.status_code == 200, picture.text[:200] if picture.status_code != 200 else ""
            import hashlib
            import io

            import av
            assert picture.headers["X-Nalu-Preview-SHA256"] == hashlib.sha256(picture.content).hexdigest()
            assert picture.headers["X-Nalu-Preview-Audio"] == "none"
            assert picture.headers["X-Nalu-Master-Accepted"] == "false"
            with av.open(io.BytesIO(picture.content)) as player:
                frames = list(player.decode(video=0))
                assert len(frames) == 312
                assert abs(float(frames[-1].time) - 311 / 24) < 0.001
                assert not player.streams.audio
            picture_id = picture.headers["X-Nalu-Preview-Receipt-ID"]
            picture_record = repo.get_run_event(picture_id)
            assert picture_record.payload["viewing_verified"] is False
            edit_review_url = f"{edit_url}/{edit.json()['id']}/reviews"
            edit_review = {"expected_edit_sha256": editing["edit_sha256"], "preview_id": picture_id,
                "expected_preview_sha256": picture.headers["X-Nalu-Preview-SHA256"],
                "decision": "reject", "reviewed_by": "synthetic-qa", "confirmation": "合成预览待修改"}
            assert api.post(edit_review_url, json=edit_review, headers={"Origin": "https://example.org"}).status_code == 403
            assert api.post(edit_review_url, json={**edit_review, "expected_preview_sha256": "0" * 64}).status_code == 409
            rejected_edit = api.post(edit_review_url, json=edit_review)
            assert rejected_edit.status_code == 200, rejected_edit.text
            assert rejected_edit.json()["payload"]["edit_approved"] is False
            assert reopened.post(edit_review_url, json=edit_review).json()["id"] == rejected_edit.json()["id"]
            assert api.post(edit_review_url, json={**edit_review, "decision": "accept"}).status_code == 409
            accepted_edit_request = {**edit_review, "decision": "accept", "expected_review_id": rejected_edit.json()["id"],
                                     "confirmation": "合成确认13秒画面剪辑，非成片验收"}
            reviewed_edit = api.post(edit_review_url, json=accepted_edit_request)
            assert reviewed_edit.status_code == 200, reviewed_edit.text
            decision = reviewed_edit.json()["payload"]
            assert decision["edit_approved"] is True
            assert decision["duration_confirmed_seconds"] == 13 and decision["original_planned_seconds"] == 15
            assert not decision["audio_approved"] and not decision["captions_approved"] and not decision["master_accepted"]
            assert reopened.post(edit_review_url, json=accepted_edit_request).json()["id"] == reviewed_edit.json()["id"]
            assert api.post(edit_review_url, json=edit_review).status_code == 409
            retime_url = f"/v1/production-runs/{run.id}/sound-plan-drafts"
            retime = {"expected_plan_sha256": plan["plan_sha256"], "edit_id": edit.json()["id"],
                      "expected_edit_sha256": editing["edit_sha256"]}
            retimed = api.post(retime_url, json=retime)
            assert retimed.status_code == 200, retimed.text
            sound = retimed.json()["payload"]
            assert sound["duration_seconds"] == 13 and sound["planned_duration_seconds"] == 15
            assert [(cue["start_seconds"], cue["end_seconds"]) for cue in sound["cues"]] == [(0, 7), (7, 13)]
            assert sound["edit_approved"] is False and sound["speech_alignment_verified"] is False
            assert reopened.post(retime_url, json=retime).json()["id"] == retimed.json()["id"]
            approved_timing = {**retime, "expected_edit_review_id": reviewed_edit.json()["id"]}
            prepared_sound = api.post(retime_url, json=approved_timing)
            assert prepared_sound.status_code == 200, prepared_sound.text
            approved_sound = prepared_sound.json()["payload"]
            assert approved_sound["edit_approved"] is True
            assert approved_sound["edit_review_sha256"] == decision["review_sha256"]
            assert approved_sound["caption_timing_basis"] == "APPROVED_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT"
            assert approved_sound["duration_seconds"] == 13
            assert not any(approved_sound[key] for key in ("audio_generated", "voice_authorized",
                           "speech_alignment_verified", "captions_approved", "master_accepted", "generation_performed"))
            assert reopened.post(retime_url, json=approved_timing).json()["id"] == prepared_sound.json()["id"]
            import io
            import math
            import struct
            import wave

            from nalu_runtime.models import AssetConsentRevocationCreate, AssetKind, ConsentScope
            audio_buffer = io.BytesIO()
            with wave.open(audio_buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(b"".join(struct.pack("<h", round(1000 * math.sin(i * 0.2))) for i in range(8 * 8000)))
            recording = AssetService(repo, root).import_bytes(project["id"], content=audio_buffer.getvalue(),
                filename="synthetic-tone-not-speech.wav", content_type="audio/wav", kind=AssetKind.ARCHIVE_AUDIO,
                name="合成音频非真实旁白", subject_name="", season_id=None, episode_id=episode["id"],
                consent_granted=True, consent_scope=ConsentScope.PROJECT_ONLY, guardian_approved=False,
                consent_granted_by="synthetic-qa", consent_statement="合成测试音频授权，仅测试")
            take_url = f"/v1/production-runs/{run.id}/audio-takes"
            take_request = {"sound_plan_id": prepared_sound.json()["id"],
                            "expected_sound_plan_sha256": approved_sound["sound_plan_sha256"], "shot_index": 0,
                            "asset_id": recording.id, "expected_asset_sha256": recording.metadata["sha256"]}
            assert api.post(take_url, json=take_request, headers={"Origin": "https://example.org"}).status_code == 403
            assert api.post(take_url, json={**take_request, "expected_asset_sha256": "0" * 64}).status_code == 409
            assert api.post(take_url, json={**take_request, "source_in_seconds": 3}).status_code == 409
            take = api.post(take_url, json=take_request)
            assert take.status_code == 200, take.text
            assert take.json()["payload"]["decoded_sample_count"] == 7 * 48000
            assert not take.json()["payload"]["speech_alignment_verified"]
            assert not take.json()["payload"]["audio_approved"]
            assert reopened.post(take_url, json=take_request).json()["id"] == take.json()["id"]
            assert reopened.post(take_url, json={**take_request, "source_in_seconds": 0.0}).json()["id"] == take.json()["id"]
            assert run.id in repo.asset_dependency_report(recording.id).production_run_ids
            recovery_query = {"sound_plan_id": prepared_sound.json()["id"],
                              "expected_sound_plan_sha256": approved_sound["sound_plan_sha256"]}
            event_count = len(repo.list_run_events(run.id))
            recovered_takes = reopened.get(take_url, params=recovery_query)
            assert recovered_takes.status_code == 200, recovered_takes.text
            assert [item["id"] for item in recovered_takes.json()] == [take.json()["id"]]
            assert len(repo.list_run_events(run.id)) == event_count
            assert api.get(take_url, params={**recovery_query, "expected_sound_plan_sha256": "0" * 64}).status_code == 409
            listening_url = f"{take_url}/{take.json()['id']}/reviews"
            listening_request = {"expected_take_sha256": take.json()["payload"]["take_sha256"],
                                 "decision": "accept", "reviewed_by": "synthetic-qa",
                                 "confirmation": "合成试听确认，仅测试，并非实际旁白验收"}
            assert api.post(listening_url, json=listening_request, headers={"Origin": "https://example.org"}).status_code == 403
            assert api.post(listening_url, json={**listening_request, "expected_take_sha256": "0" * 64}).status_code == 409
            listened = api.post(listening_url, json=listening_request)
            assert listened.status_code == 200, listened.text
            assert listened.json()["payload"]["take_approved"] is True
            assert listened.json()["payload"]["listening_evidence"] == "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY"
            assert not any(listened.json()["payload"][key] for key in ("speech_alignment_verified", "final_mix_approved",
                           "captions_approved", "master_accepted", "generation_performed"))
            assert reopened.post(listening_url, json=listening_request).json()["id"] == listened.json()["id"]
            assert api.post(listening_url, json={**listening_request, "decision": "reject"}).status_code == 409
            rejected_listening = api.post(listening_url, json={**listening_request, "decision": "reject",
                                         "expected_review_id": listened.json()["id"]})
            assert rejected_listening.status_code == 200, rejected_listening.text
            assert rejected_listening.json()["payload"]["take_approved"] is False
            assert reopened.post(listening_url, json=listening_request).status_code == 409
            event_count = len(repo.list_run_events(run.id))
            repo.revoke_asset_consent(recording.id, AssetConsentRevocationCreate(requested_by="synthetic-qa", reason="测试撤销"))
            assert reopened.post(take_url, json=take_request).status_code == 409
            assert reopened.get(take_url, params=recovery_query).status_code == 409
            assert reopened.post(listening_url, json=listening_request).status_code == 409
            assert len(repo.list_run_events(run.id)) == event_count
            assert api.post(retime_url, json={**retime, "expected_edit_review_id": rejected_edit.json()["id"]}).status_code == 409
            assert api.post(retime_url, json={"expected_plan_sha256": plan["plan_sha256"],
                            "expected_edit_review_id": reviewed_edit.json()["id"]}).status_code == 422
            assert api.post(retime_url, json={**retime, "expected_edit_sha256": "0" * 64}).status_code == 409
            assert api.post(retime_url, json={"expected_plan_sha256": plan["plan_sha256"], "edit_id": edit.json()["id"]}).status_code == 422
            assert [file.read_bytes() for file in files] == [video_bytes, second_bytes]
            reject_again = api.post(edit_review_url, json={**edit_review, "expected_review_id": reviewed_edit.json()["id"]})
            assert reject_again.status_code == 200, reject_again.text
            assert reopened.post(take_url, json=take_request).status_code == 409
            assert reopened.post(retime_url, json=approved_timing).status_code == 409
            assert api.post(retime_url, json={**retime, "expected_edit_review_id": reject_again.json()["id"]}).status_code == 409
            files[0].write_bytes(b"corrupted")
            assert reopened.post(staging).status_code == 409
            assert reopened.post(edit_url, json=edit_request).status_code == 409
            assert reopened.post(preview_url, json=preview_request).status_code in {400, 409}
            assert reopened.post(edit_review_url, json=accepted_edit_request).status_code == 409
            return
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
