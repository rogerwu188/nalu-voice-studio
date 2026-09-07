"""Bind a user's shot decision to decoded media and its current production inputs."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .repository import ConflictError, encode, new_id, utc_now
from .video_materialization import VideoMaterializationService
from .video_preparation import VideoPreparationRequest, VideoPreparationService, digest


class VideoReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    preparation_id: str = Field(min_length=1, max_length=160)
    expected_materialization_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_event_id: str | None = None
    decision: Literal["accept", "reject"]
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)


class VideoReviewService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def review(self, run_id, materialization_id, incoming: VideoReviewRequest):
        repo = self.repository
        request_sha = digest({"materialization_id": materialization_id, "request": incoming.model_dump()})
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            event, _ = VideoMaterializationService(repo, self.data_root).read_saved(run_id, materialization_id)
            media = event.payload
            if media["materialization_sha256"] != incoming.expected_materialization_sha256:
                raise ConflictError("video changed; reload before reviewing")
            prepared = repo.get_run_event(incoming.preparation_id)
            saved = prepared.payload
            if (prepared.run_id != run_id or prepared.event_type != "video_task_prepared"
                    or saved.get("preparation_sha256") != digest({k: v for k, v in saved.items() if k != "preparation_sha256"})):
                raise ConflictError("video preparation integrity failed")
            source = VideoPreparationRequest.model_validate({k: saved[k] for k in VideoPreparationRequest.model_fields if k in saved})
            current = VideoPreparationService(repo, self.data_root).validate(run_id, source)
            if (current["preparation_sha256"] != saved["preparation_sha256"]
                    or current["request_sha256"] != media["request_sha256"] or current["task_key"] != media["task_key"]):
                raise ConflictError("video no longer matches this shot's confirmed production inputs")
            if incoming.decision == "accept":
                video = media["video"]
                width, height = (int(part) for part in current["request"]["video_transport"]["aspect_ratio"].split(":"))
                if (abs(video["width"] / video["height"] - width / height) > 0.01
                        or abs(video["duration_seconds"] - current["request"]["duration_seconds"]) > 0.25):
                    raise ConflictError("video duration or framing differs from the confirmed shot")
            rows = db.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
            reviews = [row for row in rows if row["event_type"] == "video_shot_reviewed"
                       and json.loads(row["payload_json"]).get("task_key") == media["task_key"]]
            latest = reviews[-1] if reviews else None
            if latest:
                prior = json.loads(latest["payload_json"])
                if prior.get("review_sha256") != digest({k: v for k, v in prior.items() if k != "review_sha256"}):
                    raise ConflictError("previous video review integrity failed")
                if prior.get("review_request_sha256") == request_sha:
                    return repo.get_run_event(latest["id"])
            if incoming.expected_review_event_id != (latest["id"] if latest else None):
                raise ConflictError("shot review changed; reload before deciding again")
            # Until downstream receipt consumers are wired, do not allow a decision
            # to silently invalidate an already materialized episode.
            if any("postproduction" in row["event_type"] or "master" in row["event_type"] for row in rows):
                raise ConflictError("episode postproduction exists; reconcile it before changing this shot")
            record = {"run_id": run_id, "task_key": media["task_key"], "materialization_id": materialization_id,
                      "materialization_sha256": media["materialization_sha256"], "video_sha256": media["video"]["sha256"],
                      "preparation_id": prepared.id, "preparation_sha256": saved["preparation_sha256"],
                      "approved_plan_event_id": current.get("approved_plan_event_id"),
                      "approved_plan_sha256": current.get("approved_plan_sha256"),
                      "request_sha256": media["request_sha256"], "binding_id": media["binding_id"],
                      "review_request_sha256": request_sha, "decision": incoming.decision,
                      "reviewed_by": incoming.reviewed_by, "confirmation": incoming.confirmation,
                      "user_approved": incoming.decision == "accept", "visual_semantics_verified": False,
                      "audio_verified": False, "billing_verified": False, "master_accepted": False,
                      "generation_performed": False}
            record["review_sha256"] = digest(record)
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, run_id, sequence,
                "video_shot_reviewed", None, None, "User reviewed this exact shot video; professional QA remains separate.",
                encode(record), utc_now()))
        return repo.get_run_event(event_id)
