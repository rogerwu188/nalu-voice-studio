"""Explicit, version-bound reuse decisions; no provider authority is transferred."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .repair_video_candidates import repair_video_candidates
from .repository import ConflictError, encode, new_id, utc_now
from .shot_review import ShotReviewService
from .video_preparation import digest


class RepairVideoReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_candidates_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shot_index: int = Field(strict=True, ge=0, le=119)
    expected_review_id: str | None = Field(default=None, min_length=1, max_length=160)
    decision: Literal["accept", "reject"]
    reviewed_by: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=2000)


def review_repair_video(production, run_id, request):
    repo = production.repository
    request_sha = digest(request.model_dump())
    with repo.db.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        candidates = repair_video_candidates(production, run_id)
        if candidates["candidates_sha256"] != request.expected_candidates_sha256:
            raise ConflictError("repair candidates changed; review the current clips")
        plan = ShotReviewService(repo).current(run_id)
        if plan.event_type != "shot_plan_approved" or plan.payload.get("approved") is not True:
            raise ConflictError("confirm the repair shot plan before adopting clips")
        selected = next((i for i in candidates["items"] if i["shot_index"] == request.shot_index), None)
        if selected is None or selected["status"] != "available_for_review":
            raise ConflictError("original clip is unavailable for repair review")
        events = repo.list_run_events(run_id)
        reviews = [e for e in events if e.event_type == "repair_video_reviewed"
                   and e.payload.get("shot_index") == request.shot_index]
        current = reviews[-1] if reviews else None
        if current is not None:
            if current.payload.get("review_sha256") != digest({
                    k: v for k, v in current.payload.items() if k != "review_sha256"}):
                raise ConflictError("saved repair decision changed")
            if current.payload.get("request_sha256") == request_sha:
                return current
        if (current.id if current else None) != request.expected_review_id:
            raise ConflictError("repair decision changed; reload before confirming")
        if any(e.event_type.startswith(("postproduction_", "episode_picture_")) for e in events):
            raise ConflictError("repair editing already exists; reconcile before changing clip decisions")
        payload = {"shot_index": request.shot_index, "candidate": selected,
                   "plan_id": plan.id, "plan_sha256": plan.payload["plan_sha256"],
                   "candidates_sha256": candidates["candidates_sha256"],
                   "request_sha256": request_sha, "decision": request.decision,
                   "reviewed_by": request.reviewed_by, "confirmation": request.confirmation,
                   "viewing_evidence": "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY",
                   "adopted": request.decision == "accept", "generation_performed": False,
                   "paid_approved": False, "master_accepted": False}
        payload["review_sha256"] = digest(payload)
        identity = new_id("evt")
        sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
        db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (
            identity, run_id, sequence, "repair_video_reviewed", None, None,
            "Explicit original-clip reuse decision; no provider submission or final acceptance.",
            encode(payload), utc_now()))
    return repo.get_run_event(identity)
