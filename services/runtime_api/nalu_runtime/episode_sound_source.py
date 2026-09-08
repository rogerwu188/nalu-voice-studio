"""Prepare authorized local sound assets for episode mixing, without paid generation."""

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from .episode_edit_review import EpisodeEditReviewService
from .models import PostproductionAudioSource, RunStatus
from .postproduction_materializer import PostproductionMaterializationError, _audio_chunks
from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory, sync_directory
from .video_preparation import digest

PREFIX = "provider-results/authorized-sound/"


class EpisodeSoundSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sound_plan_id: str = Field(min_length=1, max_length=160)
    expected_sound_plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    layer: Literal["ambience", "foley", "music", "sfx"]
    asset_id: str = Field(min_length=1, max_length=160)
    expected_asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_in_seconds: float = Field(default=0, ge=0, le=1800)
    gain_db: float = Field(default=0, ge=-60, le=12)


class EpisodeSoundSourceService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, Path(data_root).resolve()

    def asset_source(self, run, request, expected_consent=None):
        repo = self.repository
        project, episode = repo.get_project(run.project_id), repo.get_episode(run.episode_id)
        asset = repo.get_asset(request.asset_id)
        consents = repo.list_asset_consent_records(asset.id)
        if (project.archived_at or asset.project_id != project.id or asset.kind != "archive_audio"
                or not asset.consent_granted or asset.episode_id not in {None, episode.id}
                or asset.season_id not in {None, episode.season_id}
                or (project.audience_mode == "child" and not asset.guardian_approved)
                or not consents or consents[-1].action_type != "granted"
                or not consents[-1].statement.strip() or not consents[-1].recorded_by.strip()
                or (expected_consent is not None and consents[-1].id != expected_consent)):
            raise ConflictError("sound source requires current project-scoped use consent")
        uri = urlparse(asset.local_uri)
        path = Path(unquote(uri.path))
        if (uri.scheme != "file" or uri.netloc not in {"", "localhost"} or path.resolve() != path
                or not path.is_relative_to(self.data_root / "assets" / run.project_id)
                or not path.is_file() or not 0 < path.stat().st_size <= 100 * 1024 * 1024):
            raise ConflictError("sound source must be a managed bounded audio file")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != request.expected_asset_sha256 or asset.metadata.get("sha256") != request.expected_asset_sha256:
            raise ConflictError("sound source bytes changed")
        return path, raw, consents[-1].id

    def stage(self, run_id, request):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            if run.status not in {RunStatus.PREFLIGHT, RunStatus.WAITING_FOR_APPROVAL, RunStatus.RUNNING}:
                raise ConflictError("sound preparation requires an active unsealed production run")
            event = repo.get_run_event(request.sound_plan_id)
            sound = event.payload
            if (event.run_id != run_id or event.event_type != "episode_sound_plan_drafted"
                    or sound.get("sound_plan_sha256") != request.expected_sound_plan_sha256
                    or digest({k: v for k, v in sound.items() if k != "sound_plan_sha256"}) != request.expected_sound_plan_sha256
                    or sound.get("edit_approved") is not True):
                raise ConflictError("sound source requires the exact approved sound plan")
            EpisodeEditReviewService(repo, self.data_root).approved(run_id, sound["edit_id"], sound["edit_sha256"], sound["edit_review_id"])
            duration = sound["duration_seconds"]
            if not 0 < duration <= 1800:
                raise ConflictError("sound timeline duration is invalid")
            path, raw, consent = self.asset_source(run, request)
            deadline = time.monotonic() + 30
            try:
                samples = sum(len(chunk) // 2 for chunk in _audio_chunks(path,
                    start_seconds=request.source_in_seconds, sample_count=round(duration * 48000),
                    require_full_duration=True, should_cancel=lambda: time.monotonic() > deadline))
            except PostproductionMaterializationError as exc:
                raise ConflictError("sound source cannot cover the episode; choose a longer recording") from exc
            if samples != round(duration * 48000) or self.asset_source(run, request, consent)[1] != raw:
                raise ConflictError("sound source changed during preparation")
            binding = {**request.model_dump(), "consent_record_id": consent, "duration_seconds": duration}
            binding_sha = digest(binding)
            relative = f"{PREFIX}{binding_sha}/source.audio"
            source = PostproductionAudioSource(layer=request.layer, source_relative_path=relative,
                source_sha256=request.expected_asset_sha256, source_cue_sha256s=[digest(cue) for cue in sound["cues"]],
                source_in_seconds=request.source_in_seconds, gain_db=request.gain_db)
            payload = {"binding": binding, "source": source.model_dump(mode="json"),
                       "generation_performed": False, "master_accepted": False}
            payload["source_binding_sha256"] = digest(payload)
            existing = next((e for e in repo.list_run_events(run_id)
                if e.event_type == "episode_sound_source_staged" and e.payload == payload), None)
            package = Path(run.package_path).absolute()
            if (package.resolve() != package or not package.is_relative_to(self.data_root / "runs")
                    or not package.is_file() or (package.parent / "rendered-output-seal.json").exists()):
                raise ConflictError("sound workspace is unavailable or sealed")
            directory = package.parent
            for component in ("qingshan-workspace", "exports", *relative.split("/")[:-1]):
                directory /= component
                if directory.is_symlink() or directory.resolve() != directory:
                    raise ConflictError("unsafe sound workspace")
                secure_directory(directory)
            target = directory / "source.audio"
            if target.exists() or target.is_symlink():
                if target.is_symlink() or not target.is_file() or target.read_bytes() != raw:
                    raise ConflictError("staged sound changed; reconciliation required")
            elif existing:
                raise ConflictError("staged sound missing; reconciliation required")
            else:
                descriptor, temporary = tempfile.mkstemp(prefix=".sound-", dir=directory)
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(raw); output.flush(); os.fsync(output.fileno())
                    os.link(temporary, target)
                    sync_directory(directory)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            if existing:
                return existing
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                "episode_sound_source_staged", None, None, "Authorized sound asset prepared for mixing.", encode(payload), utc_now()))
        return repo.get_run_event(identity)

    def validate_sources(self, run_id, sources, sound_plan_id=None):
        sources = [s.model_dump(mode="json") if isinstance(s, PostproductionAudioSource) else s for s in sources]
        sources = [s for s in sources if s["source_relative_path"].startswith(PREFIX)]
        if not sources:
            return
        run = self.repository.get_run(run_id)
        events = self.repository.list_run_events(run_id)
        for source in sources:
            event = next((e for e in events if e.event_type == "episode_sound_source_staged"
                          and e.payload.get("source") == source), None)
            if event is None or digest({k: v for k, v in event.payload.items() if k != "source_binding_sha256"}) != event.payload.get("source_binding_sha256"):
                raise ConflictError("sound source binding is absent or changed")
            binding = event.payload["binding"]
            if sound_plan_id is not None and binding["sound_plan_id"] != sound_plan_id:
                raise ConflictError("sound source belongs to a different episode edit")
            request = EpisodeSoundSourceRequest.model_validate({k: binding[k] for k in EpisodeSoundSourceRequest.model_fields})
            self.asset_source(run, request, binding["consent_record_id"])
