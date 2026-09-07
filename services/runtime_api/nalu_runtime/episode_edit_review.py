"""Explicit edit review bound to the exact locally rendered proxy receipt."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .episode_preview import EpisodePreviewService
from .repository import ConflictError, encode, new_id, utc_now
from .video_preparation import digest


class EpisodeEditReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_edit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_id: str = Field(min_length=1, max_length=160)
    expected_preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=160)
    decision: Literal["accept", "reject"]
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)


class EpisodeEditReviewService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def approved(self, run_id, edit_id, edit_sha256, review_id):
        """Resolve current approved timing; caller holds the writer transaction."""
        edit, _, _, _ = EpisodePreviewService(self.repository, self.data_root).inputs(run_id, edit_id, edit_sha256)
        reviews = [event for event in self.repository.list_run_events(run_id)
                   if event.event_type == "postproduction_edit_reviewed" and event.payload.get("edit_id") == edit_id]
        current = reviews[-1] if reviews else None
        if current is None or current.id != review_id:
            raise ConflictError("reload the current edit confirmation before postproduction")
        payload = current.payload
        if (payload.get("review_sha256") != digest({k: v for k, v in payload.items() if k != "review_sha256"})
                or payload.get("decision") != "accept" or payload.get("edit_approved") is not True
                or payload.get("edit_sha256") != edit_sha256
                or payload.get("duration_confirmed_seconds") != edit.payload["edited_duration_seconds"]):
            raise ConflictError("postproduction requires an intact accepted edit confirmation")
        preview = self.repository.get_run_event(payload["preview_id"])
        receipt = preview.payload
        if (preview.run_id != run_id or preview.event_type != "episode_picture_preview_rendered"
                or receipt.get("receipt_sha256") != digest({k: v for k, v in receipt.items() if k != "receipt_sha256"})
                or receipt.get("receipt_sha256") != payload.get("preview_receipt_sha256")
                or receipt.get("preview_sha256") != payload.get("preview_sha256")
                or receipt.get("edit_id") != edit_id or receipt.get("edit_sha256") != edit_sha256
                or receipt.get("duration_seconds") != payload["duration_confirmed_seconds"]):
            raise ConflictError("confirmed preview receipt changed before postproduction")
        return current

    def review(self, run_id, edit_id, request):
        repo = self.repository
        request_sha = digest({"edit_id": edit_id, "request": request.model_dump()})
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            edit, _, _, _ = EpisodePreviewService(repo, self.data_root).inputs(run_id, edit_id, request.expected_edit_sha256)
            preview = repo.get_run_event(request.preview_id)
            payload = preview.payload
            if (preview.run_id != run_id or preview.event_type != "episode_picture_preview_rendered"
                    or payload.get("receipt_sha256") != digest({k: v for k, v in payload.items() if k != "receipt_sha256"})
                    or payload.get("edit_id") != edit_id or payload.get("edit_sha256") != request.expected_edit_sha256
                    or payload.get("preview_sha256") != request.expected_preview_sha256
                    or payload.get("duration_seconds") != edit.payload["edited_duration_seconds"]):
                raise ConflictError("review must refer to the exact rendered edit preview")
            events = repo.list_run_events(run_id)
            reviews = [e for e in events if e.event_type == "postproduction_edit_reviewed" and e.payload.get("edit_id") == edit_id]
            current = reviews[-1] if reviews else None
            if current is not None and current.payload.get("review_sha256") != digest({k: v for k, v in current.payload.items() if k != "review_sha256"}):
                raise ConflictError("saved edit review integrity failed")
            if current is not None and current.payload.get("request_sha256") == request_sha:
                return current
            if (current.id if current else None) != request.expected_review_id:
                raise ConflictError("edit decision changed; reload before confirming")
            if any(e.event_type == "postproduction_materialized" or "master" in e.event_type for e in events):
                raise ConflictError("downstream master work exists; reconcile before changing edit approval")
            record = {"edit_id": edit_id, "edit_sha256": request.expected_edit_sha256,
                      "preview_id": preview.id, "preview_sha256": request.expected_preview_sha256,
                      "preview_receipt_sha256": payload["receipt_sha256"], "request_sha256": request_sha,
                      "decision": request.decision, "reviewed_by": request.reviewed_by, "confirmation": request.confirmation,
                      "edit_approved": request.decision == "accept", "duration_confirmed_seconds": edit.payload["edited_duration_seconds"],
                      "original_planned_seconds": edit.payload["planned_duration_seconds"],
                      "viewing_evidence": "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY", "audio_approved": False,
                      "captions_approved": False, "master_accepted": False, "generation_performed": False}
            record["review_sha256"] = digest(record)
            identity = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                "postproduction_edit_reviewed", None, None, "Explicit picture-edit decision saved; final audio/master QA remains required.",
                encode(record), utc_now()))
        return repo.get_run_event(identity)
