"""Assemble adopted cue recordings and captions without fabricating sound layers."""

import hashlib
import io
import wave

from .episode_audio import EpisodeAudioService
from .episode_audio_review import EpisodeAudioReviewService
from .episode_transcript import RecordingTranscriptService, caption_vtt
from .repository import ConflictError


def assemble_dialogue(parts, duration_seconds):
    """Require contiguous, complete PCM coverage; no silent padding or stretching."""
    total = round(duration_seconds * 48000)
    if not 1 <= total <= 86_400_000 or not parts:
        raise ConflictError("episode dialogue duration or inventory is invalid")
    pcm = bytearray()
    words = []
    for part in parts:
        start = round(part["start_seconds"] * 48000)
        if start != len(pcm) // 4:
            raise ConflictError("recording coverage contains a gap or overlap")
        with wave.open(io.BytesIO(part["audio"]), "rb") as source:
            if (source.getframerate(), source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (48000, 2, 2, "NONE"):
                raise ConflictError("recording PCM format changed")
            data = source.readframes(source.getnframes())
            if len(data) != part["sample_count"] * 4 or len(pcm) + len(data) > total * 4:
                raise ConflictError("recording PCM coverage changed")
        pcm.extend(data)
        for word in part["segments"]:
            words.append({**word, "start_seconds": word["start_seconds"] + part["start_seconds"],
                          "end_seconds": word["end_seconds"] + part["start_seconds"]})
    if len(pcm) != total * 4:
        raise ConflictError("not every episode cue has adopted audio")
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(2); target.setsampwidth(2); target.setframerate(48000)
        target.writeframes(pcm)
    return output.getvalue(), caption_vtt(words, 0)


class EpisodeDialogueService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def build(self, run_id, sound_plan_id, expected_sound_plan_sha256):
        repo = self.repository
        audio_service = EpisodeAudioReviewService(repo, self.data_root)
        transcripts = RecordingTranscriptService(repo, self.data_root)
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            takes = EpisodeAudioService(repo, self.data_root).recover(
                run_id, sound_plan_id, expected_sound_plan_sha256, _db=db)
            sound = repo.get_run_event(sound_plan_id).payload
            if [e.payload["shot_index"] for e in takes] != list(range(len(sound["cues"]))):
                raise ConflictError("every cue needs an adopted recording before episode assembly")
            parts, lineage = [], []
            for take in takes:
                p = take.payload
                state = audio_service.recover(run_id, take.id, p["take_sha256"], _db=db)
                if not state.take_approved:
                    raise ConflictError("every recording needs explicit listening confirmation")
                review_id = state.latest_review.id
                transcript = transcripts.recover(run_id, take.id, p["take_sha256"], review_id, _db=db)
                if transcript is None:
                    raise ConflictError("every recording needs a saved transcript")
                captions = transcripts.recover_review(run_id, take.id, transcript.id,
                    transcript.payload["transcript_sha256"], _db=db)
                if not captions.captions_approved:
                    raise ConflictError("every recording needs confirmed captions")
                raw, sha = audio_service.accepted_audio(run_id, take.id, p["take_sha256"], review_id, _db=db)
                parts.append({"start_seconds": p["start_seconds"], "sample_count": p["decoded_sample_count"],
                              "audio": raw, "segments": captions.latest_review.payload["segments"]})
                lineage.append({"take_id": take.id, "take_sha256": p["take_sha256"],
                    "recording_review_id": review_id, "audio_sha256": sha,
                    "transcript_id": transcript.id, "transcript_sha256": transcript.payload["transcript_sha256"],
                    "caption_review_id": captions.latest_review.id,
                    "caption_review_sha256": captions.latest_review.payload["review_sha256"]})
            audio, captions = assemble_dialogue(parts, sound["duration_seconds"])
            return audio, captions, {"sound_plan_id": sound_plan_id, "sound_plan_sha256": expected_sound_plan_sha256,
                "sources": lineage, "dialogue_sha256": hashlib.sha256(audio).hexdigest(),
                "captions_sha256": hashlib.sha256(captions).hexdigest(), "master_accepted": False,
                "speech_alignment_verified": False, "other_audio_layers_generated": False}
