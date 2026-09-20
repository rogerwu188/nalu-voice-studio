#!/usr/bin/env python3
"""Opt-in real HTTPS -> isolated SQLite -> writer-request rehearsal, no model call."""

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.interactive_writer_service import writer_request
from nalu_runtime.novel_import import NovelImport, writing_context


def verify_source_windows(state):
    window = writing_context(state, "第一回至第一百回")
    chunks, windows = [], 0
    while window["passages"]:
        windows += 1
        assert windows <= 100, "continuation failed to advance"
        assert sum(len(p["text"]) for p in window["passages"]) <= 60000
        chunks.extend(p["text"] for p in window["passages"])
        window = writing_context(state, "继续改编小说下一段", previous=window)
    text = "".join(chunks)
    assert text == "".join(p["text"] for p in state["chapters"]), "source windows skip or duplicate text"
    return {"windows": windows, "characters": len(text),
            "joined_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "no_skips_or_duplicates": True, "model_called": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapters", type=int, default=2, choices=range(2, 101),
                        metavar="2..100", help="explicit number of live chapters to fetch")
    parser.add_argument("--resume-database", type=Path,
                        help="resume a failed isolated import without rediscovering or refetching saved chapters")
    args = parser.parse_args()
    count = args.chapters
    # Keep evidence isolated from the user's running application and projects.
    if args.resume_database:
        if not args.resume_database.is_file():
            parser.error("--resume-database must name an existing isolated database")
        database_path = args.resume_database.resolve()
        root = database_path.parent
    else:
        root = Path(tempfile.mkdtemp(prefix="nalu-live-novel-"))
        database_path = root / "nalu.sqlite3"
    source = "https://zh.wikisource.org/wiki/西遊記"
    with TestClient(create_app(database_path, root / "data")) as api:
        if args.resume_database:
            projects = api.get("/v1/projects").json()
            matches = [item for item in projects if item["title"] == "Isolated live novel QA"]
            assert len(matches) == 1, "isolated QA project identity changed"
            project = matches[0]["id"]
            route = f"/v1/projects/{project}/novel-import"
            previous = api.get(route).json()
            assert previous["status"] in {"failed", "ready"}, "resume only a paused or active isolated import"
            completed_before = previous["completed_chapters"]
            assert completed_before > 0
            if previous["status"] == "failed":
                assert api.post(route + "/resume").json()["status"] == "ready"
        else:
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
    with TestClient(create_app(database_path, root / "data")) as api:
        if not args.resume_database:
            assert api.get(route + "/chapters/1").json() == original
            assert api.post(route + "/resume").json()["status"] == "ready"
            second = api.post(route + "/fetch-next")
            assert second.status_code == 200, second.text
            assert second.json()["completed_chapters"] == 2
        chapter = api.get(route + "/chapters/2").json()
        if args.resume_database:
            state = api.get(f"/v1/projects/{project}/interactive-story").json()
            assert any(item["turn_id"] == "live-chapter-two" for item in state["turns"])
            turn = state
        else:
            response = api.post(f"/v1/projects/{project}/interactive-story/turns", json={
                "turn_id": "live-chapter-two", "expected_revision": 0,
                "text": "请改编第二回，先写成一集草稿", "source_mode": "web_source",
            })
            assert response.status_code == 200, response.text
            turn = response.json()
        request = json.loads(writer_request(turn, "fixture-no-call"))
        context = json.loads(request["messages"][1]["content"])["novel_source"]
        assert context["passages"][0]["chapter_sha256"] == chapter["sha256"]
        start = (completed_before + 1) if args.resume_database else 3
        for expected in range(start, count + 1):
            for attempt in range(3):
                time.sleep(0.5)
                fetched = api.post(route + "/fetch-next")
                assert fetched.status_code == 200, fetched.text
                imported = fetched.json()
                if imported["completed_chapters"] == expected:
                    break
                failures = [item for item in imported["chapters"] if item.get("status") == "failed"]
                assert imported["status"] == "failed" and len(failures) == 1 \
                    and failures[0].get("error") == "source_timeout", fetched.text
                assert attempt < 2, fetched.text
                assert api.post(route + "/resume").json()["status"] == "ready"
            else:
                raise AssertionError(f"chapter {expected} did not persist after explicit timeout retries")
            if expected % 10 == 0:
                print(json.dumps({"saved_chapters": expected, "target": count}), flush=True)
        final = api.get(route).json()
        assert final["completed_chapters"] == count
        if count == 100:
            assert final["status"] == "complete"
            assert all(item["status"] == "complete" for item in final["chapters"])
            assert api.get(route + "/chapters/100").json()["text"]
            print(json.dumps(verify_source_windows(NovelImport(api.app.state.repository.db).read(project))))
        print(json.dumps({"source": source, "catalog_chapters": 100,
                          "saved_chapters": count, "second_chapter_characters": len(chapter["text"]),
                          "second_chapter_sha256": chapter["sha256"],
                          "database": str(database_path),
                          "restart_recovery": True, "writer_received_second_chapter": True,
                          "model_called": False, "full_catalog_import": count == 100,
                          "full_book_import": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
