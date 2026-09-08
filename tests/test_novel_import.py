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
