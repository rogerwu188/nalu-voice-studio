"""Persist a bound provider video as a local candidate, never an accepted master."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .repository import ConflictError, encode, new_id, utc_now
from .secure_files import secure_directory, sync_directory
from .video_download import MAX_VIDEO_BYTES, download_video, inspect_video
from .video_preparation import digest


class VideoMaterializationService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, Path(data_root).resolve()

    def _observation(self, run_id, observation_id, index):
        repo = self.repository
        run = repo.get_run(run_id)
        if repo.get_project(run.project_id).archived_at:
            raise ConflictError("archived project is read-only")
        event = repo.get_run_event(observation_id)
        record = event.payload
        expected = hashlib.sha256(json.dumps({k: v for k, v in record.items() if k != "observation_sha256"},
                                             sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (event.run_id != run_id or event.event_type != "provider_task_observed"
                or record.get("observation_sha256") != expected or record.get("status") != "completed"
                or record.get("billing_verified") is not False or record.get("master_accepted") is not False
                or type(index) is not int or not 0 <= index < len(record.get("result_urls", []))):
            raise ConflictError("a completed bound video observation is required")
        binding = repo.get_remote_task_binding(record.get("binding_id"))
        if (binding.run_id != run_id or binding.provider != "giggle" or binding.model != "seedance-2.0-pro"
                or not binding.provider_task_id or binding.provider_task_id != record.get("task_id")):
            raise ConflictError("video observation differs from saved provider binding")
        return event, binding

    def _directory(self, run_id, *, create=True):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_id):
            raise ConflictError("invalid video storage identity")
        path = self.data_root
        for part in ("runs", run_id, "generated-videos"):
            path = path / part
            if path.is_symlink():
                raise ConflictError("unsafe video storage path")
            if create:
                secure_directory(path)
        return path

    def read_saved(self, run_id, materialization_id):
        event = self.repository.get_run_event(materialization_id)
        record = event.payload
        if (event.run_id != run_id or event.event_type != "video_result_materialized" or record.get("run_id") != run_id
                or record.get("materialization_sha256") != digest({k: v for k, v in record.items() if k != "materialization_sha256"})):
            raise ConflictError("video materialization integrity changed")
        observed, binding = self._observation(run_id, record.get("observation_id"), record.get("result_index"))
        if (record.get("binding_id") != binding.id or record.get("request_sha256") != binding.request_sha256
                or record.get("task_key") != binding.task_key
                or record.get("observation_sha256") != observed.payload["observation_sha256"]):
            raise ConflictError("saved video differs from its source task")
        filename = record.get("filename", "")
        if not re.fullmatch(r"[a-f0-9]{64}\.mp4", filename):
            raise ConflictError("invalid video filename")
        path = self._directory(run_id, create=False) / filename
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != record["video"]["byte_size"]:
                raise ValueError("missing or changed video")
            with path.open("rb") as source:
                raw = source.read(MAX_VIDEO_BYTES + 1)
            if inspect_video(raw) != record["video"] or filename != record["video"]["sha256"] + ".mp4":
                raise ValueError("video changed")
        except Exception:  # noqa: BLE001 -- do not expose private paths or media diagnostics
            raise ConflictError("saved video is missing or changed; reconciliation required") from None
        return event, raw

    def materialize(self, run_id, observation_id, index=0):
        observed, binding = self._observation(run_id, observation_id, index)
        identity = digest({"run_id": run_id, "observation_id": observation_id, "result_index": index})
        for event in self.repository.list_run_events(run_id):
            if event.event_type == "video_result_materialized" and event.payload.get("materialization_id") == identity:
                return self.read_saved(run_id, event.id)[0]
        url = observed.payload["result_urls"][index]
        raw = download_video(url)
        video = inspect_video(raw)
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current, current_binding = self._observation(run_id, observation_id, index)
            if current.payload != observed.payload or current_binding != binding:
                raise ConflictError("video context changed during download")
            # A concurrent materializer may already have committed the same result.
            for event in self.repository.list_run_events(run_id):
                if event.event_type == "video_result_materialized" and event.payload.get("materialization_id") == identity:
                    return self.read_saved(run_id, event.id)[0]
            directory = self._directory(run_id)
            filename = video["sha256"] + ".mp4"
            path = directory / filename
            descriptor, temporary = tempfile.mkstemp(prefix=".video-", dir=directory)
            try:
                with os.fdopen(descriptor, "wb") as target:
                    target.write(raw)
                    target.flush()
                    os.fsync(target.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    if path.is_symlink() or not path.is_file() or path.stat().st_size != len(raw) or path.read_bytes() != raw:
                        raise ConflictError("video storage collision requires reconciliation") from None
                sync_directory(directory)
            finally:
                Path(temporary).unlink(missing_ok=True)
                sync_directory(directory)
            record = {"run_id": run_id, "materialization_id": identity, "observation_id": observation_id,
                      "observation_sha256": observed.payload["observation_sha256"], "binding_id": binding.id,
                      "result_index": index, "task_key": binding.task_key, "request_sha256": binding.request_sha256,
                      "source_url_sha256": hashlib.sha256(url.encode()).hexdigest(), "filename": filename,
                      "video": video, "video_downloaded": True, "generation_performed": False,
                      "billing_verified": False, "visual_semantics_verified": False, "master_accepted": False}
            record["materialization_sha256"] = digest(record)
            event_id, now = new_id("evt"), utc_now()
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, run_id, sequence,
                       "video_result_materialized", None, None, "Video saved locally; shot QA remains required.", encode(record), now))
        return self.repository.get_run_event(event_id)
