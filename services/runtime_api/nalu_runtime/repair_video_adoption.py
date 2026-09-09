"""Explicit, version-bound reuse decisions; no provider authority is transferred."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .repair_video_candidates import repair_video_candidates
from .repository import ConflictError, encode, new_id, utc_now
from .shot_planning import ShotPlanningService
from .shot_review import ShotReviewService
from .video_preparation import digest
from .video_tail import VideoTailService


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


def read_repair_clip(repo, data_root, run_id, review_id):
    """Revalidate a stored decision for editing, never a new provider submission."""
    event = repo.get_run_event(review_id)
    payload = event.payload
    if (event.run_id != run_id or event.event_type != "repair_video_reviewed"
            or payload.get("adopted") is not True or payload.get("decision") != "accept"
            or payload.get("review_sha256") != digest({k: v for k, v in payload.items() if k != "review_sha256"})):
        raise ConflictError("repair clip is not currently adopted")
    decisions = [e for e in repo.list_run_events(run_id) if e.event_type == "repair_video_reviewed"
                 and e.payload.get("shot_index") == payload["shot_index"]]
    if not decisions or decisions[-1].id != event.id:
        raise ConflictError("repair clip decision has changed")
    package = ShotPlanningService(repo)._package(repo.get_run(run_id), _read_saved=True)
    plan = ShotReviewService(repo).current(run_id)
    if (plan is None or plan.event_type != "shot_plan_approved" or plan.payload.get("approved") is not True
            or plan.id != payload["plan_id"] or plan.payload.get("plan_sha256") != payload["plan_sha256"]
            or plan.payload.get("plan_sha256") != digest({k: v for k, v in plan.payload.items() if k != "plan_sha256"})
            or plan.payload.get("production_package_sha256") != package["package_sha256"]):
        raise ConflictError("repair plan changed after clip adoption")
    selected = payload["candidate"]
    source_id = package.get("production_policy", {}).get("repair_lineage", {}).get("source_run_id")
    if not source_id or source_id != selected["source_run_id"]:
        raise ConflictError("repair clip belongs to another source")
    source_review, media, raw = VideoTailService(repo, data_root).accepted_video(
        source_id, selected["source_review_id"], _repair_target=run_id)
    if (source_review.payload["review_sha256"] != selected["source_review_sha256"]
            or media.id != selected["materialization_id"]
            or media.payload["video"]["sha256"] != selected["video_sha256"]):
        raise ConflictError("original adopted clip changed")
    return source_review, media, raw
