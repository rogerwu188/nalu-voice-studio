"""Resumable project-owned chapter imports; no model call or script approval."""

import hashlib
import json
import uuid
from urllib.parse import urldefrag, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .repository import ConflictError, NotFoundError, utc_now
from .source_reader import read_public_chapter, source_failure_code


class NovelChapterSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=4000)
    title: str = Field(min_length=1, max_length=500)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        return chapter_url(value)


class NovelImportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: str = Field(min_length=1, max_length=4000)
    chapters: list[NovelChapterSelection] = Field(min_length=1, max_length=2000)

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value):
        return chapter_url(value)


def import_summary(state):
    if state is None:
        return None
    return {"schema_version": state["schema_version"], "status": state["status"],
            "updated_at": state["updated_at"],
            "source_url": state["selection"]["source_url"],
            "completed_chapters": sum(c["status"] == "complete" for c in state["chapters"]),
            "chapters": [{key: value for key, value in item.items() if key != "text"}
                         for item in state["chapters"]]}


def chapter_url(value):
    value = urldefrag(value)[0]
    parsed = urlsplit(value)
    if (len(value) > 4000 or parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.port not in {None, 443}):
        raise ValueError("chapter requires public HTTPS URL")
    return value


class NovelImport:
    # Existing project-bible storage is SQLite-owned and follows project backup,
    # restore and deletion. No plaintext sidecar with an independent lifecycle.
    key = "nalu_novel_import_v1"

    def __init__(self, database, reader=None):
        self.database = database
        self.reader = reader or read_public_chapter

    def _load(self, connection, project_id, *, writing=False):
        row = connection.execute(
            "SELECT project_bible_json, archived_at FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("project not found")
        if writing and row["archived_at"]:
            raise ConflictError("archived project is read-only")
        bible = json.loads(row["project_bible_json"])
        return bible, bible.get(self.key)

    def _save(self, connection, project_id, bible, state):
        state["updated_at"] = utc_now()
        bible[self.key] = state
        connection.execute("UPDATE projects SET project_bible_json=?, updated_at=? WHERE id=?",
                           (json.dumps(bible, ensure_ascii=False), state["updated_at"], project_id))
        return state

    def read(self, project_id):
        with self.database.connect() as connection:
            return self._load(connection, project_id)[1]

    def create(self, project_id, source_url, chapters):
        source_url = chapter_url(source_url)
        if not 1 <= len(chapters) <= 2000:
            raise ValueError("select between 1 and 2000 chapters")
        selected = [{"url": chapter_url(item["url"]), "title": item["title"][:500]}
                    for item in chapters]
        if len({item["url"] for item in selected}) != len(selected):
            raise ValueError("duplicate chapter URLs")
        identity = {"source_url": source_url, "chapters": selected}
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            bible, state = self._load(connection, project_id, writing=True)
            if state:
                if state["selection"] != identity:
                    raise ConflictError("project already has a different novel import")
                return state
            state = {"schema_version": "nalu.novel-import/v1", "selection": identity,
                     "status": "ready", "chapters": [
                         {**item, "status": "pending", "text": "", "sha256": None}
                         for item in selected], "active_attempt": None}
            return self._save(connection, project_id, bible, state)

    def pause(self, project_id):
        return self._control(project_id, resume=False)

    def resume(self, project_id):
        return self._control(project_id, resume=True)

    def _control(self, project_id, *, resume):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            bible, state = self._load(connection, project_id, writing=True)
            if not state:
                raise NotFoundError("novel import not found")
            # Explicit recovery invalidates any old in-flight response. It cannot
            # overwrite a new attempt even if the old process returns later.
            state["active_attempt"] = None
            for item in state["chapters"]:
                if item["status"] == "fetching" or (resume and item["status"] == "failed"):
                    item["status"] = "pending"
            complete = all(item["status"] == "complete" for item in state["chapters"])
            state["status"] = "complete" if complete else ("ready" if resume else "paused")
            return self._save(connection, project_id, bible, state)

    def fetch_next(self, project_id):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            bible, state = self._load(connection, project_id, writing=True)
            if not state:
                raise NotFoundError("novel import not found")
            if state["status"] != "ready":
                return state
            index = next((i for i, item in enumerate(state["chapters"])
                          if item["status"] != "complete"), None)
            if index is None:
                state["status"] = "complete"
                return self._save(connection, project_id, bible, state)
            attempt = uuid.uuid4().hex
            state["active_attempt"] = attempt
            state["status"] = "fetching"
            item = state["chapters"][index]
            item["status"] = "fetching"
            url = item["url"]
            self._save(connection, project_id, bible, state)
        # No SQLite write lock is held over the network.
        failure = None
        try:
            page = self.reader(url)
            text = page["text"]
            if page.get("truncated") or not text.strip() or len(text) > 1_000_000:
                raise ValueError("incomplete or oversized chapter")
            resolved_url = chapter_url(page["url"])
        except (ValueError, OSError, LookupError) as exc:
            failure = source_failure_code(exc)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            bible, state = self._load(connection, project_id, writing=True)
            if not state or state["active_attempt"] != attempt:
                return state
            item = state["chapters"][index]
            if failure is None and sum(len(c["text"]) for c in state["chapters"]) + len(text) > 20_000_000:
                failure = "novel_storage_limit"
            state["active_attempt"] = None
            if failure:
                item.update(status="failed", error=failure)
                state["status"] = "failed"
            else:
                item.update(status="complete", text=text, resolved_url=resolved_url,
                            sha256=hashlib.sha256(text.encode()).hexdigest(), error=None)
                state["status"] = ("complete" if all(c["status"] == "complete"
                                                    for c in state["chapters"]) else "ready")
            return self._save(connection, project_id, bible, state)
