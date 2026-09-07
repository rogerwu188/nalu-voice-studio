"""Derive a true final frame from a currently accepted, immutable shot video."""

import hashlib
import io
import json

import av

from .repository import ConflictError, encode, new_id, utc_now
from .video_materialization import VideoMaterializationService
from .video_preparation import VideoPreparationRequest, VideoPreparationService, digest


class VideoTailService:
    def __init__(self, repository, data_root):
        self.repository, self.data_root = repository, data_root

    def _derive(self, run_id, review_id):
        repo = self.repository
        review = repo.get_run_event(review_id)
        decision = review.payload
        if (review.run_id != run_id or review.event_type != "video_shot_reviewed"
                or decision.get("decision") != "accept" or decision.get("user_approved") is not True
                or decision.get("review_sha256") != digest({k: v for k, v in decision.items() if k != "review_sha256"})):
            raise ConflictError("tail frame requires an accepted video review")
        current = [e for e in repo.list_run_events(run_id) if e.event_type == "video_shot_reviewed"
                   and e.payload.get("task_key") == decision["task_key"]]
        if not current or current[-1].id != review_id:
            raise ConflictError("video decision changed; previous tail frame cannot be used")
        media, raw = VideoMaterializationService(repo, self.data_root).read_saved(run_id, decision["materialization_id"])
        if (media.payload["materialization_sha256"] != decision["materialization_sha256"]
                or media.payload["video"]["sha256"] != decision["video_sha256"]
                or media.payload["request_sha256"] != decision["request_sha256"]
                or media.payload["task_key"] != decision["task_key"]):
            raise ConflictError("accepted video lineage changed")
        prepared = repo.get_run_event(decision["preparation_id"])
        saved = prepared.payload
        if (prepared.run_id != run_id or prepared.event_type != "video_task_prepared"
                or saved.get("preparation_sha256") != decision["preparation_sha256"]
                or saved.get("preparation_sha256") != digest({k: v for k, v in saved.items() if k != "preparation_sha256"})):
            raise ConflictError("accepted preparation changed")
        request = VideoPreparationRequest.model_validate({k: saved[k] for k in VideoPreparationRequest.model_fields if k in saved})
        validated = VideoPreparationService(repo, self.data_root).validate(run_id, request)
        if validated["preparation_sha256"] != decision["preparation_sha256"]:
            raise ConflictError("accepted shot inputs changed")
        # read_saved already performs bounded full video decoding. Decode the
        # same in-memory bytes, never seek to a guessed end or generate a frame.
        try:
            last, count = None, 0
            with av.open(io.BytesIO(raw), format="mp4", options={"protocol_whitelist": "pipe", "enable_drefs": "0"}) as video:
                for frame in video.decode(video.streams.video[0]):
                    last, count = frame, count + 1
                if last is None or count != media.payload["video"]["decoded_frame_count"]:
                    raise ValueError("frame count changed")
                encoder = av.CodecContext.create("png", "w")
                encoder.width, encoder.height, encoder.pix_fmt = last.width, last.height, "rgb24"
                png = b"".join(bytes(packet) for packet in encoder.encode(last.reformat(format="rgb24")))
                png += b"".join(bytes(packet) for packet in encoder.encode(None))
                if not png.startswith(b"\x89PNG"):
                    raise ValueError("invalid encoded frame")
                record = {"run_id": run_id, "task_key": decision["task_key"], "review_id": review_id,
                          "review_sha256": decision["review_sha256"], "materialization_id": media.id,
                          "video_sha256": decision["video_sha256"], "frame_index": count - 1,
                          "time_seconds": last.time, "width": last.width, "height": last.height,
                          "frame_sha256": hashlib.sha256(png).hexdigest(), "byte_size": len(png),
                          "source": "DECODED_ACCEPTED_VIDEO_FINAL_FRAME", "generation_performed": False,
                          "visual_semantics_verified": False, "master_accepted": False}
        except Exception:  # noqa: BLE001 -- decoder errors may contain private media diagnostics
            raise ConflictError("accepted video final frame cannot be decoded") from None
        record["tail_sha256"] = digest(record)
        return record, png

    def extract(self, run_id, review_id):
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            record, _ = self._derive(run_id, review_id)
            rows = db.execute("SELECT id,payload_json FROM run_events WHERE run_id=? AND event_type='video_tail_extracted'", (run_id,)).fetchall()
            for row in rows:
                if json.loads(row["payload_json"]) == record:
                    return self.repository.get_run_event(row["id"])
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, run_id, sequence,
                "video_tail_extracted", None, None, "Final decoded frame bound to the current video decision.", encode(record), utc_now()))
        return self.repository.get_run_event(event_id)

    def read_saved(self, run_id, tail_id):
        event = self.repository.get_run_event(tail_id)
        if event.run_id != run_id or event.event_type != "video_tail_extracted":
            raise ConflictError("tail receipt belongs to another video")
        record, png = self._derive(run_id, event.payload["review_id"])
        if record != event.payload:
            raise ConflictError("tail frame changed; reconcile before continuing")
        return event, png
