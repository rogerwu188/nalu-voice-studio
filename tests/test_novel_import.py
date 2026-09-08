import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.novel_import import NovelImport
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
