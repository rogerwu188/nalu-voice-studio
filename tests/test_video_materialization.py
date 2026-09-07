from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.giggle_task_query import GiggleTaskObservation
from nalu_runtime.models import RemoteTaskState
from nalu_runtime.task_observation_service import TaskObservationService
from nalu_runtime.video_download import VideoDownloadError
from test_paid_submitter_boundary import paid_run
from test_video_download import mp4


@pytest.mark.parametrize("case", ["ok", "corrupt_saved", "pending", "invalid_index", "archived", "archive_during_download",
                                  "download_error", "concurrent", "wrong_binding"])
def test_observed_video_is_local_candidate_with_restart_and_context_protection(tmp_path, monkeypatch, case):
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    repo, submitter = api.app.state.repository, api.app.state.remote_task_submitter
    run = paid_run(api, tmp_path, run_id="run_video_materialize", model="seedance-2.0-pro")
    binding = submitter.prepare(run.id, task_key="shot-1", provider="giggle", model="seedance-2.0-pro",
                                submission_fingerprint="a" * 64, request_sha256="b" * 64)
    submitter.record_response(binding.id, target_state=RemoteTaskState.SUBMITTED, response_sha256="c" * 64,
                              provider_task_id="synthetic-video-task", charge_classification="synthetic-not-real-billing")
    observation = TaskObservationService(repo).refresh(run.id, binding.id, SimpleNamespace(query=lambda _: GiggleTaskObservation(
        "synthetic-video-task", "pending" if case == "pending" else "completed", ("https://example.org/视频.mp4",), "d" * 64)))
    raw, downloads = mp4(), []
    def download(url):
        downloads.append(url)
        if case == "download_error":
            raise VideoDownloadError("fixture unavailable")
        if case == "archive_during_download":
            with repo.db.connect() as db:
                db.execute("UPDATE projects SET archived_at='fixture' WHERE id=?", (run.project_id,))
        return raw
    monkeypatch.setattr("nalu_runtime.video_materialization.download_video", download)
    if case in {"archived", "wrong_binding"}:
        with repo.db.connect() as db:
            if case == "archived":
                db.execute("UPDATE projects SET archived_at='fixture' WHERE id=?", (run.project_id,))
            else:
                db.execute("UPDATE remote_task_bindings SET provider_task_id='foreign-task' WHERE id=?", (binding.id,))
    endpoint = f"/v1/production-runs/{run.id}/video-observations/{observation.id}/materialize"
    assert api.post(endpoint, headers={"Origin": "https://example.org"}).status_code == 403
    if case == "concurrent":
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: api.post(endpoint), range(2)))
        assert all(result.status_code == 200 for result in results), [result.text for result in results]
        assert results[0].json()["id"] == results[1].json()["id"]
        result = results[0]
    else:
        result = api.post(endpoint, params={"result_index": 3 if case == "invalid_index" else 0})
    if case in {"pending", "invalid_index", "archived", "archive_during_download", "download_error", "wrong_binding"}:
        assert result.status_code == (502 if case == "download_error" else 409), result.text
        assert not any(e.event_type == "video_result_materialized" for e in repo.list_run_events(run.id))
        return
    assert result.status_code == 200, result.text
    record = result.json()["payload"]
    assert record["video_downloaded"] is True
    assert all(record[key] is False for key in ["generation_performed", "billing_verified", "master_accepted", "visual_semantics_verified"])
    path = tmp_path / "data/runs" / run.id / "generated-videos" / record["filename"]
    assert path.read_bytes() == raw and path.stat().st_mode & 0o777 == 0o600
    preview = f"/v1/production-runs/{run.id}/video-results/{result.json()['id']}/content"
    assert api.get(preview).content == raw
    assert api.get(preview, headers={"Origin": "https://example.org"}).status_code == 403
    count = len(downloads)
    if case == "corrupt_saved":
        path.write_bytes(b"corrupted")
    restarted = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    replay = restarted.post(endpoint)
    if case == "corrupt_saved":
        assert replay.status_code == 409
    else:
        assert replay.json()["id"] == result.json()["id"]
    assert len(downloads) == count
    assert repo.get_remote_task_binding(binding.id).state == "submitted"
