"""Project-owned interactive writing state for narrated and web-sourced stories."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .database import Database
from .models import ExternalWriterDeclaration
from .novel_import import NovelImport, writing_context
from .repository import ConflictError, NotFoundError, utc_now
from .writer_receipt import WriterReceiptVerificationError, interactive_receipt


class StoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=12000)
    source_mode: Literal["narrated_story", "web_source"]
    queue_only: bool = False


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
    external_writer: ExternalWriterDeclaration | None = None
    writer_response_json: str | None = Field(default=None, max_length=2000000)
    novel_source_choice: "NovelSourceChoice | None" = None


class NovelSourceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=4000, pattern=r"^https://")


class NovelSourceChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[NovelSourceCandidate] = Field(min_length=1, max_length=5)
    writingRequested: bool


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
            queued = state.setdefault("queued_inputs", [])
            matching = next((item for item in queued if item["turn_id"] == request.turn_id), None)
            if matching and (matching["text"] != request.text or matching["source_mode"] != request.source_mode):
                raise ConflictError("queued turn ID already belongs to another input")
            if request.queue_only:
                if matching:
                    return state
                if len(queued) >= 50:
                    raise ConflictError("too many queued story inputs")
                queued.append({"turn_id": request.turn_id, "text": request.text,
                               "source_mode": request.source_mode, "created_at": utc_now()})
                # Do not invalidate the response currently in flight. The answer
                # transaction reloads this queue and preserves later additions.
                return self._save(connection, project_id, bible, state)
            if state["revision"] != request.expected_revision:
                raise ConflictError("story changed; reload before adding this input")
            if len(state["turns"]) >= 500:
                raise ConflictError("story conversation limit reached")
            if matching:
                queued.remove(matching)
            if state["turns"] and state["turns"][-1]["status"] == "pending":
                state["turns"][-1]["status"] = "superseded"
            state["revision"] += 1
            # Freeze source evidence with this input. Background import progress
            # must not mutate the body of an already charged/recoverable request.
            context = writing_context(bible.get(NovelImport.key), request.text,
                                      previous=state.get("novel_source"))
            if context is not None:
                state["novel_source"] = context
            else:
                state.pop("novel_source", None)
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
                    writers = state.setdefault("draft_writers", {})
                    receipts = state.setdefault("draft_receipts", {})
                    for draft in request.episode_drafts:
                        # Corrections cannot inherit an older run's receipt.
                        writers[str(draft.episode_number)] = (
                            request.external_writer.model_dump(mode="json")
                            if request.external_writer else None
                        )
                        receipts[str(draft.episode_number)] = None
                        if request.external_writer and request.writer_response_json:
                            try:
                                writer, receipt = interactive_receipt(
                                    request.writer_response_json,
                                    request.external_writer.model_dump(mode="json"),
                                    draft.episode_number, state["revision"] + 1, draft.script,
                                )
                            except WriterReceiptVerificationError as exc:
                                raise ConflictError(str(exc)) from exc
                            writers[str(draft.episode_number)] = writer
                            receipts[str(draft.episode_number)] = receipt
            state["revision"] += 1
            return self._save(connection, project_id, bible, state)
