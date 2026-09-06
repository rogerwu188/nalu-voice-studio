"""Single-attempt image submission using backup-preserved SQLite run events."""

import hashlib
import json
import re
from collections.abc import Callable

import httpx

from .giggle_image_transport import GiggleImageTransport, ImageAcceptanceUnconfirmed, image_payload
from .repository import ConflictError, Repository, encode, new_id, utc_now
from .video_preparation import digest

IMAGE_EVENTS = {"image_submit_intent", "image_submit_unconfirmed", "image_task_submitted"}


class ImageSubmissionService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def _eligible(self, run_id):
        run = self.repository.get_run(run_id)
        if (run.dry_run or run.status != "waiting_for_approval"
                or self.repository.get_project(run.project_id).archived_at):
            raise ConflictError("image submission requires an active paid-approval run")
        latest = self.repository.latest_run_for_episode(run.episode_id)
        if not latest or latest.id != run_id:
            raise ConflictError("image submission belongs to an obsolete run")

    def _latest(self, db, run_id, task_key):
        rows = db.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
        match = None
        for row in rows:
            if row["event_type"] not in IMAGE_EVENTS:
                continue
            payload = json.loads(row["payload_json"])
            if payload.get("task_key") != task_key:
                continue
            if (payload.get("run_id") != run_id or payload.get("record_sha256") !=
                    digest({k: v for k, v in payload.items() if k != "record_sha256"})):
                raise ConflictError("image intent integrity or import reconciliation required")
            match = row, payload
        return match

    def _append(self, db, run_id, kind, payload):
        event_id = new_id("evt")
        payload = {k: v for k, v in payload.items() if k != "record_sha256"}
        payload["record_sha256"] = digest(payload)
        sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
        db.execute("INSERT INTO run_events VALUES (?,?,?,?,?,?,?,?,?)",
                   (event_id, run_id, sequence, kind, None, None,
                    "Image submission observation; no image or billing completion claimed.", encode(payload), utc_now()))
        return event_id

    def submit(self, run_id: str, task_key: str, request: dict, *, secret: Callable[[], str],
               authorize: Callable[[str, str, str], None], transport: httpx.BaseTransport | None = None):
        """Trusted runtime caller must verify scope, entry state and exact cost approval.

        The callback performs local read-only validation (no provider I/O or writes).
        No HTTP caller can supply this callback. It is required, with no permissive
        default. This service is not exposed until the concrete authority path exists.
        """
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", task_key):
            raise ConflictError("invalid image task identity")
        self.repository.get_run(run_id)
        endpoint, payload = image_payload(request)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        request_sha = hashlib.sha256(endpoint.encode() + b"\0" + raw).hexdigest()
        intent_id = digest({"run_id": run_id, "task_key": task_key, "kind": "image"})
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = self._latest(db, run_id, task_key)
            if existing:
                if existing[1]["request_sha256"] != request_sha:
                    raise ConflictError("image task already binds another request; reconcile before a new attempt")
                return self.repository.get_run_event(existing[0]["id"])
            self._eligible(run_id)
            authorize(run_id, task_key, request_sha)
            record = {"run_id": run_id, "task_key": task_key, "intent_id": intent_id,
                      "endpoint": endpoint, "request_sha256": request_sha,
                      "state": "submission_unconfirmed", "automatic_resubmit": False,
                      "image_generated": False, "billing_verified": False}
            intent_event = self._append(db, run_id, "image_submit_intent", record)
        # A crash from this point onward cannot lead to another POST on restart.
        def authorize_transport(identity, actual_sha):
            if identity != intent_id or actual_sha != request_sha:
                raise ConflictError("image transport changed after durable intent")
            self._eligible(run_id)
            authorize(run_id, task_key, request_sha)
            with self.repository.db.connect() as db:
                current = self._latest(db, run_id, task_key)
                if not current or current[0]["id"] != intent_event:
                    raise ConflictError("image intent changed before HTTP")
        try:
            receipt = GiggleImageTransport(secret, authorize=authorize_transport, transport=transport).submit(
                payload, intent_id=intent_id)
        except (ImageAcceptanceUnconfirmed, ConflictError):
            with self.repository.db.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._latest(db, run_id, task_key)
                if current and current[0]["id"] == intent_event:
                    event_id = self._append(db, run_id, "image_submit_unconfirmed", record)
                else:
                    raise ConflictError("image outcome requires reconciliation") from None
            return self.repository.get_run_event(event_id)
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._latest(db, run_id, task_key)
            if not current or current[0]["id"] != intent_event:
                raise ConflictError("image receipt cannot replace changed intent")
            event_id = self._append(db, run_id, "image_task_submitted",
                                    {**record, "state": "submitted", "receipt": receipt,
                                     "provider_task_id": receipt["provider_task_id"]})
        return self.repository.get_run_event(event_id)
