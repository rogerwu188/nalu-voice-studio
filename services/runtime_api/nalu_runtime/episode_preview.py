"""Local, transient picture-only edit preview; never a release master."""

import hashlib
import tempfile
import time
from pathlib import Path
from threading import BoundedSemaphore

from pydantic import BaseModel, ConfigDict, Field

from .models import PostproductionShotSource
from .postproduction_materializer import _encode_mp4, _safe_input, _selected_frames
from .repair_video_adoption import read_repair_clip
from .repository import ConflictError, encode, new_id, utc_now
from .shot_review import ShotReviewService
from .video_preparation import digest
from .video_tail import VideoTailService

PREVIEW_SLOT = BoundedSemaphore(1)


class EpisodePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_edit_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EpisodePreviewService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, Path(data_root).resolve()

    def inputs(self, run_id, edit_id, expected_sha):
        repo = self.repository
        run = repo.get_run(run_id)
        if str(run.status) in {"cancelled", "failed"} or repo.get_project(run.project_id).archived_at:
            raise ConflictError("episode is not available for preview")
        edits = [e for e in repo.list_run_events(run_id) if e.event_type == "postproduction_edit_drafted"]
        edit = edits[-1] if edits else None
        plan = ShotReviewService(repo).current(run_id)
        if (edit is None or edit.id != edit_id or edit.payload.get("edit_sha256") != expected_sha
                or digest({k: v for k, v in edit.payload.items() if k != "edit_sha256"}) != expected_sha
                or plan is None or plan.id != edit.payload.get("plan_id")
                or plan.payload.get("plan_sha256") != edit.payload.get("plan_sha256")):
            raise ConflictError("preview requires the current exact edit")
        package = Path(run.package_path).absolute()
        if not package.is_relative_to(self.data_root / "runs") or package.resolve() != package:
            raise ConflictError("preview source is outside managed run storage")
        root = package.parent / "qingshan-workspace/exports"
        sources = [PostproductionShotSource.model_validate(s) for s in edit.payload["shots"]]
        items = edit.payload["items"]
        if len(sources) != len(items) or not sources or edit.payload["frame_rate"] != 24:
            raise ConflictError("edited source inventory is inconsistent")
        paths, geometry = [], None
        for source, item in zip(sources, items, strict=True):
            if item.get("repair_review_id"):
                review, media, _ = read_repair_clip(repo, self.data_root, run_id, item["repair_review_id"])
                if review.run_id != item.get("source_run_id") or review.id != item["review_id"]:
                    raise ConflictError("repair preview source changed")
            else:
                review, media, _ = VideoTailService(repo, self.data_root).accepted_video(run_id, item["review_id"])
            if (review.payload["review_sha256"] != item["review_sha256"] or media.id != item["materialization_id"]
                    or source.source_sha256 != media.payload["video"]["sha256"] or source.shot_id != item["task_key"]):
                raise ConflictError("adopted preview source changed")
            if geometry is None:
                video = media.payload["video"]
                scale = min(640 / video["width"], 640 / video["height"], 1)
                geometry = (max(2, int(video["width"] * scale) // 2 * 2), max(2, int(video["height"] * scale) // 2 * 2))
            paths.append(_safe_input(root, source.source_relative_path, source.source_sha256))
        return edit, sources, paths, geometry

    def render(self, run_id, edit_id, expected_sha):
        if not PREVIEW_SLOT.acquire(blocking=False):
            raise ConflictError("another local picture preview is rendering; try again when it finishes")
        try:
            return self._render(run_id, edit_id, expected_sha)
        finally:
            PREVIEW_SLOT.release()

    def _render(self, run_id, edit_id, expected_sha):
        edit, sources, paths, geometry = self.inputs(run_id, edit_id, expected_sha)
        width, height = geometry
        started, last_check = time.monotonic(), 0.0
        def cancelled():
            nonlocal last_check
            now = time.monotonic()
            if now - started > 300:
                return True
            if now - last_check > 1:
                last_check = now
                return str(self.repository.get_run(run_id).status) in {"cancelled", "failed"}
            return False
        with tempfile.TemporaryDirectory(prefix="nalu-edit-preview-") as temporary:
            output = Path(temporary) / "picture-preview.mp4"
            output.touch(mode=0o600)
            def frames():
                for source, path in zip(sources, paths, strict=True):
                    duration = round((source.source_out_seconds - source.source_in_seconds) * 24) / 24
                    for frame in _selected_frames(path, start_seconds=source.source_in_seconds,
                            duration_seconds=duration, frame_rate=24, width=width, height=height,
                            pixel_format="yuv420p", should_cancel=cancelled):
                        if output.exists() and output.stat().st_size > 128_000_000:
                            raise ConflictError("preview exceeds the bounded local output size")
                        yield frame
            count = _encode_mp4(output, frames=frames(), audio_chunks=(), width=width, height=height,
                frame_rate=24, pixel_format="yuv420p", should_cancel=cancelled)
            if count != sum(t["frame_count"] for t in edit.payload["timeline"]) or output.stat().st_size > 128_000_000:
                raise ConflictError("preview does not match the saved edit timeline")
            # A changed plan, decision, source file or cancellation invalidates the result.
            self.inputs(run_id, edit_id, expected_sha)
            raw = output.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        record = {"edit_id": edit_id, "edit_sha256": expected_sha, "preview_sha256": sha,
                  "byte_size": len(raw), "frame_count": count, "duration_seconds": count / 24,
                  "width": width, "height": height, "audio": "none", "master_accepted": False,
                  "generation_performed": False, "viewing_verified": False}
        record["receipt_sha256"] = digest(record)
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.inputs(run_id, edit_id, expected_sha)
            previous = [e for e in self.repository.list_run_events(run_id)
                        if e.event_type == "episode_picture_preview_rendered" and e.payload == record]
            if previous:
                identity = previous[-1].id
            else:
                identity = new_id("evt")
                sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
                db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (identity, run_id, sequence,
                    "episode_picture_preview_rendered", None, None,
                    "Picture-only proxy rendered; user viewing and approval are not inferred.", encode(record), utc_now()))
        return raw, sha, identity
