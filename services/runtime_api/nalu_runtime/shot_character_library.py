"""Prepare local character cards from a reviewed shot plan, never auto-confirm them."""

import json
import re

from pydantic import BaseModel, ConfigDict, Field

from .models import LibraryEntityCreate
from .repository import ConflictError, encode, new_id, utc_now
from .shot_planning import ShotPlanningService
from .shot_review import PLAN_EVENTS
from .video_preparation import digest


class ShotCharacterLibraryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ShotCharacterLibraryService:
    def __init__(self, repository):
        self.repository = repository

    def prepare(self, run_id, plan_id, request: ShotCharacterLibraryRequest):
        repo = self.repository
        with repo.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            run = repo.get_run(run_id)
            package = ShotPlanningService(repo)._package(run)
            events = db.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
            plans = [row for row in events if row["event_type"] in PLAN_EVENTS]
            if not plans or plans[-1]["id"] != plan_id or plans[-1]["event_type"] != "shot_plan_approved":
                raise ConflictError("confirm the current shot plan before preparing character cards")
            payload = json.loads(plans[-1]["payload_json"])
            if (payload.get("approved") is not True or payload.get("plan_sha256") != request.expected_plan_sha256
                    or digest({k: v for k, v in payload.items() if k != "plan_sha256"}) != request.expected_plan_sha256
                    or payload.get("production_package_sha256") != package.get("package_sha256")):
                raise ConflictError("character cards require the intact reviewed shot plan")
            episode = repo.get_episode(run.episode_id)
            if payload.get("script_revision") != episode.approved_script_revision:
                raise ConflictError("script changed; reconcile its shot plan first")
            for row in events:
                if row["event_type"] == "shot_character_library_prepared":
                    saved = json.loads(row["payload_json"])
                    if saved.get("plan_event_id") == plan_id and saved.get("plan_sha256") == request.expected_plan_sha256:
                        return repo.get_run_event(row["id"])
            bindings, readback = [], []
            now = utc_now()
            for design in payload["plan"].get("visual_assets", []):
                if design["kind"] != "character_image":
                    continue
                name = re.sub(r"\s+", " ", design["name"].strip()).casefold()
                existing = db.execute("SELECT * FROM library_entities WHERE project_id=? AND kind='character' AND stable_name=?",
                                      (run.project_id, name)).fetchone()
                if existing:
                    entity_id, revision = existing["id"], existing["current_revision"]
                    # Keep existing family facts and previously confirmed revisions intact.
                    is_new = False
                    confirmed = existing["confirmed_revision"] == revision
                else:
                    draft = LibraryEntityCreate(kind="character", name=design["name"], description=design["description"],
                        attributes={"shot_plan_source": {"run_id": run_id, "plan_id": plan_id,
                                    "design_key": design["key"], "source_excerpt": design["source_excerpt"]}},
                        source_asset_ids=[design["existing_asset_id"]] if design.get("existing_asset_id") else [],
                        source_channel="system", change_summary="根据已审阅分镜整理人物草稿，等待用户确认")
                    repo._validate_library_sources(run.project_id, draft)
                    entity_id, revision, is_new, confirmed = new_id("lib"), 1, True, False
                    db.execute("INSERT INTO library_entities VALUES (?, ?, ?, ?, 1, NULL, ?, ?)",
                               (entity_id, run.project_id, "character", name, now, now))
                    db.execute("INSERT INTO library_entity_revisions VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (entity_id, draft.name, draft.description, encode(draft.attributes),
                                encode(draft.source_asset_ids), encode([]), draft.source_channel, draft.change_summary, now))
                bindings.append({"design_key": design["key"], "entity_id": entity_id, "revision": revision,
                                 "created_draft": is_new, "confirmed_at_preparation": confirmed})
                readback.append(f"{design['name']}：" + ("沿用已有项目人物资料，请核对是否是同一个人。" if not is_new
                                else design["description"] + "。这是根据分镜整理的草稿，请告诉我哪里需要修改，再确认。"))
            record = {"plan_event_id": plan_id, "plan_sha256": request.expected_plan_sha256,
                      "bindings": bindings, "readback": "\n".join(readback),
                      "characters_auto_confirmed": False, "production_package_changed": False,
                      "generation_performed": False, "paid_approved": False}
            record["preparation_sha256"] = digest(record)
            event_id = new_id("evt")
            sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()[0]
            db.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (event_id, run_id, sequence, "shot_character_library_prepared", None, None,
                        "Character cards prepared locally for conversational confirmation.", encode(record), now))
        return repo.get_run_event(event_id)
