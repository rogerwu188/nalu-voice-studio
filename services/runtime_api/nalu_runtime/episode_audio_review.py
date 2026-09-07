"""Explicit listening decisions on exact recording windows, not final mix QA."""

import hashlib
import io
import sys
import time
import wave
from contextlib import nullcontext
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from .episode_audio import EpisodeAudioService
from .models import RunEvent
from .postproduction_materializer import PostproductionMaterializationError, _audio_chunks
from .repository import ConflictError, encode, new_id, utc_now
from .video_preparation import digest


class EpisodeAudioReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_take_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=160)
    decision: Literal["accept", "reject"]
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)


class EpisodeAudioReviewRecovery(BaseModel):
    current_take_id: str
    current_take_sha256: str
    latest_review: RunEvent | None
    applies_to_current_take: bool
    take_approved: bool


class EpisodeAudioReviewService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def recover(self, run_id, take_id, expected_take_sha256, *, _db=None):
        repo = self.repository
        with (nullcontext(_db) if _db is not None else repo.db.connect()) as db:
            # Serialize the source/consent check and decision snapshot without
            # appending an event or replaying the user's confirmation.
            if _db is None:
                db.execute("BEGIN IMMEDIATE")
            take = repo.get_run_event(take_id)
            p = take.payload
            if (take.run_id != run_id or take.event_type != "episode_audio_take_attached"
                    or p.get("take_sha256") != expected_take_sha256
                    or digest({k: v for k, v in p.items() if k != "take_sha256"}) != expected_take_sha256):
                raise ConflictError("listening recovery requires the exact recording take")
            current = EpisodeAudioService(repo, self.data_root).recover(
                run_id, p["sound_plan_id"], p["expected_sound_plan_sha256"], _db=db)
            if not any(item.id == take_id for item in current):
                raise ConflictError("recording changed; recover the current take first")
            reviews = [event for event in repo.list_run_events(run_id)
                       if event.event_type == "episode_audio_take_reviewed"
                       and event.payload.get("sound_plan_id") == p["sound_plan_id"]
                       and event.payload.get("shot_index") == p["shot_index"]]
            latest = reviews[-1] if reviews else None
            applies = False
            if latest:
                r = latest.payload
                if r.get("review_sha256") != digest({k: v for k, v in r.items() if k != "review_sha256"}):
                    raise ConflictError("saved listening review integrity failed")
                reviewed_take = repo.get_run_event(r["take_id"])
                original = reviewed_take.payload
                if (reviewed_take.run_id != run_id or reviewed_take.event_type != "episode_audio_take_attached"
                        or r["take_sha256"] != original.get("take_sha256")
                        or original.get("take_sha256") != digest({k: v for k, v in original.items() if k != "take_sha256"})
                        or r["sound_plan_id"] != original.get("sound_plan_id")
                        or r["shot_index"] != original.get("shot_index")
                        or any(r.get(review_key) != original.get(take_key) for review_key, take_key in (
                            ("sound_plan_sha256", "expected_sound_plan_sha256"),
                            ("edit_review_id", "edit_review_id"), ("edit_sha256", "edit_sha256"),
                            ("asset_id", "asset_id"), ("asset_sha256", "expected_asset_sha256"),
                            ("source_in_seconds", "source_in_seconds"), ("duration_seconds", "duration_seconds")))
                        or r.get("listening_evidence") != "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY"
                        or r["decision"] not in {"accept", "reject"}
                        or r["take_approved"] != (r["decision"] == "accept")
                        or any(r.get(key) is not False for key in (
                            "speech_alignment_verified", "final_mix_approved", "captions_approved",
                            "master_accepted", "generation_performed"))):
                    raise ConflictError("saved listening review belongs to another recording")
                applies = r["take_id"] == take_id and r["take_sha256"] == expected_take_sha256
            # An older take's decision is retained only as the CAS predecessor,
            # never as approval of the replacement recording.
            return EpisodeAudioReviewRecovery(current_take_id=take_id, current_take_sha256=expected_take_sha256,
                latest_review=latest, applies_to_current_take=applies,
                take_approved=bool(applies and latest.payload.get("take_approved") is True))

    def accepted_audio(self, run_id, take_id, expected_take_sha256, expected_review_id):
        """Decode the exact accepted source window, without padding or cloning."""
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            recovered = self.recover(run_id, take_id, expected_take_sha256, _db=db)
            if (not recovered.take_approved or recovered.latest_review is None
                    or recovered.latest_review.id != expected_review_id):
                raise ConflictError("confirm the current recording before preparing its audio")
            take = repo.get_run_event(take_id).payload
            asset = repo.get_asset(take["asset_id"])
            source = Path(unquote(urlparse(asset.local_uri).path))
            output = io.BytesIO()
            deadline = time.monotonic() + 30
            count = 0
            try:
                with wave.open(output, "wb") as target:
                    target.setnchannels(2)
                    target.setsampwidth(2)
                    target.setframerate(48000)
                    for samples in _audio_chunks(source, start_seconds=take["source_in_seconds"],
                            sample_count=take["decoded_sample_count"], require_full_duration=True,
                            should_cancel=lambda: time.monotonic() > deadline):
                        count += len(samples) // 2
                        if count > 300 * 48000:
                            raise ConflictError("accepted recording exceeds export duration")
                        if sys.byteorder != "little":
                            samples.byteswap()
                        target.writeframesraw(samples.tobytes())
            except PostproductionMaterializationError as exc:
                raise ConflictError("accepted recording could not be decoded") from exc
            # Recovery has already checked managed path and live consent; detect
            # a file edit during decode before returning any bytes to the caller.
            with source.open("rb") as current_source:
                source_bytes = current_source.read(100 * 1024 * 1024 + 1)
            if (count != take["decoded_sample_count"] or source.resolve() != source
                    or len(source_bytes) > 100 * 1024 * 1024
                    or hashlib.sha256(source_bytes).hexdigest() != take["expected_asset_sha256"]):
                raise ConflictError("recording changed while preparing accepted audio")
            data = output.getvalue()
            return data, hashlib.sha256(data).hexdigest()

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
