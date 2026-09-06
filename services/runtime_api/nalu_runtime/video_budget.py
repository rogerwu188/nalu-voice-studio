"""Atomic local estimate reservations; never a provider price or billing guarantee."""

import json

from pydantic import BaseModel, ConfigDict, Field

from .models import RunStatus
from .repository import ConflictError, Repository, encode, new_id, utc_now
from .video_preparation import digest


class VideoBudgetApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preparation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimated_credits: int = Field(strict=True, gt=0)
    confirmed_run_budget_credits: int = Field(strict=True, gt=0)
    approved_by: str = Field(min_length=1, max_length=160, pattern=r"\S")
    confirmation: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    guardian_approval: bool = False


class VideoBudgetService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def reserve(self, run_id: str, preparation_id: str, approval: VideoBudgetApproval):
        # One write transaction serializes all shot reservations against this run.
        event_id, now = new_id("evt"), utc_now()
        with self.repository.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = db.execute("SELECT * FROM production_runs WHERE id = ?", (run_id,)).fetchone()
            if run is None or run["dry_run"] or run["status"] != RunStatus.WAITING_FOR_APPROVAL:
                raise ConflictError("estimate approval requires a non-dry approval-waiting run")
            project = db.execute("SELECT * FROM projects WHERE id = ?", (run["project_id"],)).fetchone()
            if project["archived_at"]:
                raise ConflictError("archived project is read-only")
            if project["audience_mode"] == "child" and not approval.guardian_approval:
                raise ConflictError("child projects require guardian approval")
            if run["estimated_budget_credits"] != approval.confirmed_run_budget_credits:
                raise ConflictError("run estimate changed; review the current budget")
            source = db.execute(
                "SELECT * FROM run_events WHERE id = ? AND run_id = ? AND event_type = 'video_task_prepared'",
                (preparation_id, run_id),
            ).fetchone()
            if source is None:
                raise ConflictError("saved shot preparation not found in this run")
            prepared = json.loads(source["payload_json"])
            expected = digest({k: v for k, v in prepared.items() if k != "preparation_sha256"})
            if prepared.get("preparation_sha256") != expected or expected != approval.preparation_sha256:
                raise ConflictError("shot preparation changed; review again")
            if digest(prepared["request"]) != prepared["request_sha256"]:
                raise ConflictError("saved request integrity failed")
            preparations = db.execute(
                "SELECT payload_json FROM run_events WHERE run_id = ? AND event_type = 'video_task_prepared' AND sequence > ?",
                (run_id, source["sequence"]),
            ).fetchall()
            if any(json.loads(row[0]).get("task_key") == prepared["task_key"]
                   and json.loads(row[0]).get("preparation_sha256") != expected for row in preparations):
                raise ConflictError("a newer shot preparation requires review")
            rows = db.execute(
                "SELECT id, payload_json FROM run_events WHERE run_id = ? AND event_type = 'video_estimate_reserved'",
                (run_id,),
            ).fetchall()
            reservations = [(row["id"], json.loads(row["payload_json"])) for row in rows]
            for _, record in reservations:
                if (record.get("reservation_sha256") != digest({k: v for k, v in record.items() if k != "reservation_sha256"})
                        or record.get("run_id") != run_id
                        or type(record.get("estimated_credits")) is not int
                        or record["estimated_credits"] <= 0):
                    raise ConflictError("prior reservation requires integrity or import reconciliation")
            reserved_keys = {record["task_key"] for _, record in reservations}
            if len(reserved_keys) != len(reservations):
                raise ConflictError("duplicate shot reservations require reconciliation")
            bindings = db.execute("SELECT task_key FROM remote_task_bindings WHERE run_id = ?", (run_id,)).fetchall()
            if any(row[0] not in reserved_keys for row in bindings):
                raise ConflictError("existing provider tasks have unreserved cost; reconcile first")
            prior = next(((identity, record) for identity, record in reservations
                          if record["task_key"] == prepared["task_key"]), None)
            if prior:
                if prior[1]["preparation_sha256"] != expected or prior[1]["estimated_credits"] != approval.estimated_credits:
                    raise ConflictError("shot already reserves a different request or estimate")
                event_id = prior[0]
            else:
                total = sum(record["estimated_credits"] for _, record in reservations) + approval.estimated_credits
                if total > approval.confirmed_run_budget_credits:
                    raise ConflictError("shot estimates exceed the confirmed run budget")
                record = {**approval.model_dump(), "run_id": run_id, "preparation_id": preparation_id,
                          "task_key": prepared["task_key"], "request_sha256": prepared["request_sha256"],
                          "production_package_sha256": prepared["production_package_sha256"],
                          "total_reserved_estimate_credits": total,
                          "provider_price_verified": False, "provider_charge_cap_guaranteed": False,
                          "generation_performed": False}
                record["reservation_sha256"] = digest(record)
                sequence = db.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?", (run_id,)).fetchone()[0]
                db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (event_id, run_id, sequence, "video_estimate_reserved", None, None,
                            "Local shot estimate approved and reserved; provider price remains unverified.",
                            encode(record), now))
        return self.repository.get_run_event(event_id)
