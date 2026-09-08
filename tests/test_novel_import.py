import json

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.interactive_story import InteractiveStory, StoryAnswer, StoryInput
from nalu_runtime.interactive_writer_service import writer_request
from nalu_runtime.novel_import import NovelImport, catalog_chapters, writing_context
from nalu_runtime.repository import ConflictError


def setup_import(tmp_path, reader):
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    project = api.post("/v1/projects", json={"title": "小说"}).json()["id"]
    service = NovelImport(api.app.state.repository.db, reader)
    chapters = [{"url": f"https://example.com/{i}", "title": f"第{i}章"} for i in (1, 2)]
    service.create(project, "https://example.com/index", chapters)
    return service, project, chapters


def test_restart_preserves_complete_chapters_and_explicit_retry(tmp_path):
    calls = []
    failing = True

    def reader(url):
        calls.append(url)
        if url.endswith("2") and failing:
            raise TimeoutError("private diagnostic")
        return {"url": url, "text": "完整章节" * 7000, "truncated": False}

    service, project, chapters = setup_import(tmp_path, reader)
    first = service.fetch_next(project)
    assert first["status"] == "ready"
    assert len(first["chapters"][0]["text"]) > 24000
    service = NovelImport(service.database, reader)
    failed = service.fetch_next(project)
    assert failed["status"] == "failed"
    assert failed["chapters"][1]["error"] == "source_timeout"
    service.fetch_next(project)
    assert len(calls) == 2  # no implicit failed retry
    failing = False
    service.resume(project)
    complete = service.fetch_next(project)
    assert complete["status"] == "complete"
    service.fetch_next(project)
    assert calls == [chapters[0]["url"], chapters[1]["url"], chapters[1]["url"]]
    assert service.create(project, "https://example.com/index", chapters) == complete
    with pytest.raises(ConflictError):
        service.create(project, "https://example.com/index", list(reversed(chapters)))


def test_pause_discards_inflight_response_and_resume_recovers(tmp_path):
    def reader(url):
        service.pause(project)
        return {"url": url, "text": "old response", "truncated": False}

    service, project, _ = setup_import(tmp_path, reader)
    result = service.fetch_next(project)
    assert result["status"] == "paused"
    assert result["chapters"][0]["text"] == ""
    service.reader = lambda url: {"url": url, "text": "new response", "truncated": False}
    service.fetch_next(project)
    assert service.read(project)["chapters"][0]["text"] == ""
    service.resume(project)
    assert service.fetch_next(project)["chapters"][0]["text"] == "new response"


def test_process_crash_requires_explicit_recovery(tmp_path):
    class Crash(BaseException):
        pass

    def reader(url):
        raise Crash()

    service, project, _ = setup_import(tmp_path, reader)
    with pytest.raises(Crash):
        service.fetch_next(project)
    recovered = NovelImport(service.database, lambda url: {"url": url, "text": "正文"})
    assert recovered.fetch_next(project)["status"] == "fetching"
    recovered.resume(project)
    assert recovered.fetch_next(project)["chapters"][0]["status"] == "complete"


def test_public_api_import_restore_and_chapter_read(tmp_path, monkeypatch):
    calls = []

    def reader(url):
        calls.append(url)
        return {"url": url, "text": "第一个完整章节", "truncated": False}

    monkeypatch.setattr("nalu_runtime.novel_import.read_public_chapter", reader)
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    project = api.post("/v1/projects", json={"title": "导入小说"}).json()["id"]
    path = f"/v1/projects/{project}/novel-import"
    payload = {"source_url": "https://example.com/index", "chapters": [
        {"url": "https://example.com/1", "title": "第一章"}]}
    assert api.post(path, json=payload, headers={"Origin": "https://example.com"}).status_code == 403
    assert api.get(path).json() is None
    assert api.post(path, json=payload).status_code == 201
    assert calls == []  # creating a selection does not fetch behind the user's back
    assert api.get(path + "/chapters/1").status_code == 409
    assert api.post(path + "/pause").json()["status"] == "paused"
    assert api.post(path + "/fetch-next").json()["status"] == "paused"
    assert calls == []
    assert api.post(path + "/resume").json()["status"] == "ready"
    result = api.post(path + "/fetch-next")
    assert result.status_code == 200
    assert result.json()["completed_chapters"] == 1
    assert "text" not in result.json()["chapters"][0]
    restored = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    assert restored.get(path + "/chapters/1").json()["text"] == "第一个完整章节"
    assert restored.post(path + "/fetch-next").json()["status"] == "complete"
    assert calls == ["https://example.com/1"]
    assert restored.get(path + "/chapters/0").status_code == 404
    assert restored.post(path + "/delete-all").status_code == 404


