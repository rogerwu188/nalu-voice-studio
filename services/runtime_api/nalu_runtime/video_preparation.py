"""Persist the exact shot and decoded opening image before paid review/dispatch."""

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import av
from pydantic import BaseModel, ConfigDict, Field

from .giggle_video_transport import seedance_image_payload
from .models import RunStatus
from .qingshan_compilers import ModelCompilerRegistry
from .repository import ConflictError, Repository


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


class VideoPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,120}$")
    request: dict[str, Any]


class VideoPreparationService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def prepare(self, run_id: str, incoming: VideoPreparationRequest):
        run = self.repository.get_run(run_id)
        if self.repository.get_project(run.project_id).archived_at:
            raise ConflictError("archived project is read-only")
        if run.status not in {RunStatus.PREFLIGHT, RunStatus.WAITING_FOR_APPROVAL}:
            raise ConflictError("shot preparation requires a preflight or approval-waiting run")
        path = Path(run.package_path)
        if path.is_symlink() or not path.is_file():
            raise ConflictError("production package is unavailable")
        try:
            package = json.loads(path.read_text())
            package_sha = package["package_sha256"]
            if digest({k: v for k, v in package.items() if k != "package_sha256"}) != package_sha:
                raise ValueError("package changed")
        except (OSError, ValueError, KeyError, TypeError):
            raise ConflictError("production package integrity failed") from None
        if package.get("production_policy", {}).get("requested_model") != run.requested_model:
            raise ConflictError("run model differs from production package")
        failures = ModelCompilerRegistry().validate_paid_boundary_request(
            run.requested_model, incoming.request,
            production_package=package, package_sha256=package_sha,
        )
        if failures:
            raise ConflictError("shot contract failed: " + "; ".join(failures))
        # This concrete transport is image-only. Never drop extra references to fit it.
        payload = seedance_image_payload(incoming.request)
        raw = base64.b64decode(payload["start_frame"]["base64"], validate=True)
        try:
            if not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
                raise ValueError("not a still image")
            with av.open(io.BytesIO(raw)) as image:
                stream = image.streams.video[0]
                codec = stream.codec_context
                if codec.name not in {"png", "mjpeg"} or not 0 < codec.width * codec.height <= 16_000_000:
                    raise ValueError("unsupported opening image")
                decoded = next(image.decode(stream))
                width, height = decoded.width, decoded.height
                decoded.to_ndarray(format="rgb24")
        except Exception:  # noqa: BLE001 -- decoder messages may contain source bytes
            raise ConflictError("opening frame must be a bounded decodable PNG or JPEG") from None
        ratio_width, ratio_height = (int(part) for part in payload["aspect_ratio"].split(":"))
        if abs(width / height - ratio_width / ratio_height) > 0.01:
            raise ConflictError("opening frame aspect ratio differs from the selected video ratio")
        request_sha = digest(incoming.request)
        record = {"task_key": incoming.task_key, "request": incoming.request,
                  "request_sha256": request_sha, "production_package_sha256": package_sha,
                  "frame": {"sha256": hashlib.sha256(raw).hexdigest(), "width": width, "height": height},
                  "provider": "giggle", "model": run.requested_model,
                  "paid_approved": False, "generation_performed": False,
                  "visual_semantics_verified": False}
        record["preparation_sha256"] = digest(record)
        return self.repository.append_run_event_once(
            run_id, "video_task_prepared", dedupe_key="preparation_sha256",
            dedupe_value=record["preparation_sha256"],
            message="Exact shot and opening image saved for review; no provider submission.", payload=record,
        )
