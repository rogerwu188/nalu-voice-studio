#!/usr/bin/env python3
"""Exercise local repair preview/approved sound timing in an isolated QA fixture."""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("application_support", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args()
    root = args.application_support.resolve()
    if not root.name.startswith("nalu-native-postproduction-") or not (root / "nalu.sqlite3").is_file():
        parser.error("requires an existing isolated native postproduction QA fixture")
    app = create_app(root / "nalu.sqlite3", root / "data")
    with TestClient(app) as api:
        repo = app.state.repository
        base = f"/v1/production-runs/{args.run_id}"
        events = repo.list_run_events(args.run_id)
        edit = [e for e in events if e.event_type == "postproduction_edit_drafted"][-1]
        assert all(item.get("repair_review_id") for item in edit.payload["items"])
        remote_before = repo.db.connect()
        with remote_before as db:
            count_before = db.execute("SELECT COUNT(*) FROM remote_task_bindings WHERE run_id=?", (args.run_id,)).fetchone()[0]
        preview = api.post(base + f"/episode-edit-drafts/{edit.id}/picture-preview",
                           json={"expected_edit_sha256": edit.payload["edit_sha256"]})
        assert preview.status_code == 200, preview.text
        reviews = [e for e in repo.list_run_events(args.run_id) if e.event_type == "postproduction_edit_reviewed"
                   and e.payload.get("edit_id") == edit.id]
        if reviews:
            accepted = reviews[-1]
            assert accepted.payload["edit_approved"] is True
        else:
            response = api.post(base + f"/episode-edit-drafts/{edit.id}/reviews", json={
                "expected_edit_sha256": edit.payload["edit_sha256"],
                "preview_id": preview.headers["X-Nalu-Preview-Receipt-ID"],
                "expected_preview_sha256": preview.headers["X-Nalu-Preview-SHA256"],
                "decision": "accept", "reviewed_by": "isolated synthetic QA",
                "confirmation": "Synthetic repair timing check only, not film quality acceptance"})
            assert response.status_code == 200, response.text
            accepted = repo.get_run_event(response.json()["id"])
        request = {"expected_plan_sha256": edit.payload["plan_sha256"], "edit_id": edit.id,
                   "expected_edit_sha256": edit.payload["edit_sha256"], "expected_edit_review_id": accepted.id}
        sound = api.post(base + "/sound-plan-drafts", json=request)
        assert sound.status_code == 200, sound.text
        result = sound.json()
        assert result["payload"]["edit_approved"] is True
        assert result["payload"]["duration_seconds"] == edit.payload["edited_duration_seconds"]
        assert api.post(base + "/sound-plan-drafts", json=request).json() == result
        with repo.db.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM remote_task_bindings WHERE run_id=?", (args.run_id,)).fetchone()[0] == count_before
        print(json.dumps({"run_id": args.run_id, "edit_id": edit.id, "sound_plan_id": result["id"],
                          "duration_seconds": result["payload"]["duration_seconds"],
                          "real_film_accepted": False, "provider_calls": False}))


if __name__ == "__main__":
    main()
