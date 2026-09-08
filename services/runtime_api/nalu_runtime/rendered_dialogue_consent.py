"""Live recording authorization for an already rendered adopted-dialogue plan."""

import json
import re
from pathlib import Path

from .postproduction_materializer import canonical_sha256
from .repository import ConflictError
from .video_preparation import digest


def validate_rendered_dialogue_consent(repository, data_root, run_id):
    events = [e for e in repository.list_run_events(run_id) if e.event_type == "postproduction_materialized"]
    if not events:
        return
    run = repository.get_run(run_id)
    plan_sha = events[-1].payload.get("plan_sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", plan_sha):
        raise ConflictError("rendered dialogue plan identity is invalid")
    package = Path(run.package_path).absolute()
    path = package.parent / "qingshan-workspace/exports/materialized" / plan_sha / "materialization-plan.json"
    try:
        if (not path.is_relative_to(Path(data_root).resolve() / "runs") or path.resolve() != path
                or not path.is_file() or path.stat().st_size > 8_000_000):
            raise ValueError("unsafe plan")
        plan = json.loads(path.read_text(encoding="utf-8"))
        if (plan.get("plan_sha256") != plan_sha
                or canonical_sha256({k: v for k, v in plan.items() if k != "plan_sha256"}) != plan_sha
                or plan.get("run_id") != run_id):
            raise ValueError("changed plan")
        request = plan["request"]
        from .episode_sound_source import EpisodeSoundSourceService
        EpisodeSoundSourceService(repository, data_root).validate_sources(run_id, request.get("audio_layers", []))
        staging_id = request.get("adopted_dialogue_staging_id")
        if not staging_id:
            return  # Other pipeline sources retain their existing authorization gates.
        staged = repository.get_run_event(staging_id)
        p = staged.payload
        if (staged.run_id != run_id or staged.event_type != "episode_dialogue_staged"
                or p.get("staging_sha256") != request.get("expected_dialogue_staging_sha256")
                or digest({k: v for k, v in p.items() if k != "staging_sha256"}) != p.get("staging_sha256")):
            raise ValueError("changed staged source")
        project = repository.get_project(run.project_id)
        episode = repository.get_episode(run.episode_id)
        if project.archived_at or not p["lineage"]["sources"]:
            raise ValueError("unavailable sources")
        for source in p["lineage"]["sources"]:
            take = repository.get_run_event(source["take_id"])
            t = take.payload
            if (take.run_id != run_id or take.event_type != "episode_audio_take_attached"
                    or t.get("take_sha256") != source["take_sha256"]
                    or digest({k: v for k, v in t.items() if k != "take_sha256"}) != t.get("take_sha256")):
                raise ValueError("changed recording binding")
            asset = repository.get_asset(t["asset_id"])
            consents = repository.list_asset_consent_records(asset.id)
            if (asset.project_id != run.project_id or not asset.consent_granted
                    or asset.kind not in {"archive_audio", "voice_reference"}
                    or asset.metadata.get("sha256") != t["expected_asset_sha256"]
                    or asset.episode_id not in {None, episode.id} or asset.season_id not in {None, episode.season_id}
                    or (project.audience_mode == "child" and not asset.guardian_approved)
                    or not consents or consents[-1].action_type != "granted"
                    or consents[-1].id != t["consent_record_id"]):
                raise ConflictError("rendered recording consent is missing, changed or revoked")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ConflictError("rendered dialogue authorization evidence is missing or changed") from exc
