"""Read-only project-scoped binding to a locally observed writer response."""

import hashlib
import json

from .database import Database
from .models import WriterReceiptReconciliation
from .repository import ConflictError
from .writer_receipt import interactive_receipt, interactive_response_scripts
from .writer_transport import validate_writer_response


def writer_observation(database: Database, project_id: str,
                       receipt: WriterReceiptReconciliation | None) -> dict | None:
    if receipt is None or receipt.agent_id != "nalu-interactive-writer":
        return None
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT * FROM writer_executions WHERE project_id=?
               AND state='completed' AND started_at=? AND completed_at=?""",
            (project_id, receipt.started_at, receipt.completed_at),
        ).fetchall()
    if not rows:
        # Imported executions are quarantined, never promoted by matching JSON.
        return None
    matches = []
    for row in rows:
        raw = row["response_json"].encode()
        if hashlib.sha256(raw).hexdigest() != row["response_sha256"]:
            raise ConflictError("observed writer response integrity failed")
        validate_writer_response(raw)
        response = json.loads(raw)
        if (receipt.provider != "hopsapi.com"
                or response["id"] != receipt.session_or_task_id
                or response["model"] != receipt.model_id
                or row["started_at"] != receipt.started_at
                or row["completed_at"] != receipt.completed_at):
            continue
        number = int(receipt.writer_episode.removeprefix("E"))
        scripts = interactive_response_scripts(raw.decode(), receipt.model_id, receipt.session_or_task_id)
        if number not in scripts:
            continue
        declaration = receipt.model_dump()
        declaration["receipt_sha256"] = row["response_sha256"]
        rebuilt, _ = interactive_receipt(raw.decode(), declaration, number,
                                         receipt.writer_version, scripts[number])
        if rebuilt["receipt_sha256"] == receipt.receipt_sha256:
            matches.append(row)
    if len(matches) != 1:
        raise ConflictError("writer receipt does not identify one observed execution")
    row = matches[0]
    observation = {
        "schema_version": "nalu.writer-observation/v1",
        "project_id": project_id, "turn_id": row["turn_id"],
        "episode_id": receipt.episode_id, "script_revision": receipt.script_revision,
        "writer_receipt_record_sha256": receipt.record_sha256,
        "response_sha256": row["response_sha256"],
        "execution_request_sha256": row["request_sha256"],
        "provider": receipt.provider, "model_id": receipt.model_id,
        "session_or_task_id": receipt.session_or_task_id,
        "started_at": row["started_at"], "completed_at": row["completed_at"],
        "runtime_response_observed": True,
        "remote_lookup_performed": False,
        "production_authorized": False,
    }
    observation["record_sha256"] = hashlib.sha256(json.dumps(
        observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    return observation
