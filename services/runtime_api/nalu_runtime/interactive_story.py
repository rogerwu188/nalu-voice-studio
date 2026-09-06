"""Project-owned interactive writing state for narrated and web-sourced stories."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .database import Database
from .repository import ConflictError, NotFoundError, utc_now


class StoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=12000)
    source_mode: Literal["narrated_story", "web_source"]


class EpisodeWritingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_number: int = Field(ge=1, le=500)
    title: str = Field(min_length=1, max_length=160)
    outline: str = Field(min_length=1, max_length=12000)
    script: str = Field(default="", max_length=100000)


class StoryAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    reply: str = Field(min_length=1, max_length=12000)
    summary: str = Field(default="", max_length=24000)
    episode_drafts: list[EpisodeWritingDraft] = Field(default_factory=list, max_length=50)
    outcome: Literal["answered", "lookup_failed", "writer_failed"] = "answered"


class InteractiveStory:
    # project_bible is already local SQLite, exported/restored and deleted with
    # the project. Keep user conversation distinct from confirmed script revisions.
    key = "nalu_interactive_story_v1"

    def __init__(self, database: Database):
        self.database = database

    def _load(self, connection, project_id):
        row = connection.execute(
            "SELECT project_bible_json, archived_at FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("project not found")
        bible = json.loads(row["project_bible_json"])
        state = bible.get(self.key, {
            "schema_version": "nalu.interactive-story/v1", "revision": 0,
            "turns": [], "summary": "", "episode_drafts": [],
        })
        return row, bible, state

    def read(self, project_id):
        with self.database.connect() as connection:
            return self._load(connection, project_id)[2]

    def _save(self, connection, project_id, bible, state):
        bible[self.key] = state
        connection.execute(
            "UPDATE projects SET project_bible_json=?, updated_at=? WHERE id=?",
            (json.dumps(bible, ensure_ascii=False), utc_now(), project_id),
        )
        return state

    def append(self, project_id, request: StoryInput):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row, bible, state = self._load(connection, project_id)
            if row["archived_at"]:
                raise ConflictError("archived project is read-only")
            for turn in state["turns"]:
                if turn["turn_id"] == request.turn_id:
                    if turn["text"] != request.text or turn["source_mode"] != request.source_mode:
                        raise ConflictError("turn ID already belongs to another input")
                    return state
            if state["revision"] != request.expected_revision:
                raise ConflictError("story changed; reload before adding this input")
            if len(state["turns"]) >= 500:
                raise ConflictError("story conversation limit reached")
            if state["turns"] and state["turns"][-1]["status"] == "pending":
                state["turns"][-1]["status"] = "superseded"
            state["revision"] += 1
            state["turns"].append({
                "turn_id": request.turn_id, "text": request.text,
                "source_mode": request.source_mode, "status": "pending",
                "created_at": utc_now(),
            })
            return self._save(connection, project_id, bible, state)

    def answer(self, project_id, turn_id, request: StoryAnswer):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row, bible, state = self._load(connection, project_id)
            if row["archived_at"]:
                raise ConflictError("archived project is read-only")
            if not state["turns"] or state["turns"][-1]["turn_id"] != turn_id:
                raise ConflictError("answer no longer belongs to the current story input")
            turn = state["turns"][-1]
            payload = request.model_dump(exclude={"expected_revision"})
            if turn.get("answer") == payload:
                return state
            if state["revision"] != request.expected_revision or turn["status"] != "pending":
                raise ConflictError("story changed; discard stale answer")
            numbers = [draft.episode_number for draft in request.episode_drafts]
            if len(numbers) != len(set(numbers)):
                raise ConflictError("duplicate episode draft numbers")
            turn["answer"] = payload
            turn["status"] = request.outcome
            # Failed lookup/writing must never erase the story already developed.
            if request.outcome == "answered":
                if request.summary:
                    state["summary"] = request.summary
                if request.episode_drafts:
                    existing = {item["episode_number"]: item for item in state["episode_drafts"]}
                    existing.update({draft.episode_number: draft.model_dump() for draft in request.episode_drafts})
                    state["episode_drafts"] = [existing[number] for number in sorted(existing)]
            state["revision"] += 1
            return self._save(connection, project_id, bible, state)
