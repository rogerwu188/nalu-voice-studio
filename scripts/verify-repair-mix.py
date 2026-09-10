"""Prepare/render only an existing isolated synthetic repair fixture, no providers."""

import argparse
import io
import json
import math
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.asset_service import AssetService
from nalu_runtime.episode_edit_review import EpisodeEditReviewService
from nalu_runtime.models import AssetKind, ConsentScope
from nalu_runtime.repository import ConflictError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("application_support", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--synthetic-sound", action="store_true",
                        help="Import explicitly synthetic full-length tone assets for isolated mix QA")
    args = parser.parse_args()
    root = args.application_support.resolve()
    if not root.name.startswith("nalu-native-postproduction-") or not (root / "nalu.sqlite3").is_file():
        parser.error("requires an isolated native postproduction fixture")
    app = create_app(root / "nalu.sqlite3", root / "data")
    with TestClient(app) as api:
        repo = app.state.repository
        base = f"/v1/production-runs/{args.run_id}"
        events = repo.list_run_events(args.run_id)
        sound = [e for e in events if e.event_type == "episode_sound_plan_drafted"][-1]
        try:
            EpisodeEditReviewService(repo, root / "data").approved(
                args.run_id, sound.payload["edit_id"], sound.payload["edit_sha256"],
                sound.payload.get("edit_review_id"))
        except ConflictError as exc:
            print(json.dumps({"mix_prepared": False, "run_id": args.run_id,
                "failed_stage": "edit_approval", "detail": str(exc),
                "assets_imported": False, "render_started": False,
                "real_master_accepted": False}), flush=True)
            raise SystemExit(1) from exc
        if repo.get_run(args.run_id).status in {"running", "qa_review"}:
            mix = api.get(base + "/adopted-dialogue/prepared-mix", params={"sound_plan_id": sound.id,
                "expected_sound_plan_sha256": sound.payload["sound_plan_sha256"]})
            assert mix.status_code == 200, mix.text
            if args.render:
                rendered = api.post(base + "/postproduction-materializations", json=mix.json())
                print("render_status", rendered.status_code, flush=True)
                assert rendered.status_code == 201, rendered.text
                print(json.dumps(rendered.json()), flush=True)
            return
        staging = [e for e in events if e.event_type == "episode_dialogue_staged"][-1]
        reuse = [e for e in events if e.event_type == "repair_video_reviewed"][-1]
        original = repo.list_run_events(reuse.payload["candidate"]["source_run_id"])
        sources = []
        for layer in ("ambience", "foley", "music", "sfx"):
            source = [e for e in original if e.event_type == "episode_sound_source_staged"
                      and e.payload["binding"]["layer"] == layer][-1]
            binding = source.payload["binding"]
            request = {key: binding[key] for key in ("asset_id", "expected_asset_sha256", "gain_db", "layer", "source_in_seconds")}
            request.update(sound_plan_id=sound.id, expected_sound_plan_sha256=sound.payload["sound_plan_sha256"])
            if args.synthetic_sound:
                run = repo.get_run(args.run_id)
                duration = sound.payload["duration_seconds"]
                assert 0 < duration <= 60, "synthetic fixture is limited to sixty seconds"
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(48000)
                    audio.writeframes(b"".join(struct.pack("<h", int(1000 * math.sin(2 * math.pi * 220 * i / 48000)))
                                               for i in range(round(duration * 48000))))
                content = buffer.getvalue()
                import hashlib
                sha = hashlib.sha256(content).hexdigest()
                name = f"Synthetic repair QA only {layer} {sha}"
                existing = [a for a in repo.list_assets(run.project_id) if a.name == name
                            and a.metadata.get("sha256") == sha and a.episode_id == run.episode_id]
                asset = existing[0] if existing else AssetService(repo, root / "data").import_bytes(
                    run.project_id, content=content, filename=f"synthetic-repair-{layer}.wav",
                    content_type="audio/wav", kind=AssetKind.ARCHIVE_AUDIO, name=name, subject_name="",
                    season_id=None, episode_id=run.episode_id, consent_granted=True,
                    consent_scope=ConsentScope.PROJECT_ONLY, guardian_approved=False,
                    consent_granted_by="synthetic-qa", consent_statement="Locally synthesized tone for isolated QA only")
                request.update(asset_id=asset.id, expected_asset_sha256=sha, source_in_seconds=0)
            prepared = api.post(base + "/sound-sources", json=request)
            if prepared.status_code != 200:
                print(json.dumps({"mix_prepared": False, "run_id": args.run_id,
                    "failed_layer": layer, "asset_id": request["asset_id"],
                    "required_duration_seconds": sound.payload["duration_seconds"],
                    "source_in_seconds": binding["source_in_seconds"],
                    "status_code": prepared.status_code, "detail": prepared.text,
                    "render_started": False, "real_master_accepted": False}), flush=True)
                raise SystemExit(1)
            sources.append(prepared.json()["payload"]["source"])
        mix = api.post(base + "/adopted-dialogue/prepare-mix", json={
            "staging_id": staging.id, "expected_staging_sha256": staging.payload["staging_sha256"],
            "requested_by": "synthetic-repair-qa", "sound_layers": sources, "width": 64, "height": 64})
        assert mix.status_code == 200, mix.text
        print(json.dumps({"mix_prepared": True, "run_id": args.run_id, "real_master_accepted": False}), flush=True)
        if args.render:
            rendered = api.post(base + "/postproduction-materializations", json=mix.json())
            print("render_status", rendered.status_code, flush=True)
            assert rendered.status_code == 201, rendered.text
            print(json.dumps(rendered.json()), flush=True)


if __name__ == "__main__":
    main()
