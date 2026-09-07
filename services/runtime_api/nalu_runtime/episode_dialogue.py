"""Assemble adopted cue recordings and captions without fabricating sound layers."""

import hashlib
import io
import os
import tempfile
import wave
from contextlib import nullcontext
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .episode_audio import EpisodeAudioService
from .episode_audio_review import EpisodeAudioReviewService
from .episode_transcript import RecordingTranscriptService, caption_vtt
from .models import (
    PostproductionAudioSource,
    PostproductionMaterializationCreate,
    PostproductionShotSource,
)
from .postproduction_materializer import PostproductionMaterializationError, _safe_input
from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory, sync_directory
from .video_preparation import digest


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


class EpisodeDialogueStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sound_plan_id: str = Field(min_length=1, max_length=160)
    expected_sound_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_lineage_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EpisodeMixPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staging_id: str = Field(min_length=1, max_length=160)
    expected_staging_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    requested_by: str = Field(min_length=1, max_length=160)
    sound_layers: list[PostproductionAudioSource] = Field(min_length=4, max_length=4)
    width: int = Field(default=1920, ge=16, le=3840)
    height: int = Field(default=1080, ge=16, le=2160)

    @model_validator(mode="after")
    def distinct_layers(self):
        if {layer.layer for layer in self.sound_layers} != {"ambience", "foley", "music", "sfx"}:
            raise ValueError("select exactly one source for each remaining sound layer")
        if self.width % 2 or self.height % 2:
            raise ValueError("output geometry must use even dimensions")
        return self