def test_source_only_import_discovers_without_manual_chapter_list(tmp_path, monkeypatch):
    calls = []

    def reader(url):
        calls.append(url)
        return {"url": url, "text": "目录", "truncated": False, "links": [
            {"url": "https://example.com/2", "title": "第二章 归来"},
            {"url": "https://example.com/1", "title": "第1章 出发"},
            {"url": "https://example.com/1", "title": "第1章 出发"},
            {"url": "https://ads.example.com/3", "title": "第三章 广告"},
            {"url": "https://example.com/login", "title": "登录"},
        ]}

    monkeypatch.setattr("nalu_runtime.novel_import.read_public_chapter", reader)
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    project = api.post("/v1/projects", json={"title": "自动目录"}).json()["id"]
    path = f"/v1/projects/{project}/novel-import"
    payload = {"source_url": "https://example.com/index"}
    response = api.post(path, json=payload)
    assert response.status_code == 201, response.text
    assert [c["title"] for c in response.json()["chapters"]] == ["第1章 出发", "第二章 归来"]
    assert api.post(path, json=payload).json() == response.json()
    assert calls == [payload["source_url"]]


def test_catalog_does_not_silently_choose_between_volumes():
    page = {"url": "https://example.com/index", "links": [
        {"url": "https://example.com/a", "title": "第一章 甲"},
        {"url": "https://example.com/b", "title": "第1章 乙"},
    ]}
    with pytest.raises(ValueError, match="ambiguous"):
        catalog_chapters(page)
    with pytest.raises(ValueError, match="incomplete"):
        catalog_chapters({**page, "truncated": True})


def test_long_chapter_continuation_is_bounded_and_does_not_restart(tmp_path):
    service, project, _ = setup_import(tmp_path, lambda url: {
        "url": url, "text": "abcdefghij", "truncated": False})
    service.fetch_next(project)
    state = service.read(project)
    first = writing_context(state, "第一章", character_budget=6)
    second = writing_context(state, "继续改编小说下一段", character_budget=6, previous=first)
    assert second["passages"][0]["text"] == "ghij"
    assert second["passages"][0]["start_character"] == 6
    assert not second["passages"][0]["complete_chapter"]
    exhausted = writing_context(state, "继续改编小说下一段", previous=second)
    assert exhausted["passages"] == []
    assert writing_context(state, "继续改编小说下一段", previous=exhausted)["passages"] == []
    service.fetch_next(project)
    resumed = writing_context(service.read(project), "继续改编小说下一段", previous=exhausted)
    assert resumed["passages"][0]["chapter_number"] == 2
    assert resumed["passages"][0]["start_character"] == 0
    assert writing_context(state, "修改刚才剧本", character_budget=6, previous=first)["passages"][0]["text"] == "abcdef"


def test_imported_chapters_reach_frozen_writer_context(tmp_path):
    service, project, _ = setup_import(tmp_path, lambda url: {
        "url": url, "text": "小说正文：" + url, "truncated": False})
    service.fetch_next(project)
    story = InteractiveStory(service.database)
    state = story.append(project, StoryInput(turn_id="write", expected_revision=0,
                         text="请把第一章写成第一集", source_mode="web_source"))
    body = writer_request(state, "fixture-model")
    context = json.loads(json.loads(body)["messages"][1]["content"])
    assert context["novel_source"]["passages"][0]["text"] == "小说正文：https://example.com/1"
    assert context["novel_source"]["scope"] == "explicit_bounded_passages_not_whole_novel"
    service.fetch_next(project)
    assert writer_request(story.read(project), "fixture-model") == body
    updated = story.append(project, StoryInput(turn_id="next", expected_revision=1,
                           text="接着改编第二回", source_mode="web_source"))
    assert updated["novel_source"]["passages"][0]["source_url"] == "https://example.com/2"


