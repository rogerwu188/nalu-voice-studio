"""Atomic repository authorization guards, not a provider-production fixture."""
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RunStatus
from nalu_runtime.repository import ConflictError, encode, utc_now


@pytest.mark.parametrize("change", [None, "dry", "cancelled", "revision", "plan", "archived", "episode", "newer",
                                    "repair", "repair_wrong_source", "repair_missing_decision"])
def test_local_start_is_atomic_and_requires_current_prepared_episode(tmp_path, change):
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        plan = client.post("/v1/project-plans", json={"project": {"title": "guard fixture"}}).json()
        episode = plan["episodes"][0]
        base = f"/v1/episodes/{episode['id']}"
        client.post(base + "/scripts", json={"content": "合成测试", "summary_for_voice_review": "合成测试"})
        assert client.post(base + "/scripts/1/approve", json={"approved_by": "synthetic QA"}).status_code == 200
        repo, now = app.state.repository, utc_now()
        run = ProductionRun(id="run-a", project_id=plan["project"]["id"], season_id=episode["season_id"],
            episode_id=episode["id"], status=RunStatus.WAITING_FOR_APPROVAL, dry_run=False,
            requested_model="seedance-2.0-pro", estimated_budget_credits=None,
            package_path=str(tmp_path / "unused-package.json"), created_at=now, updated_at=now)
        repo.save_run(run)
        is_repair = isinstance(change, str) and change.startswith("repair")
        if is_repair:
            repo.save_run(run.model_copy(update={"id": "run-0", "status": RunStatus.QA_REVIEW}))
        with repo.db.connect() as db:
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", ("prepared", run.id, 1,
                "episode_mix_prepared", None, None, "fixture", encode({"plan_sha256": "a" * 64}), now))
            if change == "dry" or is_repair:
                db.execute("UPDATE production_runs SET dry_run=1 WHERE id=?", (run.id,))
            if is_repair and change != "repair_missing_decision":
                db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", ("reuse", run.id, 2,
                    "repair_video_reviewed", None, None, "fixture",
                    encode({"candidate": {"source_run_id": "run-0"}}), now))
            if change == "cancelled":
                db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
            if change == "archived":
                db.execute("UPDATE projects SET archived_at=? WHERE id=?", (now, run.project_id))
            if change == "episode":
                db.execute("UPDATE episodes SET status='script_review' WHERE id=?", (run.episode_id,))
        if change == "newer":
            repo.save_run(run.model_copy(update={"id": "run-z"}))
        before = repo.get_episode(run.episode_id).status
        kwargs = {"plan_sha256": ("b" if change == "plan" else "a") * 64,
                  "approved_revision": 2 if change == "revision" else 1, "requested_by": "synthetic QA"}
        if is_repair:
            kwargs["repair_source_run_id"] = "wrong" if change == "repair_wrong_source" else "run-0"
        event_count = len(repo.list_run_events(run.id))
        if change is None or change == "repair":
            assert repo.begin_adopted_postproduction(run.id, **kwargs).status == RunStatus.RUNNING
            assert repo.get_episode(run.episode_id).status == "postproduction"
            assert repo.list_run_events(run.id)[-1].payload["network_call_performed"] is False
        else:
            with pytest.raises(ConflictError):
                repo.begin_adopted_postproduction(run.id, **kwargs)
            assert repo.get_episode(run.episode_id).status == before
            assert len(repo.list_run_events(run.id)) == event_count
