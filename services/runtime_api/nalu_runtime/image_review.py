"""User frame decisions are version-bound observations, not automatic professional QA."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .asset_service import AssetService
from .image_materialization import ImageMaterializationService
from .image_preparation import ImagePreparationRequest, ImagePreparationService
from .repository import ConflictError, Repository, encode, new_id, utc_now
from .video_preparation import digest


class ImageReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    preparation_id: str
    expected_materialization_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_event_id: str | None = None
    decision: Literal["accept", "reject"]
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)


class ImageReviewService:
    def __init__(self, repository: Repository, assets: AssetService, data_root):
        self.repository, self.assets, self.data_root = repository, assets, data_root

    def review(self, run_id, materialization_id, incoming: ImageReviewRequest):
        review_sha = digest({"materialization_id": materialization_id, "request": incoming.model_dump()})
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            materialized, _ = ImageMaterializationService(self.repository, self.data_root).read_saved(run_id, materialization_id)
            image = materialized.payload
            if image["materialization_sha256"] != incoming.expected_materialization_sha256:
                raise ConflictError("image changed; reload before reviewing")
            prepared = self.repository.get_run_event(incoming.preparation_id)
            if prepared.run_id != run_id or prepared.event_type != "image_task_prepared":
                raise ConflictError("image preparation does not belong to this run")
            saved = prepared.payload
            if saved.get("record_sha256") != digest({k: v for k, v in saved.items() if k != "record_sha256"}):
                raise ConflictError("image preparation integrity failed")
            source = ImagePreparationRequest.model_validate({key: saved[key] for key in ImagePreparationRequest.model_fields if key in saved})
            current, _ = ImagePreparationService(self.repository, self.assets).materialize(run_id, source)
            if (current["preparation_sha256"] != saved.get("preparation_sha256")
                    or current["request_sha256"] != image["request_sha256"]
                    or current["image_task_key"] != image["task_key"]):
                raise ConflictError("image no longer matches the confirmed shot and references")
            ratio_width, ratio_height = (int(part) for part in current["aspect_ratio"].split(":"))
            if incoming.decision == "accept" and abs(image["image"]["width"] / image["image"]["height"] - ratio_width / ratio_height) > 0.01:
                raise ConflictError("image framing differs from the reviewed production ratio")
            rows = db.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
            reviews = [row for row in rows if row["event_type"] == "image_frame_reviewed"
                       and json.loads(row["payload_json"]).get("task_key") == image["task_key"]]
            latest = reviews[-1] if reviews else None
            if latest:
                previous = json.loads(latest["payload_json"])
                if previous.get("review_sha256") != digest({k: v for k, v in previous.items() if k != "review_sha256"}):
                    raise ConflictError("previous image review integrity failed")
            if latest and json.loads(latest["payload_json"]).get("review_request_sha256") == review_sha:
                return self.repository.get_run_event(latest["id"])
            if incoming.expected_review_event_id != (latest["id"] if latest else None):
                raise ConflictError("frame review changed; reload before another decision")
            if any(row["event_type"] in {"video_task_prepared", "video_estimate_reserved"} for row in rows):
                raise ConflictError("video preparation has started; reconcile downstream work before changing frame review")
            if db.execute("SELECT 1 FROM remote_task_bindings WHERE run_id=? LIMIT 1", (run_id,)).fetchone():
                raise ConflictError("provider video work exists; reconcile before changing frame review")
            record = {"run_id": run_id, "task_key": image["task_key"], "materialization_id": materialization_id,
                      "materialization_sha256": image["materialization_sha256"], "image_sha256": image["image"]["sha256"],
                      "preparation_id": prepared.id, "preparation_sha256": saved["preparation_sha256"],
                      "approved_plan_event_id": current["approved_plan_event_id"],
                      "approved_plan_sha256": current["approved_plan_sha256"],
                      "review_request_sha256": review_sha, "decision": incoming.decision,
                      "reviewed_by": incoming.reviewed_by, "confirmation": incoming.confirmation,
                      "user_approved": incoming.decision == "accept", "visual_semantics_verified": False,
                      "paid_approved": False, "generation_performed": False}
            record["review_sha256"] = digest(record)
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, run_id, sequence,
                "image_frame_reviewed", None, None, "User reviewed the exact saved image; professional QA and paid approval remain separate.",
                encode(record), utc_now()))
        return self.repository.get_run_event(event_id)
