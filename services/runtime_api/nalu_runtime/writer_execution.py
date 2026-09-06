"""Durable runtime-owned writer invocation; no client response-import operation."""

import hashlib
import json
from collections.abc import Callable

from .database import Database
from .repository import ConflictError, NotFoundError, utc_now


class WriterExecution:
    def __init__(self, database: Database):
        self.database = database

    def execute(
        self, project_id: str, turn_id: str, request_body: bytes,
        *, destination: str, transport: Callable[[bytes], bytes],
    ) -> bytes:
        """Caller is trusted runtime code, never an HTTP-supplied callback.

        Destination and request must be compiled/validated by that caller. Only
        transport's actual response can complete an attempt. There is no retry of
        submitting/ambiguous attempts and no provider-verification claim here.
        """
        if not turn_id or len(turn_id) > 120 or not destination:
            raise ValueError("invalid writer execution identity")
        digest = hashlib.sha256(destination.encode() + b"\0" + request_body).hexdigest()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project = connection.execute(
                "SELECT archived_at FROM projects WHERE id=?", (project_id,)
            ).fetchone()
            if project is None:
                raise NotFoundError("project not found")
            if project["archived_at"]:
                raise ConflictError("archived project is read-only")
            existing = connection.execute(
                "SELECT * FROM writer_executions WHERE project_id=? AND turn_id=?",
                (project_id, turn_id),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != digest:
                    raise ConflictError("writer turn already belongs to another request")
                if existing["state"] != "completed":
                    raise ConflictError("writer outcome unresolved; automatic replay is prohibited")
                raw = existing["response_json"].encode()
                if hashlib.sha256(raw).hexdigest() != existing["response_sha256"]:
                    raise ConflictError("stored writer response integrity failed")
                return raw
            connection.execute(
                "INSERT INTO writer_executions VALUES (?, ?, ?, 'submitting', NULL, NULL, ?, NULL)",
                (project_id, turn_id, digest, utc_now()),
            )
        # The transaction commits before network I/O, including on process loss.
        try:
            raw = transport(request_body)
            if not isinstance(raw, bytes) or not 0 < len(raw) <= 2_000_000:
                raise ValueError("invalid writer response size")
            text = raw.decode("utf-8")
            if not isinstance(json.loads(text), dict):
                raise TypeError("writer response must be an object")
            with self.database.connect() as connection:
                changed = connection.execute(
                    """UPDATE writer_executions SET state='completed', response_json=?,
                       response_sha256=?, completed_at=?
                       WHERE project_id=? AND turn_id=? AND state='submitting'
                       AND request_sha256=?""",
                    (text, hashlib.sha256(raw).hexdigest(), utc_now(), project_id, turn_id, digest),
                ).rowcount
                if changed != 1:
                    raise ConflictError("writer execution changed while request was in flight")
            return raw
        except Exception:
            # Never persist exception strings: transports may include credentials.
            with self.database.connect() as connection:
                connection.execute(
                    """UPDATE writer_executions SET state='ambiguous'
                       WHERE project_id=? AND turn_id=? AND state='submitting'""",
                    (project_id, turn_id),
                )
            raise
