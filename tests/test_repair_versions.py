import json
from pathlib import Path

import pytest
from nalu_runtime.models import RunStatus
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
    parent = api.post(endpoint, json={"dry_run": True}).json()
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
    assert all((directory / path).read_bytes() == content for path, content in old_files.items())
