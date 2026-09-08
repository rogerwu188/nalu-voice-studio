import io
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.giggle_task_query import GiggleTaskObservation
from nalu_runtime.models import RemoteTaskState
from nalu_runtime.task_observation_service import TaskObservationService
from nalu_runtime.video_preparation import digest
from test_paid_submitter_boundary import paid_run
from test_video_download import mp4


@pytest.mark.parametrize("case", ["accept", "reject", "stale", "duration", "ratio", "changed_inputs", "concurrent"])
def test_video_review_is_bound_replayable_and_not_master_qa(tmp_path, monkeypatch, case):
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    repo, submitter = api.app.state.repository, api.app.state.remote_task_submitter
    run = paid_run(api, tmp_path, run_id="run_video_review", model="seedance-2.0-pro")
    prepared = {"task_key": "shot", "request": {"duration_seconds": 2 if case == "duration" else 1,
                "video_transport": {"aspect_ratio": "16:9" if case == "ratio" else "1:1"}}, "request_sha256": "b" * 64}
    prepared["preparation_sha256"] = digest(prepared)
    preparation = repo.append_run_event(run.id, "video_task_prepared", message="synthetic preparation", payload=prepared)
    # Isolate decision service; production-input validation has its own compiler/
    # director/frame contract suites. Real synthetic MP4 materialization is used.
    def validate_preparation(_service, _run_id, _request, *, _read_saved=False):
        # Mirror the production API's explicit saved-read mode. State-policy
        # behavior is independently exercised by test_saved_video_read_states.
        assert isinstance(_read_saved, bool)
        return {**prepared, "preparation_sha256": "c" * 64} if case == "changed_inputs" else prepared

    monkeypatch.setattr("nalu_runtime.video_review.VideoPreparationService.validate", validate_preparation)
    binding = submitter.prepare(run.id, task_key="shot", provider="giggle", model="seedance-2.0-pro",
                                submission_fingerprint="a" * 64, request_sha256="b" * 64)
    submitter.record_response(binding.id, target_state=RemoteTaskState.SUBMITTED, response_sha256="c" * 64,
                              provider_task_id="fixture-task", charge_classification="synthetic-not-real-billing")
    observed = TaskObservationService(repo).refresh(run.id, binding.id, SimpleNamespace(query=lambda _: GiggleTaskObservation(
        "fixture-task", "completed", ("https://example.org/video.mp4",), "d" * 64)))
    raw = mp4()
    monkeypatch.setattr("nalu_runtime.video_materialization.download_video", lambda _: raw)
    result = api.post(f"/v1/production-runs/{run.id}/video-observations/{observed.id}/materialize").json()
    endpoint = f"/v1/production-runs/{run.id}/video-results/{result['id']}/reviews"
    request = {"preparation_id": preparation.id, "expected_materialization_sha256": result["payload"]["materialization_sha256"],
               "decision": "reject" if case == "reject" else "accept", "reviewed_by": "fixture-user", "confirmation": "采用这个镜头"}
    if case == "stale":
        request["expected_materialization_sha256"] = "0" * 64
    assert api.post(endpoint, json=request, headers={"Origin": "https://example.org"}).status_code == 403
    if case == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: api.post(endpoint, json=request), range(2)))
        assert responses[0].json()["id"] == responses[1].json()["id"]
        response = responses[0]
    else:
        response = api.post(endpoint, json=request)
    if case in {"stale", "duration", "ratio", "changed_inputs"}:
        assert response.status_code == 409, response.text
        assert not any(e.event_type == "video_shot_reviewed" for e in repo.list_run_events(run.id))
        return
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["payload"]["user_approved"] == (case != "reject")
    assert all(saved["payload"][k] is False for k in ["visual_semantics_verified", "audio_verified", "billing_verified",
                                                   "master_accepted", "generation_performed"])
    restarted = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    assert restarted.post(endpoint, json=request).json()["id"] == saved["id"]
    tail_route = f"/v1/production-runs/{run.id}/video-reviews/{saved['id']}/tail-frame"
    assert api.post(tail_route, headers={"Origin": "https://example.org"}).status_code == 403
    tail = api.post(tail_route)
    if case == "reject":
        assert tail.status_code == 409
    else:
        assert tail.status_code == 200, tail.text
        assert tail.json()["payload"]["frame_index"] == 11
        assert tail.json()["payload"]["time_seconds"] == pytest.approx(11 / 12)
        assert tail.json()["payload"]["generation_performed"] is False
        assert restarted.post(tail_route).json()["id"] == tail.json()["id"]
        preview = f"/v1/production-runs/{run.id}/video-tails/{tail.json()['id']}/content"
        png = api.get(preview).content
        with av.open(io.BytesIO(raw)) as source:
            final = list(source.decode(video=0))[-1].to_ndarray(format="rgb24")
        with av.open(io.BytesIO(png)) as image:
            extracted = next(image.decode(video=0)).to_ndarray(format="rgb24")
        assert np.array_equal(extracted, final)
        if case == "concurrent":
            with ThreadPoolExecutor(max_workers=2) as pool:
                tails = list(pool.map(lambda _: api.post(tail_route), range(2)))
            assert all(t.json()["id"] == tail.json()["id"] for t in tails)
        assert api.get(preview, headers={"Origin": "https://example.org"}).status_code == 403
    changed = {**request, "decision": "reject" if case != "reject" else "accept"}
    assert api.post(endpoint, json=changed).status_code == 409
    changed["expected_review_event_id"] = saved["id"]
    assert api.post(endpoint, json=changed).status_code == 200
    if case != "reject":
        assert api.get(preview).status_code == 409
        assert api.post(tail_route).status_code == 409
    assert repo.get_remote_task_binding(binding.id).state == "submitted"