class EpisodeDialogueService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def prepare_mix(self, run_id, request):
        repo = self.repository
        receipt = repo.get_run_event(request.staging_id)
        p = receipt.payload
        if (receipt.run_id != run_id or receipt.event_type != "episode_dialogue_staged"
                or p.get("staging_sha256") != request.expected_staging_sha256
                or digest({k: v for k, v in p.items() if k != "staging_sha256"}) != request.expected_staging_sha256):
            raise ConflictError("mix preparation requires the exact staged dialogue")
        lineage, files = p["lineage"], p["files"]
        sound = repo.get_run_event(lineage["sound_plan_id"]).payload
        edit = repo.get_run_event(sound["edit_id"]).payload
        prepared = PostproductionMaterializationCreate(
            requested_by=request.requested_by, adopted_dialogue_staging_id=receipt.id,
            expected_dialogue_staging_sha256=p["staging_sha256"],
            shots=[PostproductionShotSource.model_validate(shot) for shot in edit["shots"]],
            audio_layers=[PostproductionAudioSource(layer="dialogue",
                source_relative_path=files["dialogue.wav"]["relative_path"],
                source_sha256=files["dialogue.wav"]["sha256"],
                source_cue_sha256s=[digest(cue) for cue in sound["cues"]]),
                *sorted(request.sound_layers, key=lambda layer: layer.layer)],
            captions_source_relative_path=files["captions.vtt"]["relative_path"],
            captions_source_sha256=files["captions.vtt"]["sha256"],
            subtitle_contract_sha256=digest([s["caption_review_sha256"] for s in lineage["sources"]]),
            width=request.width, height=request.height, frame_rate=edit["frame_rate"])
        self.validate_materialization(run_id, prepared)
        exports = Path(repo.get_run(run_id).package_path).parent / "qingshan-workspace/exports"
        try:
            for layer in request.sound_layers:
                _safe_input(exports, layer.source_relative_path, layer.source_sha256)
        except PostproductionMaterializationError as exc:
            raise ConflictError("selected sound-layer file is missing or changed") from exc
        return prepared

    def validate_materialization(self, run_id, request):
        receipt = self.repository.get_run_event(request.adopted_dialogue_staging_id)
        p = receipt.payload
        if (receipt.run_id != run_id or receipt.event_type != "episode_dialogue_staged"
                or p.get("staging_sha256") != request.expected_dialogue_staging_sha256
                or digest({k: v for k, v in p.items() if k != "staging_sha256"}) != request.expected_dialogue_staging_sha256):
            raise ConflictError("adopted dialogue staging identity changed")
        lineage = p["lineage"]
        current = self.stage(run_id, EpisodeDialogueStageRequest(sound_plan_id=lineage["sound_plan_id"],
            expected_sound_plan_sha256=lineage["sound_plan_sha256"], expected_lineage_sha256=lineage["lineage_sha256"]))
        if current.id != receipt.id:
            raise ConflictError("adopted dialogue receipt changed")
        sound = self.repository.get_run_event(lineage["sound_plan_id"]).payload
        edit = self.repository.get_run_event(sound["edit_id"]).payload
        dialogue = next((layer for layer in request.audio_layers if layer.layer == "dialogue"), None)
        files = p["files"]
        cues = [digest(cue) for cue in sound["cues"]]
        if (dialogue is None or dialogue.source_relative_path != files["dialogue.wav"]["relative_path"]
                or dialogue.source_sha256 != files["dialogue.wav"]["sha256"]
                or dialogue.source_in_seconds != 0 or dialogue.source_cue_sha256s != cues
                or request.captions_source_relative_path != files["captions.vtt"]["relative_path"]
                or request.captions_source_sha256 != files["captions.vtt"]["sha256"]
                or request.subtitle_contract_sha256 != digest([s["caption_review_sha256"] for s in lineage["sources"]])
                or [shot.model_dump(mode="json") for shot in request.shots] != edit["shots"]
                or request.frame_rate != edit["frame_rate"]):
            raise ConflictError("materialization inputs differ from adopted edit, dialogue or captions")
        return receipt

    def build(self, run_id, sound_plan_id, expected_sound_plan_sha256, *, _db=None):
        repo = self.repository
        audio_service = EpisodeAudioReviewService(repo, self.data_root)
        transcripts = RecordingTranscriptService(repo, self.data_root)
        with (repo.db.connect() if _db is None else nullcontext(_db)) as db:
            if _db is None:
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
            manifest = {"sound_plan_id": sound_plan_id, "sound_plan_sha256": expected_sound_plan_sha256,
                "sources": lineage, "dialogue_sha256": hashlib.sha256(audio).hexdigest(),
                "captions_sha256": hashlib.sha256(captions).hexdigest(), "master_accepted": False,
                "speech_alignment_verified": False, "other_audio_layers_generated": False}
            manifest["lineage_sha256"] = digest(manifest)
            return audio, captions, manifest

    def stage(self, run_id, request):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            audio, captions, lineage = self.build(run_id, request.sound_plan_id,
                request.expected_sound_plan_sha256, _db=db)
            if lineage["lineage_sha256"] != request.expected_lineage_sha256:
                raise ConflictError("dialogue sources changed before staging")
            run = repo.get_run(run_id)
            package = Path(run.package_path).absolute()
            root = Path(self.data_root).resolve()
            if package.resolve() != package or not package.is_relative_to(root / "runs") or not package.is_file():
                raise ConflictError("dialogue workspace is outside managed storage")
            if (package.parent / "rendered-output-seal.json").exists():
                raise ConflictError("sealed outputs cannot accept new staged dialogue")
            relative = f"provider-results/adopted-dialogue/{lineage['lineage_sha256']}"
            exports = package.parent / "qingshan-workspace" / "exports"
            directory = package.parent
            for component in ("qingshan-workspace", "exports", *relative.split("/")):
                directory /= component
                if directory.is_symlink() or directory.resolve() != directory:
                    raise ConflictError("unsafe dialogue staging directory")
                secure_directory(directory)
            files = {"dialogue.wav": audio, "captions.vtt": captions,
                     "lineage.json": (encode(lineage) + "\n").encode("utf-8")}
            payload = {"run_id": run_id, "lineage": lineage, "files": {
                name: {"relative_path": str((directory / name).relative_to(exports)),
                       "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw)}
                for name, raw in files.items()}, "master_accepted": False}
            payload["staging_sha256"] = digest(payload)
            existing = next((e for e in repo.list_run_events(run_id)
                if e.event_type == "episode_dialogue_staged" and e.payload.get("lineage", {}).get("lineage_sha256") == request.expected_lineage_sha256), None)
            if existing and existing.payload != payload:
                raise ConflictError("dialogue staging receipt changed")
            for name, raw in files.items():
                path = directory / name
                if path.exists() or path.is_symlink():
                    if path.is_symlink() or not path.is_file() or path.stat().st_size != len(raw) or path.read_bytes() != raw:
                        raise ConflictError("staged dialogue is changed; reconciliation required")
                    continue
                if existing:
                    raise ConflictError("staged dialogue is missing; reconciliation required")
                descriptor, temporary = tempfile.mkstemp(prefix=".dialogue-", dir=directory)
                try:
                    with os.fdopen(descriptor, "wb") as target:
                        target.write(raw); target.flush(); os.fsync(target.fileno())
                    os.link(temporary, path)
                    sync_directory(directory)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                    sync_directory(directory)
            if existing:
                return existing
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                "episode_dialogue_staged", None, None, "Adopted dialogue/captions staged; final mixing remains pending.",
                encode(payload), utc_now()))
        return repo.get_run_event(identity)
