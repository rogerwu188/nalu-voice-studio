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
    parser.add_argument("--synthetic-dialogue", action="store_true",
                        help="Exercise test-only listening/transcript confirmations and dialogue staging")
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
        # Attach original synthetic recordings through current consent checks.
        # Never carry the parent's listening/caption approval into the repair.
        source_id = edit.payload["items"][0]["source_run_id"]
        original_takes = [e for e in repo.list_run_events(source_id)
                          if e.event_type == "episode_audio_take_attached"]
        attached = []
        for cue in result["payload"]["cues"]:
            original = [e for e in original_takes if e.payload["shot_index"] == cue["shot_index"]][-1]
            take_request = {"sound_plan_id": result["id"],
                            "expected_sound_plan_sha256": result["payload"]["sound_plan_sha256"],
                            "shot_index": cue["shot_index"], "asset_id": original.payload["asset_id"],
                            "expected_asset_sha256": original.payload["expected_asset_sha256"],
                            "source_in_seconds": original.payload["source_in_seconds"]}
            take = api.post(base + "/audio-takes", json=take_request)
            assert take.status_code == 200, take.text
            assert take.json()["payload"]["audio_approved"] is False
            assert take.json()["payload"]["captions_approved"] is False
            assert api.post(base + "/audio-takes", json=take_request).json() == take.json()
            attached.append(take.json()["id"])
            if args.synthetic_dialogue:
                take_base = base + "/audio-takes/" + take.json()["id"]
                take_sha = take.json()["payload"]["take_sha256"]
                listening = api.post(take_base + "/reviews", json={
                    "expected_take_sha256": take_sha, "decision": "accept",
                    "reviewed_by": "synthetic-qa", "confirmation": "Synthetic tone fixture only, not human listening acceptance"})
                assert listening.status_code == 200, listening.text
                audio_query = {"expected_take_sha256": take_sha, "expected_review_id": listening.json()["id"]}
                audio = api.get(take_base + "/accepted-audio", params=audio_query)
                assert audio.status_code == 200, audio.text
                transcript = api.post(take_base + "/transcripts", json={**audio_query,
                    "source_audio_sha256": audio.headers["x-nalu-audio-sha256"],
                    "sample_count": take.json()["payload"]["decoded_sample_count"],
                    "transcript": "合成测试字幕", "segments": [{"start_seconds": 0.1,
                        "end_seconds": 0.8, "text": "合成测试字幕", "confidence": 0.9}],
                    "recognizer_id": "apple-speech-on-device", "recognizer_version": "synthetic-fixture",
                    "generated_at": "2026-09-07T09:00:00Z", "local_recognition": True})
                assert transcript.status_code == 200, transcript.text
                captions = api.post(take_base + "/transcripts/" + transcript.json()["id"] + "/reviews", json={
                    "expected_transcript_sha256": transcript.json()["payload"]["transcript_sha256"],
                    "segments": [{"start_seconds": 0.1, "end_seconds": 0.8, "text": "合成测试字幕"}],
                    "reviewed_by": "synthetic-qa", "confirmation": "Synthetic caption fixture only"})
                assert captions.status_code == 200, captions.text
        dialogue_stage_id = None
        if args.synthetic_dialogue:
            query = {"sound_plan_id": result["id"],
                     "expected_sound_plan_sha256": result["payload"]["sound_plan_sha256"]}
            audio = api.get(base + "/adopted-dialogue", params=query)
            assert audio.status_code == 200, audio.text
            staged = api.post(base + "/adopted-dialogue/stage", json={**query,
                "expected_lineage_sha256": audio.headers["x-nalu-lineage-sha256"]})
            assert staged.status_code == 200, staged.text
            dialogue_stage_id = staged.json()["id"]
        with repo.db.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM remote_task_bindings WHERE run_id=?", (args.run_id,)).fetchone()[0] == count_before
        print(json.dumps({"run_id": args.run_id, "edit_id": edit.id, "sound_plan_id": result["id"],
                          "duration_seconds": result["payload"]["duration_seconds"],
                          "audio_take_ids": attached,
                          "synthetic_dialogue_stage_id": dialogue_stage_id,
                          "real_film_accepted": False, "provider_calls": False}))


if __name__ == "__main__":
    main()
