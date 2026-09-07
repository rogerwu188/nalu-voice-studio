"""Persist unapproved timed transcript drafts bound to actual adopted PCM."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .episode_audio_review import EpisodeAudioReviewService
from .repository import ConflictError, encode, new_id, utc_now
from .video_preparation import digest


class RecordingWord(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)


class RecordingTranscriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    expected_take_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_id: str = Field(min_length=1, max_length=160)
    source_audio_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sample_count: int = Field(strict=True, ge=1, le=14_400_000)
    transcript: str = Field(min_length=1, max_length=24000)
    segments: list[RecordingWord] = Field(min_length=1, max_length=4000)
    recognizer_id: Literal["apple-speech-on-device"]
    recognizer_version: str = Field(min_length=1, max_length=200)
    generated_at: AwareDatetime
    local_recognition: Literal[True]

    @model_validator(mode="after")
    def ordered_window(self):
        end = 0.0
        for word in self.segments:
            if not end <= word.start_seconds < word.end_seconds <= self.sample_count / 48000:
                raise ValueError("transcript segments must be ordered inside the accepted recording")
            end = word.end_seconds
        return self


class RecordingTranscriptService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def _validate(self, run_id, take_id, request, db):
        audio, sha = EpisodeAudioReviewService(self.repository, self.data_root).accepted_audio(
            run_id, take_id, request.expected_take_sha256, request.expected_review_id, _db=db)
        if sha != request.source_audio_sha256 or len(audio) != 44 + request.sample_count * 4:
            raise ConflictError("transcript source does not match the current accepted PCM")

    def save(self, run_id, take_id, request):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._validate(run_id, take_id, request, db)
            payload = {**request.model_dump(mode="json"), "take_id": take_id,
                       "captions_approved": False, "speech_alignment_verified": False,
                       "master_accepted": False, "recognition_evidence": "CLIENT_REPORTED_LOCAL_ASR_DRAFT"}
            payload["transcript_sha256"] = digest(payload)
            for event in repo.list_run_events(run_id):
                if event.event_type == "episode_recording_transcribed" and event.payload == payload:
                    return event
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                "episode_recording_transcribed", None, None, "Timed transcript draft saved; user review required.",
                encode(payload), utc_now()))
        return repo.get_run_event(identity)

    def recover(self, run_id, take_id, expected_take_sha256, expected_review_id):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            matches = [event for event in repo.list_run_events(run_id)
                       if event.event_type == "episode_recording_transcribed" and event.payload.get("take_id") == take_id
                       and event.payload.get("expected_review_id") == expected_review_id]
            if not matches:
                EpisodeAudioReviewService(repo, self.data_root).accepted_audio(
                    run_id, take_id, expected_take_sha256, expected_review_id, _db=db)
                return None
            latest = matches[-1]
            p = latest.payload
            if (p.get("transcript_sha256") != digest({k: v for k, v in p.items() if k != "transcript_sha256"})
                    or p.get("expected_take_sha256") != expected_take_sha256
                    or any(p.get(key) is not False for key in ("captions_approved", "speech_alignment_verified", "master_accepted"))):
                raise ConflictError("saved transcript identity or integrity changed")
            request = RecordingTranscriptRequest.model_validate({key: p[key] for key in RecordingTranscriptRequest.model_fields})
            self._validate(run_id, take_id, request, db)
            return latest
