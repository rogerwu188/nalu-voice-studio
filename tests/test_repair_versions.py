import hashlib
import json
from pathlib import Path

import pytest
from nalu_runtime.models import RunStatus
from nalu_runtime.video_preparation import digest
from test_rendered_output_immutability import (
    advance_episode_to_qa,
    approved_episode_with_library,
    client,
)


@pytest.mark.parametrize("parent_changes_before_commit", [False, True, "plan"])
def test_local_repair_version_preserves_parent_and_replays_after_restart(
    tmp_path, monkeypatch, parent_changes_before_commit
):
    api = client(tmp_path)
    _, episode, _ = approved_episode_with_library(api)
    endpoint = f"/v1/episodes/{episode['id']}/production-runs"
    assert api.get(endpoint).json() == []
    assert api.get('/v1/episodes/missing/production-runs').status_code == 404
    parent = api.post(endpoint, json={"dry_run": True}).json()
    parent_package = json.loads(Path(parent["package_path"]).read_text())
    shot = {"source_excerpt": "林叔", "scene": "家", "duration_seconds": 10,
            "entry_state": "门外", "action": "回家", "exit_state": "门内", "camera": "中景",
            "dialogue_or_narration": "回家", "sound": "脚步", "image_prompt": "门口",
            "video_prompt": "走进家", "reference_asset_ids": [], "transition": "scene_start"}
    original_plan = {"plan": {"summary": "回家", "shots": [shot] * (episode["target_seconds"] // 10)},
                     "approved": True, "production_package_sha256": parent_package["package_sha256"],
                     "script_revision": parent_package["approved_script"]["revision"]}
    original_plan["plan_sha256"] = digest(original_plan)
    original_event = api.app.state.repository.append_run_event(parent["id"], "shot_plan_approved", payload=original_plan)
    advance_episode_to_qa(api, episode["id"])
    api.app.state.repository.update_run_status(parent["id"], RunStatus.QA_REVIEW)
    directory = Path(parent["package_path"]).parent
    exports = directory / "qingshan-workspace" / "exports"
    (exports / "bad.mp4").write_bytes(b"invalid test master")
    (exports / "captions.vtt").write_text("WEBVTT\n", encoding="utf-8")
    base = f"/v1/production-runs/{parent['id']}"
    seal = api.post(base + "/rendered-output-seal", json={"sealed_by": "test", "artifacts": [
        {"kind": "master_video", "relative_path": "bad.mp4", "media_type": "video/mp4"},
        {"kind": "captions", "relative_path": "captions.vtt", "media_type": "text/vtt"}]}).json()
    assert api.post(base + "/media-structure-qa").json()["status"] == "FAIL"
    plan = api.get(base + "/postproduction-repair-plan").json()
    old_files = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    body = {"dry_run": True, "repair_source_run_id": parent["id"],
            "expected_repair_plan_sha256": plan["plan_sha256"], "approved_by": "test",
            "repair_confirmation": "确认准备新版本，不开始付费生成"}
    assert api.post(endpoint, json=body).status_code == 409
    headers = {"Idempotency-Key": "repair-one"}
    for override in (
        {"paid_generation_approved": True},
        {"repair_confirmation": None},
        {"expected_repair_plan_sha256": None},
        {"approved_by": None},
    ):
        rejected = api.post(endpoint, json={**body, **override}, headers=headers)
        assert rejected.status_code == 422, rejected.text
    stale = api.post(endpoint, json={**body, "expected_repair_plan_sha256": "0" * 64},
                     headers={"Idempotency-Key": "stale-plan"})
    assert stale.status_code == 409, stale.text
    if parent_changes_before_commit:
        repository = api.app.state.repository
        original_commit = repository.commit_preflight_run

        def commit_after_parent_changed(*args, **kwargs):
            if parent_changes_before_commit == "plan":
                (directory / "postproduction-repair-plan.json").write_text("{}", encoding="utf-8")
            else:
                repository.update_run_status(parent["id"], RunStatus.CANCELLED)
            return original_commit(*args, **kwargs)

        monkeypatch.setattr(repository, "commit_preflight_run", commit_after_parent_changed)
    response = api.post(endpoint, json=body, headers=headers)
    if parent_changes_before_commit:
        assert response.status_code == 409, response.text
        assert api.app.state.repository.latest_run_for_episode(episode["id"]).id == parent["id"]
        assert all((directory / path).read_bytes() == content for path, content in old_files.items()
                   if not (parent_changes_before_commit == "plan" and path.name == "postproduction-repair-plan.json"))
        return
    assert response.status_code == 201, response.text
    repair = response.json()
    assert repair["id"] != parent["id"] and repair["dry_run"]
    package = json.loads(Path(repair["package_path"]).read_text())
    assert package["production_policy"]["repair_lineage"]["output_seal_sha256"] == seal["manifest_sha256"]
    assert not package["production_policy"]["paid_generation_approved"]
    assert client(tmp_path).post(endpoint, json=body, headers=headers).json() == repair
    assert api.post(endpoint, json=body, headers={"Idempotency-Key": "another"}).status_code == 409
    assert api.get(base).json()["status"] == "qa_review"
    history = client(tmp_path).get(endpoint)
    assert history.status_code == 200
    assert [run["id"] for run in history.json()] == [repair["id"], parent["id"]]
    assert [run["status"] for run in history.json()] == ["preflight", "qa_review"]
    _, other_episode, _ = approved_episode_with_library(api)
    assert api.get(f"/v1/episodes/{other_episode['id']}/production-runs").json() == []
    assert api.app.state.repository.latest_run_for_episode(episode["id"]).id == repair["id"]
    assert all((directory / path).read_bytes() == content for path, content in old_files.items())
    draft_endpoint = f"/v1/production-runs/{repair['id']}/repair-shot-draft"
    draft_request = {"source_run_id": parent["id"], "source_event_id": original_event.id,
                     "expected_plan_sha256": original_plan["plan_sha256"],
                     "expected_package_sha256": package["package_sha256"]}
    assert api.post(draft_endpoint, json=draft_request, headers={"Origin": "https://example.com"}).status_code == 403
    assert api.post(draft_endpoint, json={**draft_request, "expected_plan_sha256": "0" * 64}).status_code == 409
    draft = api.post(draft_endpoint, json=draft_request)
    assert draft.status_code == 200, draft.text
    assert draft.json()["event_type"] == "shot_plan_drafted"
    assert draft.json()["payload"]["approved"] is False
    assert draft.json()["payload"]["generation_performed"] is False
    assert draft.json()["payload"]["paid_approved"] is False
    assert all(task["state"] == "awaiting_plan_review_and_frame" for task in draft.json()["payload"]["tasks"])
    assert client(tmp_path).post(draft_endpoint, json=draft_request).json() == draft.json()
    api.app.state.repository.append_run_event(repair["id"], "shot_plan_revised", payload={})
    assert api.post(draft_endpoint, json=draft_request).status_code == 409
    # History playback reads the original seal, never the child workspace.
    restarted = client(tmp_path)
    download = restarted.get(base + "/sealed-master")
    assert download.status_code == 200, download.text
    assert download.content == b"invalid test master"
    assert download.headers["X-Nalu-Master-SHA256"] == hashlib.sha256(download.content).hexdigest()
    assert restarted.get(f"/v1/production-runs/{repair['id']}/sealed-master").status_code == 409
    assert restarted.app.state.repository.latest_run_for_episode(episode["id"]).id == repair["id"]
    # Byte integrity is not semantic acceptance: this deliberately invalid video
    # is inspectable, but remains QA_REVIEW. Tampering must block even inspection.
    assert restarted.get(base).json()["status"] == "qa_review"
    (exports / "bad.mp4").write_bytes(b"tampered")
    assert restarted.get(base + "/sealed-master").status_code == 409
