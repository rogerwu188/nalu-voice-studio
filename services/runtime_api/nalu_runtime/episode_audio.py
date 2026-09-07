"""Bind an existing authorized recording to an approved episode sound cue."""

import hashlib
import time
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from .episode_edit_review import EpisodeEditReviewService
from .models import AssetKind, AudienceMode
from .postproduction_materializer import PostproductionMaterializationError, _audio_chunks
from .repository import ConflictError, encode, new_id, utc_now
from .video_preparation import digest


class EpisodeAudioTakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sound_plan_id: str = Field(min_length=1, max_length=160)
    expected_sound_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shot_index: int = Field(strict=True, ge=0, le=119)
    asset_id: str = Field(min_length=1, max_length=160)
    expected_asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_in_seconds: float = Field(default=0.0, ge=0, le=1800)


class EpisodeAudioService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, Path(data_root).resolve()

    def recover(self, run_id, sound_plan_id, expected_sound_plan_sha256, *, _db=None):
        """Read saved candidates, never create a replacement for an invalid take."""
        repo = self.repository
        sound = repo.get_run_event(sound_plan_id)
        plan = sound.payload
        if (sound.run_id != run_id or sound.event_type != "episode_sound_plan_drafted"
                or plan.get("sound_plan_sha256") != expected_sound_plan_sha256
                or digest({k: v for k, v in plan.items() if k != "sound_plan_sha256"}) != expected_sound_plan_sha256
                or plan.get("edit_approved") is not True):
            raise ConflictError("recording recovery requires the exact approved sound plan")
        EpisodeEditReviewService(repo, self.data_root).approved(
            run_id, plan["edit_id"], plan["edit_sha256"], plan["edit_review_id"])
        latest = {}
        for event in repo.list_run_events(run_id):
            if event.event_type != "episode_audio_take_attached" or event.payload.get("sound_plan_id") != sound_plan_id:
                continue
            payload = event.payload
            if payload.get("take_sha256") != digest({k: v for k, v in payload.items() if k != "take_sha256"}):
                raise ConflictError("saved recording attachment integrity failed")
            latest[payload["shot_index"]] = event
        result = []
        for index in sorted(latest):
            event = latest[index]
            request = EpisodeAudioTakeRequest.model_validate({key: event.payload[key] for key in EpisodeAudioTakeRequest.model_fields})
            if request.expected_sound_plan_sha256 != expected_sound_plan_sha256:
                raise ConflictError("saved recording sound plan changed")
            result.append(self.attach(run_id, request, _expected_event=event, _db=_db))
        return result

    def attach(self, run_id, request, *, _expected_event=None, _db=None):
        repo = self.repository
        with (nullcontext(_db) if _db is not None else repo.db.connect()) as db:
            if _db is None:
                db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            project = repo.get_project(run.project_id)
            episode = repo.get_episode(run.episode_id)
            sound = repo.get_run_event(request.sound_plan_id)
            plan = sound.payload
            if (sound.run_id != run_id or sound.event_type != "episode_sound_plan_drafted"
                    or plan.get("sound_plan_sha256") != request.expected_sound_plan_sha256
                    or digest({k: v for k, v in plan.items() if k != "sound_plan_sha256"}) != request.expected_sound_plan_sha256
                    or plan.get("edit_approved") is not True):
                raise ConflictError("recording requires the exact approved-edit sound plan")
            EpisodeEditReviewService(repo, self.data_root).approved(
                run_id, plan["edit_id"], plan["edit_sha256"], plan["edit_review_id"])
            cues = plan["cues"]
            if request.shot_index >= len(cues) or cues[request.shot_index]["shot_index"] != request.shot_index:
                raise ConflictError("recording cue is absent")
            cue = cues[request.shot_index]
            duration = cue["end_seconds"] - cue["start_seconds"]
            if not 0 < duration <= 300:
                raise ConflictError("recording cue duration is invalid")
            asset = repo.get_asset(request.asset_id)
            if (asset.project_id != run.project_id or asset.kind not in {AssetKind.ARCHIVE_AUDIO, AssetKind.VOICE_REFERENCE}
                    or asset.episode_id not in {None, episode.id} or asset.season_id not in {None, episode.season_id}
                    or not asset.consent_granted
                    or (project.audience_mode == AudienceMode.CHILD and not asset.guardian_approved)):
                raise ConflictError("recording requires project-scoped explicit use consent")
            consents = repo.list_asset_consent_records(asset.id)
            if (not consents or consents[-1].action_type != "granted"
                    or not consents[-1].recorded_by.strip() or not consents[-1].statement.strip()):
                raise ConflictError("recording use consent is missing or revoked")
            uri = urlparse(asset.local_uri)
            path = Path(unquote(uri.path))
            root = self.data_root / "assets" / run.project_id
            if (uri.scheme != "file" or uri.netloc not in {"", "localhost"} or not path.is_absolute()
                    or path.resolve() != path or not path.is_relative_to(root) or not path.is_file()
                    or not 0 < path.stat().st_size <= 100 * 1024 * 1024):
                raise ConflictError("recording must be a managed bounded audio file")
            actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha != request.expected_asset_sha256 or actual_sha != asset.metadata.get("sha256"):
                raise ConflictError("recording bytes changed")
            deadline = time.monotonic() + 30
            count = 0
            try:
                for samples in _audio_chunks(path, start_seconds=request.source_in_seconds,
                                             sample_count=round(duration * 48000), require_full_duration=True,
                                             should_cancel=lambda: time.monotonic() > deadline):
                    count += len(samples) // 2
            except PostproductionMaterializationError as exc:
                raise ConflictError("recording cannot cover this cue; select a usable recording or revise the edit") from exc
            if count != round(duration * 48000) or hashlib.sha256(path.read_bytes()).hexdigest() != actual_sha:
                raise ConflictError("recording changed during decoding")
            record = {**request.model_dump(), "edit_review_id": plan["edit_review_id"],
                      "edit_sha256": plan["edit_sha256"], "cue_sha256": digest(cue),
                      "start_seconds": cue["start_seconds"], "duration_seconds": duration,
                      "decoded_sample_count": count, "sample_rate_hz": 48000, "channels": 2,
                      "consent_record_id": consents[-1].id, "source_audio_used_without_voice_cloning": True,
                      "speech_alignment_verified": False, "audio_approved": False,
                      "captions_approved": False, "master_accepted": False, "generation_performed": False}
            record["take_sha256"] = digest(record)
            if _expected_event is not None:
                # Old receipts encoded the omitted offset as integer 0. Its
                # original digest was checked by recover; compare typed values
                # without replacing that historical digest with float 0.0.
                if ({k: v for k, v in _expected_event.payload.items() if k != "take_sha256"}
                        != {k: v for k, v in record.items() if k != "take_sha256"}):
                    raise ConflictError("recording or authorization changed after attachment")
                return _expected_event
            for event in repo.list_run_events(run_id):
                if event.event_type == "episode_audio_take_attached" and event.payload == record:
                    return event
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT OR IGNORE INTO production_run_assets VALUES (?,?,?)", (run_id, asset.id, actual_sha))
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                       "episode_audio_take_attached", None, None, "Recording attached; listening and speech alignment remain required.",
                       encode(record), utc_now()))
        return repo.get_run_event(identity)
