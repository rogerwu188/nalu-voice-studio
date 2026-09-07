"""Explicit listening decisions on exact recording windows, not final mix QA."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .episode_audio import EpisodeAudioService
from .repository import ConflictError, encode, new_id, utc_now
from .video_preparation import digest


class EpisodeAudioReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_take_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=160)
    decision: Literal["accept", "reject"]
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)


class EpisodeAudioReviewService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def review(self, run_id, take_id, request):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            take = repo.get_run_event(take_id)
            payload = take.payload
            if (take.run_id != run_id or take.event_type != "episode_audio_take_attached"
                    or payload.get("take_sha256") != request.expected_take_sha256
                    or digest({k: v for k, v in payload.items() if k != "take_sha256"}) != request.expected_take_sha256):
                raise ConflictError("listening review requires the exact saved recording take")
            current_takes = EpisodeAudioService(repo, self.data_root).recover(
                run_id, payload["sound_plan_id"], payload["expected_sound_plan_sha256"], _db=db)
            if not any(item.id == take_id for item in current_takes):
                raise ConflictError("recording choice changed; listen to the current take")
            events = repo.list_run_events(run_id)
            reviews = [event for event in events if event.event_type == "episode_audio_take_reviewed"
                       and event.payload.get("sound_plan_id") == payload["sound_plan_id"]
                       and event.payload.get("shot_index") == payload["shot_index"]]
            current = reviews[-1] if reviews else None
            if current and current.payload.get("review_sha256") != digest({k: v for k, v in current.payload.items() if k != "review_sha256"}):
                raise ConflictError("saved listening review integrity failed")
            request_sha = digest({"take_id": take_id, "request": request.model_dump()})
            if current and current.payload.get("request_sha256") == request_sha:
                return current
            if (current.id if current else None) != request.expected_review_id:
                raise ConflictError("listening decision changed; reload before confirming")
            if any("master" in event.event_type or event.event_type == "postproduction_materialized" for event in events):
                raise ConflictError("master work exists; reconcile before changing recording decisions")
            record = {"take_id": take_id, "take_sha256": request.expected_take_sha256,
                      "sound_plan_id": payload["sound_plan_id"], "sound_plan_sha256": payload["expected_sound_plan_sha256"],
                      "edit_review_id": payload["edit_review_id"], "edit_sha256": payload["edit_sha256"],
                      "shot_index": payload["shot_index"], "asset_id": payload["asset_id"],
                      "asset_sha256": payload["expected_asset_sha256"], "source_in_seconds": payload["source_in_seconds"],
                      "duration_seconds": payload["duration_seconds"], "decision": request.decision,
                      "reviewed_by": request.reviewed_by, "confirmation": request.confirmation,
                      "request_sha256": request_sha, "take_approved": request.decision == "accept",
                      "listening_evidence": "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY",
                      "speech_alignment_verified": False, "final_mix_approved": False,
                      "captions_approved": False, "master_accepted": False, "generation_performed": False}
            record["review_sha256"] = digest(record)
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                       "episode_audio_take_reviewed", None, None, "Listening decision saved; alignment and final mix QA remain required.",
                       encode(record), utc_now()))
        return repo.get_run_event(identity)
