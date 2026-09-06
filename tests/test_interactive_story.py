from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def test_two_sources_continue_same_story_and_survive_restart(tmp_path):
    database = tmp_path / "nalu.sqlite3"
    data = tmp_path / "data"
    with TestClient(create_app(database, data)) as client:
        project = client.post("/v1/projects", json={
            "title": "爷爷的故事", "project_bible": {"existing_character": "爷爷"},
        }).json()
        path = f"/v1/projects/{project['id']}/interactive-story"
        first = {"turn_id": "first", "expected_revision": 0,
                 "text": "我小时候和外婆在海边生活", "source_mode": "narrated_story"}
        assert client.post(path + "/turns", json=first).json()["revision"] == 1
        answer = {"expected_revision": 1, "reply": "那天发生了什么？",
                  "summary": "外婆和海边童年", "episode_drafts": [
                      {"episode_number": 1, "title": "海边", "outline": "祖孙相伴", "script": "第一场：码头。"},
                  ]}
        assert client.post(path + "/turns/first/answer", json=answer).json()["revision"] == 2
        # HTTP retry must not duplicate a user turn or response.
        assert client.post(path + "/turns", json=first).json()["revision"] == 2
        assert client.post(path + "/turns/first/answer", json=answer).json()["revision"] == 2
        assert client.post(path + "/turns", json={
            "turn_id": "source", "expected_revision": 2,
            "text": "再帮我找这个村子的历史网址", "source_mode": "web_source",
        }).status_code == 200
        failed = client.post(path + "/turns/source/answer", json={
            "expected_revision": 3, "reply": "查找暂时失败，可以继续讲故事。",
            "outcome": "lookup_failed", "summary": "不应覆盖",
        }).json()
        assert failed["summary"] == "外婆和海边童年"
        assert failed["episode_drafts"][0]["script"] == "第一场：码头。"
        assert len(failed["turns"]) == 2
        saved = client.get(f"/v1/projects/{project['id']}").json()
        assert saved["project_bible"]["existing_character"] == "爷爷"
    with TestClient(create_app(database, data)) as restarted:
        assert restarted.get(path).json() == failed


def test_stale_answer_and_wrong_project_cannot_replace_story(tmp_path):
    with TestClient(create_app(tmp_path / "db", tmp_path / "data")) as client:
        one = client.post("/v1/projects", json={"title": "一"}).json()["id"]
        two = client.post("/v1/projects", json={"title": "二"}).json()["id"]
        path = f"/v1/projects/{one}/interactive-story"
        for revision, turn in enumerate(["a", "b"]):
            assert client.post(path + "/turns", json={
                "turn_id": turn, "expected_revision": revision, "text": turn,
                "source_mode": "narrated_story",
            }).status_code == 200
        response = {"expected_revision": 1, "reply": "迟到的回答"}
        assert client.post(path + "/turns/a/answer", json=response).status_code == 409
        assert client.post(f"/v1/projects/{two}/interactive-story/turns/b/answer", json=response).status_code == 409
        assert client.get(path).json()["turns"][0]["status"] == "superseded"
        assert client.get(f"/v1/projects/{two}/interactive-story").json()["turns"] == []
