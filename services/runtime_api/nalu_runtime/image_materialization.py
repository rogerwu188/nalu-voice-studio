"""Materialize observed image bytes as immutable run-local files, pending visual QA."""

import hashlib
import os
import re
import tempfile
from pathlib import Path

from .image_download import download_image, inspect_image
from .image_observation import ImageObservationService
from .repository import ConflictError, Repository
from .secure_files import secure_directory, sync_directory
from .video_preparation import digest


class ImageMaterializationService:
    def __init__(self, repository: Repository, data_root: Path):
        self.repository, self.data_root = repository, data_root.resolve()

    def _observation(self, run_id, observation_id, index):
        event = self.repository.get_run_event(observation_id)
        record = event.payload
        if (event.run_id != run_id or event.event_type != "image_task_observed"
                or record.get("run_id") != run_id or record.get("status") != "completed"
                or record.get("observation_sha256") != digest({k: v for k, v in record.items() if k != "observation_sha256"})
                or type(index) is not int or not 0 <= index < len(record.get("result_urls", []))):
            raise ConflictError("download requires a completed saved image observation and valid result index")
        binding = ImageObservationService(self.repository)._binding(run_id, record.get("submission_id"))
        if (binding.payload["provider_task_id"] != record.get("task_id")
                or binding.payload["request_sha256"] != record.get("request_sha256")):
            raise ConflictError("image result differs from saved submission")
        return event

    def _directory(self, run_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_id):
            raise ConflictError("invalid run storage identity")
        path = self.data_root
        for part in ("runs", run_id, "generated-images"):
            path = path / part
            if path.is_symlink():
                raise ConflictError("unsafe image storage path")
            secure_directory(path)
        return path

    def materialize(self, run_id, observation_id, index=0):
        observed = self._observation(run_id, observation_id, index)
        identity = digest({"run_id": run_id, "observation_id": observation_id, "result_index": index})
        directory = self._directory(run_id)
        for event in self.repository.list_run_events(run_id):
            if event.event_type == "image_result_materialized" and event.payload.get("materialization_id") == identity:
                record = event.payload
                if record.get("materialization_sha256") != digest({k: v for k, v in record.items() if k != "materialization_sha256"}):
                    raise ConflictError("saved image materialization integrity failed")
                filename = record.get("filename", "")
                if not re.fullmatch(r"[a-f0-9]{64}\.(png|jpg)", filename):
                    raise ConflictError("invalid saved image filename")
                path = directory / filename
                if path.is_symlink() or not path.is_file() or path.stat().st_size != record["image"]["byte_size"]:
                    raise ConflictError("saved image is missing or changed; reconcile rather than replace")
                if inspect_image(path.read_bytes()) != record["image"]:
                    raise ConflictError("saved image bytes changed")
                return event
        url = observed.payload["result_urls"][index]
        raw = download_image(url)
        image = inspect_image(raw)
        if self._observation(run_id, observation_id, index).payload != observed.payload:
            raise ConflictError("image observation changed during download")
        filename = image["sha256"] + "." + image["extension"]
        path = directory / filename
        descriptor, temporary = tempfile.mkstemp(prefix=".image-", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            try:
                os.link(temporary, path)  # Immutable publication, never overwrite an existing image.
            except FileExistsError:
                if path.is_symlink() or not path.is_file() or path.stat().st_size != len(raw) or path.read_bytes() != raw:
                    raise ConflictError("image storage collision requires reconciliation") from None
            sync_directory(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
            sync_directory(directory)
        record = {"run_id": run_id, "materialization_id": identity, "observation_id": observation_id,
                  "submission_id": observed.payload["submission_id"], "result_index": index,
                  "task_key": observed.payload["task_key"], "request_sha256": observed.payload["request_sha256"],
                  "source_url_sha256": hashlib.sha256(url.encode()).hexdigest(), "filename": filename,
                  "image": image, "image_downloaded": True, "visual_semantics_verified": False,
                  "billing_verified": False, "master_accepted": False, "generation_performed": False}
        record["materialization_sha256"] = digest(record)
        return self.repository.append_run_event_once(run_id, "image_result_materialized", dedupe_key="materialization_id",
            dedupe_value=identity, message="Image saved locally; visual approval remains required.", payload=record)