def test_sqlite_restart_revision_and_replay_preserve_long_source_window(tmp_path):
    service, project, _ = setup_import(tmp_path, lambda url: {
        "url": url, "text": "甲" * 60000 + "乙" * 100, "truncated": False})
    service.fetch_next(project)
    story = InteractiveStory(service.database)
    story.append(project, StoryInput(turn_id="first", expected_revision=0,
                 text="第一章写成剧本", source_mode="web_source"))
    # Recreate the Runtime and repository over the same on-disk database.
    restarted = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    story = InteractiveStory(restarted.app.state.repository.db)
    request = StoryInput(turn_id="continue", expected_revision=1,
                        text="继续改编小说下一段", source_mode="web_source")
    second = story.append(project, request)
    assert second["novel_source"]["passages"][0]["text"] == "乙" * 100
    body = writer_request(second, "fixture-model")
    assert writer_request(story.append(project, request), "fixture-model") == body
    revised = story.append(project, StoryInput(turn_id="revise", expected_revision=2,
                          text="这一段写得温柔一点", source_mode="web_source"))
    assert revised["novel_source"] == second["novel_source"]
    exhausted = story.append(project, StoryInput(turn_id="end", expected_revision=3,
                            text="继续改编小说下一段", source_mode="web_source"))
    assert exhausted["novel_source"]["passages"] == []
    assert exhausted["novel_source"]["continuation_anchor"]["end_character"] == 60100


def test_source_choice_survives_restart_until_next_turn(tmp_path):
    service, project, _ = setup_import(tmp_path, lambda url: {})
    story = InteractiveStory(service.database)
    story.append(project, StoryInput(turn_id="search", expected_revision=0,
                 text="找小说", source_mode="web_source"))
    choice = {"sources": [{"title": "目录", "url": "https://example.com/book"}],
              "writingRequested": True}
    answer = StoryAnswer(expected_revision=1, reply="请选择", novel_source_choice=choice)
    story.answer(project, "search", answer)
    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    restored = InteractiveStory(api.app.state.repository.db)
    assert restored.read(project)["turns"][-1]["answer"]["novel_source_choice"] == choice
    assert restored.answer(project, "search", answer)["revision"] == 2
    new = restored.append(project, StoryInput(turn_id="selected", expected_revision=2,
                          text="导入小说 https://example.com/book", source_mode="web_source"))
    assert new["turns"][-1].get("answer") is None


@pytest.mark.parametrize("mode", ["complete", "cycle", "external", "failed", "limit"])
def test_paginated_catalog_is_not_silently_partial(tmp_path, mode):
    calls = []

    def reader(url):
        calls.append(url)
        number = int(url.rsplit("=", 1)[1])
        if number == 2 and mode == "failed":
            raise TimeoutError("catalog unavailable")
        links = [{"url": f"https://example.com/chapter/{number}",
                  "title": f"第{number}章 故事"}]
        next_url = None
        if number == 1 or mode == "limit":
            next_url = f"https://example.com/index?page={number + 1}"
        elif mode == "cycle":
            next_url = "https://example.com/index?page=1"
        elif mode == "external":
            next_url = "https://different.example/index?page=3"
        if next_url:
            links.append({"url": next_url, "title": "下一页目录"})
        return {"url": url, "text": "目录", "links": links, "truncated": False}

    api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    project = api.post("/v1/projects", json={"title": "分页"}).json()["id"]
    service = NovelImport(api.app.state.repository.db, reader)
    if mode == "complete":
        result = service.discover(project, "https://example.com/index?page=1")
        assert [c["title"] for c in result["chapters"]] == ["第1章 故事", "第2章 故事"]
        service.discover(project, "https://example.com/index?page=1")
        assert len(calls) == 2
    else:
        with pytest.raises((ValueError, TimeoutError)):
            service.discover(project, "https://example.com/index?page=1")
        assert service.read(project) is None
        assert len(calls) == (8 if mode == "limit" else 2)
