#!/usr/bin/env python3
"""Opt-in real HTTPS -> isolated SQLite -> writer-request rehearsal, no model call."""

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.interactive_writer_service import writer_request


def main():
    # Keep evidence isolated from the user's running application and projects.
    root = Path(tempfile.mkdtemp(prefix="nalu-live-novel-"))
    source = "https://zh.wikisource.org/wiki/西遊記"
    with TestClient(create_app(root / "nalu.sqlite3", root / "data")) as api:
        project = api.post("/v1/projects", json={"title": "Isolated live novel QA"}).json()["id"]
        route = f"/v1/projects/{project}/novel-import"
        catalog = api.post(route, json={"source_url": source})
        assert catalog.status_code == 201, catalog.text
        assert len(catalog.json()["chapters"]) == 100, "live catalog changed; inspect before accepting"
        first = api.post(route + "/fetch-next")
        assert first.status_code == 200, first.text
        assert first.json()["completed_chapters"] == 1
        assert api.post(route + "/pause").json()["status"] == "paused"
        assert api.post(route + "/fetch-next").json()["completed_chapters"] == 1
        original = api.get(route + "/chapters/1").json()
    with TestClient(create_app(root / "nalu.sqlite3", root / "data")) as api:
        assert api.get(route + "/chapters/1").json() == original
        assert api.post(route + "/resume").json()["status"] == "ready"
        second = api.post(route + "/fetch-next")
        assert second.status_code == 200, second.text
        assert second.json()["completed_chapters"] == 2
        chapter = api.get(route + "/chapters/2").json()
        turn = api.post(f"/v1/projects/{project}/interactive-story/turns", json={
            "turn_id": "live-chapter-two", "expected_revision": 0,
            "text": "请改编第二回，先写成一集草稿", "source_mode": "web_source",
        })
        assert turn.status_code == 200, turn.text
        request = json.loads(writer_request(turn.json(), "fixture-no-call"))
        context = json.loads(request["messages"][1]["content"])["novel_source"]
        assert context["passages"][0]["chapter_sha256"] == chapter["sha256"]
        print(json.dumps({"source": source, "catalog_chapters": 100,
                          "saved_chapters": 2, "second_chapter_characters": len(chapter["text"]),
                          "second_chapter_sha256": chapter["sha256"],
                          "database": str(root / "nalu.sqlite3"),
                          "restart_recovery": True, "writer_received_second_chapter": True,
                          "model_called": False, "full_book_import": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
