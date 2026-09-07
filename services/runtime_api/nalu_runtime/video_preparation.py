"""Persist the exact shot and decoded opening image before paid review/dispatch."""

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import av
from pydantic import BaseModel, ConfigDict, Field

from .director_contract import apply_reviewed_director
from .director_draft import DirectorDraft
from .giggle_video_transport import seedance_image_payload
from .models import RunStatus
from .qingshan_compilers import ModelCompilationError, ModelCompilerRegistry, project_aspect_ratio
from .repository import ConflictError, Repository
from .shot_identity_scope import compile_identity_scope


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


class VideoPreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,120}$")
    request: dict[str, Any]
    approved_plan_event_id: str | None = None
    approved_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    approved_frame_review_id: str | None = None


class VideoPreparationService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def prepare(self, run_id: str, incoming: VideoPreparationRequest):
        record = self.validate(run_id, incoming)
        return self.repository.append_run_event_once(
            run_id, "video_task_prepared", dedupe_key="preparation_sha256",
            dedupe_value=record["preparation_sha256"],
            message="Exact shot and opening image saved for review; no provider submission.", payload=record,
        )

    def validate(self, run_id: str, incoming: VideoPreparationRequest):
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
        plan_binding = self._plan_binding(run_id, incoming, package_sha, package)
        failures = ModelCompilerRegistry().validate_paid_boundary_request(
            run.requested_model, incoming.request,
            production_package=package, package_sha256=package_sha,
        )
        if failures:
            raise ConflictError("shot contract failed: " + "; ".join(failures))
        # This concrete transport is image-only. Never drop extra references to fit it.
        payload = seedance_image_payload(incoming.request)
        try:
            package_ratio = project_aspect_ratio(package)
        except ModelCompilationError:
            raise ConflictError("production package has an invalid project aspect ratio") from None
        if (payload["aspect_ratio"] != package_ratio
                or self.repository.get_project(run.project_id).aspect_ratio != package_ratio):
            raise ConflictError("video aspect ratio differs from the confirmed project")
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
        frame_binding = self._frame_binding(run_id, incoming, hashlib.sha256(raw).hexdigest())
        request_sha = digest(incoming.request)
        record = {"task_key": incoming.task_key, "request": incoming.request,
                  "request_sha256": request_sha, "production_package_sha256": package_sha,
                  "frame": {"sha256": hashlib.sha256(raw).hexdigest(), "width": width, "height": height},
                  "provider": "giggle", "model": run.requested_model,
                  "paid_approved": False, "generation_performed": False,
                  "visual_semantics_verified": False}
        record.update(plan_binding)
        record.update(frame_binding)
        record["preparation_sha256"] = digest(record)
        return record

    def _frame_binding(self, run_id, incoming, frame_sha):
        events = self.repository.list_run_events(run_id)
        image_key = incoming.task_key + "-entry"
        preparations = [event for event in events if event.event_type == "image_task_prepared"
                        and event.payload.get("image_task_key") == image_key]
        reviews = [event for event in events if event.event_type == "image_frame_reviewed"
                   and event.payload.get("task_key") == image_key]
        if not preparations and not reviews and not incoming.approved_frame_review_id:
            return {}  # Professional imports still require their full opening-anchor contract.
        if not reviews or incoming.approved_frame_review_id != reviews[-1].id:
            raise ConflictError("video requires the current confirmed first-frame review")
        review = reviews[-1]
        record = review.payload
        if (record.get("run_id") != run_id or record.get("decision") != "accept" or record.get("user_approved") is not True
                or record.get("review_sha256") != digest({k: v for k, v in record.items() if k != "review_sha256"})
                or record.get("image_sha256") != frame_sha
                or record.get("approved_plan_event_id") != incoming.approved_plan_event_id
                or record.get("approved_plan_sha256") != incoming.approved_plan_sha256):
            raise ConflictError("first-frame approval no longer matches the video image or shot plan")
        materialized = self.repository.get_run_event(record["materialization_id"])
        image = materialized.payload
        if (materialized.run_id != run_id or materialized.event_type != "image_result_materialized"
                or image.get("run_id") != run_id or image.get("task_key") != image_key
                or image.get("materialization_sha256") != record.get("materialization_sha256")
                or image.get("materialization_sha256") != digest({k: v for k, v in image.items() if k != "materialization_sha256"})
                or image.get("image", {}).get("sha256") != frame_sha):
            raise ConflictError("first-frame materialization binding failed")
        prepared = self.repository.get_run_event(record["preparation_id"])
        source = prepared.payload
        if (prepared.run_id != run_id or prepared.event_type != "image_task_prepared"
                or source.get("run_id") != run_id or source.get("image_task_key") != image_key
                or source.get("record_sha256") != digest({k: v for k, v in source.items() if k != "record_sha256"})
                or source.get("preparation_sha256") != record.get("preparation_sha256")
                or source.get("preparation_sha256") != digest({k: v for k, v in source.items()
                    if k not in {"record_sha256", "preparation_sha256"}})
                or source.get("approved_plan_event_id") != incoming.approved_plan_event_id
                or source.get("approved_plan_sha256") != incoming.approved_plan_sha256
                or source.get("request_sha256") != image.get("request_sha256")):
            raise ConflictError("first-frame source binding failed")
        return {"approved_frame_review_id": review.id, "approved_frame_review_sha256": record["review_sha256"],
                "frame_materialization_id": materialized.id}

    def _plan_binding(self, run_id, incoming, package_sha, package=None):
        plans = [event for event in self.repository.list_run_events(run_id)
                 if event.event_type in {"shot_plan_drafted", "shot_plan_revised", "shot_plan_approved"}]
        if not plans:
            if incoming.approved_plan_event_id or incoming.approved_plan_sha256:
                raise ConflictError("named shot approval does not exist in this run")
            return {}  # Existing professional imports without the interactive planner remain supported.
        current = plans[-1]
        record = current.payload
        expected = digest({k: v for k, v in record.items() if k != "plan_sha256"})
        if (current.event_type != "shot_plan_approved" or record.get("approved") is not True
                or incoming.approved_plan_event_id != current.id
                or incoming.approved_plan_sha256 != expected or record.get("plan_sha256") != expected
                or record.get("production_package_sha256") != package_sha):
            raise ConflictError("current shot plan must be confirmed and bound to this request")
        try:
            tasks = record["tasks"]
            matches = [task for task in tasks if task["task_key"] == incoming.task_key]
            if len(matches) != 1:
                raise ValueError("unknown task")
            index = matches[0]["shot_index"]
            if type(index) is not int or index < 0:
                raise ValueError("invalid index")
            shot = record["plan"]["shots"][index]
            prompt = shot["video_prompt"]
            if (not isinstance(prompt, str) or not prompt.strip()
                    or prompt not in incoming.request.get("prompt", "")
                    or incoming.request.get("duration_seconds") != shot["duration_seconds"]):
                raise ValueError("request differs from reviewed shot")
        except (ValueError, TypeError, KeyError, IndexError):
            raise ConflictError("video request does not preserve the reviewed shot and duration") from None
        if shot.get("director") is not None:
            apply_reviewed_director(incoming.request, DirectorDraft.model_validate(shot["director"]), index)
            if package is not None:
                scope = compile_identity_scope(record["plan"], shot, package, package_sha)
                supplied = incoming.request.get("provider_scope_projection")
                if supplied is not None and supplied != scope:
                    raise ConflictError("provider scope differs from the reviewed project characters")
                incoming.request["provider_scope_projection"] = scope
        elif record["plan"].get("visual_assets"):
            raise ConflictError("reviewed shot is missing its director choices; finish the creative revision first")
        return {"approved_plan_event_id": current.id, "approved_plan_sha256": expected,
                "approved_shot_index": index}
