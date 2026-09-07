import base64
import io
import json

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.asset_service import AssetService
from nalu_runtime.models import (
    AssetKind,
    ConsentScope,
    MemoryCardConfirmation,
    MemoryCardCreate,
    ProductionRun,
    RunStatus,
)
from nalu_runtime.repository import utc_now
from nalu_runtime.video_preparation import digest


@pytest.mark.parametrize("case", ["plain", "reference", "changed_bytes", "stale_plan", "unapproved", "unknown_shot",
                                  "continuous", "changed_ratio", "cancelled", "revoked", "non_image", "script_changed",
                                  "memory_draft", "memory_reference_only", "memory_confirmed"])
def test_confirmed_shot_compiles_opening_image_without_network(tmp_path, case):
    api = TestClient(create_app(tmp_path / "db.sqlite3", tmp_path / "data"))
    repo = api.app.state.repository
    project = api.post("/v1/projects", json={"title": "合成首帧测试"}).json()
    season = api.post(f"/v1/projects/{project['id']}/seasons", json={"title": "第一季", "season_number": 1}).json()
    episode = api.post(f"/v1/seasons/{season['id']}/episodes", json={"title": "海边", "episode_number": 1, "target_seconds": 24}).json()
    api.post(f"/v1/episodes/{episode['id']}/scripts", json={"content": "外婆看海。", "source_transcript": "外婆看海。",
                                                          "summary_for_voice_review": "海边"})
    script = api.post(f"/v1/episodes/{episode['id']}/scripts/1/approve", json={"approved_by": "QA"}).json()
    assets = []
    if case in {"reference", "changed_bytes", "revoked", "non_image", "memory_draft", "memory_reference_only", "memory_confirmed"}:
        output = io.BytesIO()
        with av.open(output, "w", format="image2pipe") as container:
            stream = container.add_stream("png", rate=1)
            stream.width, stream.height, stream.pix_fmt = 16, 16, "rgb24"
            frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        content = output.getvalue() if case != "non_image" else b"fake image bytes"
        storage = AssetService(repo, tmp_path / "data")
        asset = storage.import_bytes(project["id"], content=content, filename="fixture.png", content_type="image/png",
            kind=AssetKind.CHARACTER_IMAGE, name="合成人物", subject_name="QA", season_id=None, episode_id=None,
            consent_granted=True, consent_scope=ConsentScope.PROJECT_ONLY, guardian_approved=False,
            consent_granted_by="QA", consent_statement="Synthetic test only")
        assets = [asset.model_dump(mode="json", exclude={"consent_granted_by", "consent_statement"})]
        if case.startswith("memory_"):
            card = repo.create_memory_card(project["id"], MemoryCardCreate(asset_id=asset.id, title="合成记忆",
                allowed_use="reference_only" if case == "memory_reference_only" else "visual_generation"))
            if case != "memory_draft":
                repo.confirm_memory_card(card.id, MemoryCardConfirmation(confirmed_by="QA", reviewed_revision=1,
                    review_channel="visual", spoken_confirmation="确认合成测试资料"))
    package = {"project": project, "episode": episode, "approved_script": script, "inherited_assets": assets}
    package["package_sha256"] = digest(package)
    path = tmp_path / "package.json"
    path.write_text(json.dumps(package))
    now = utc_now()
    run = ProductionRun(id="run_image_prepare", project_id=project["id"], season_id=season["id"], episode_id=episode["id"],
        status=RunStatus.PREFLIGHT, dry_run=True, requested_model="seedance-2.0-pro", estimated_budget_credits=None,
        package_path=str(path), created_at=now, updated_at=now)
    repo.save_run(run)
    shot = {"source_excerpt": "外婆看海。", "scene": "海边", "duration_seconds": 12, "entry_state": "外婆站在岸边",
        "action": "抬头看海", "exit_state": "面朝海面", "camera": "中景缓推", "dialogue_or_narration": "我又回来了。",
        "sound": "海浪声", "image_prompt": "外婆尚未抬头", "video_prompt": "外婆抬头看海",
        "reference_asset_ids": [a["id"] for a in assets], "transition": "scene_start"}
    second = dict(shot)
    if case == "continuous":
        second.update(transition="continuous", entry_state=shot["exit_state"])
    plan = {"plan": {"summary": "海边", "shots": [shot, second]}, "approved": case != "unapproved",
            "production_package_sha256": package["package_sha256"]}
    plan["plan_sha256"] = digest(plan)
    approved = repo.append_run_event_once(run.id, "shot_plan_approved", dedupe_key="plan_sha256",
        dedupe_value=plan["plan_sha256"], message="Synthetic confirmed-plan fixture, not AI output", payload=plan)
    incoming = {"task_key": "E01-U02" if case == "continuous" else "E01-U01",
                "approved_plan_event_id": approved.id, "approved_plan_sha256": plan["plan_sha256"]}
    if case == "stale_plan":
        incoming["approved_plan_sha256"] = "0" * 64
    if case == "unknown_shot":
        incoming["task_key"] = "invented"
    if case == "changed_bytes":
        storage.managed_path(project["id"], asset.local_uri).write_bytes(b"changed fixture")
    with repo.db.connect() as db:
        if case == "changed_ratio":
            db.execute("UPDATE projects SET aspect_ratio='16:9' WHERE id=?", (project["id"],))
        elif case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        elif case == "revoked":
            db.execute("UPDATE assets SET consent_granted=0 WHERE id=?", (asset.id,))
        elif case == "script_changed":
            db.execute("UPDATE episodes SET approved_script_revision=NULL WHERE id=?", (episode["id"],))
    endpoint = f"/v1/production-runs/{run.id}/image-task-preparations"
    result = api.post(endpoint, json=incoming)
    if case not in {"plain", "reference", "memory_confirmed"}:
        assert result.status_code == 409, result.text
        assert not any(e.event_type == "image_task_prepared" for e in repo.list_run_events(run.id))
        return
    assert result.status_code == 200, result.text
    record = result.json()["payload"]
    assert record["resolution"] == "2K"
    assert record["documented_dimensions"] == {"width": 1152, "height": 2048}
    assert "外婆尚未抬头" in record["prompt"] and "入镜状态：外婆站在岸边" in record["prompt"]
    assert record["paid_approved"] is False and record["generation_performed"] is False
    assert record["image_task_key"] == "E01-U01-entry"
    assert len(record["reference_manifest"]) == (0 if case == "plain" else 1)
    if case != "plain":
        assert base64.b64encode(content).decode() not in result.text and asset.local_uri not in result.text
    restarted = TestClient(create_app(tmp_path / "db.sqlite3", tmp_path / "data"))
    assert restarted.post(endpoint, json=incoming).json()["id"] == result.json()["id"]
    assert not any(e.event_type == "image_submit_intent" for e in repo.list_run_events(run.id))
