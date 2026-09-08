"""Both input journeys via public APIs; provider/source responses are synthetic."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


@pytest.mark.parametrize("mode", ["narrated_story", "web_source"])
def test_input_revision_and_two_episode_review_survive_restart(tmp_path, monkeypatch, mode):
    calls = []
    source = "自有合成回忆：外婆在海边教我补渔网。"
    monkeypatch.setattr("nalu_runtime.app.read_public_source", lambda url: {
        "url": url, "text": source, "truncated": False, "scope": "synthetic fixture"})

    def writer(request):
        context = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(context)
        assert source in json.dumps(context, ensure_ascii=False)
        if len(calls) == 1:
            drafts = [{"episode_number": n, "title": f"合成第{n}集", "outline": "海边回忆",
                       "script": f"第{n}集：外婆教我补渔网。"} for n in (1, 2)]
        else:
            assert context["turns"][-1]["text"] == "只改第一集：是爷爷教我，不是外婆。"
            drafts = [{"episode_number": 1, "title": "合成第一集", "outline": "爷爷教我",
                       "script": "第一集：爷爷在海边教我补渔网。"}]
        return httpx.Response(200, json={"id": f"fixture-writer-{len(calls)}", "model": "fixture-model",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "reply": "请审阅草稿", "summary": source, "outcome": "answered", "episode_drafts": drafts})}}]})

    db, data = tmp_path / "nalu.sqlite3", tmp_path / "data"
    def app():
        return create_app(db, data, writer_http_transport=httpx.MockTransport(writer))
    with TestClient(app()) as client:
        plan = client.post("/v1/project-plans", json={"project": {
            "title": "合成入口验收", "planned_episode_count": 2}}).json()
        project = plan["project"]["id"]
        path = f"/v1/projects/{project}/interactive-story"
        revision = 0
        if mode == "web_source":
            response = client.get(f"/v1/projects/{project}/source-text", params={"url": "https://example.com/memoir"})
            assert response.status_code == 200
            client.post(path + "/turns", json={"turn_id": "lookup", "expected_revision": 0,
                "text": "读取我自己的回忆网页，作为整个剧本", "source_mode": mode})
            saved = client.post(path + "/turns/lookup/answer", json={"expected_revision": 1,
                "reply": response.json()["text"], "outcome": "answered"})
            assert saved.status_code == 200, saved.text
            revision = saved.json()["revision"]
        for turn, text in [("write", source + "请写两集草稿" if mode == "narrated_story" else "请根据刚才来源写两集草稿"),
                           ("correct", "只改第一集：是爷爷教我，不是外婆。")]:
            pending = client.post(path + "/turns", json={"turn_id": turn, "expected_revision": revision,
                "text": text, "source_mode": "narrated_story"})
            assert pending.status_code == 200, pending.text
            generated = client.post(path + f"/turns/{turn}/generate",
                json={"expected_revision": pending.json()["revision"], "model": "fixture-model"},
                headers={"X-Nalu-Writer-Key": "synthetic-key"})
            assert generated.status_code == 200, generated.text
            revision = generated.json()["revision"]
    with TestClient(app()) as client:
        state = client.get(path).json()
        assert len(calls) == 2  # Restart never calls the writer automatically.
        assert state["episode_drafts"][0]["script"].startswith("第一集：爷爷")
        assert state["episode_drafts"][1]["script"] == "第2集：外婆教我补渔网。"
        for episode, draft in zip(plan["episodes"], state["episode_drafts"], strict=True):
            number = str(draft["episode_number"])
            created = client.post(f"/v1/episodes/{episode['id']}/scripts", json={
                "content": draft["script"], "summary_for_voice_review": draft["outline"],
                "authoring": {"origin": "external_ai_generated", "external_writer": state["draft_writers"][number]}})
            assert created.status_code == 201, created.text
            script = created.json()
            assert script["approved_at"] is None
            base = f"/v1/episodes/{episode['id']}/scripts/{script['revision']}"
            bound = client.post(base + "/writer-receipt-reconciliations", content=state["draft_receipts"][number].encode(),
                headers={"Content-Type": "application/octet-stream"}, params={"reconciled_by": "synthetic QA"})
            assert bound.status_code == 201, bound.text
            assert client.post(base + "/approve", json={"approved_by": "synthetic QA"}).status_code == 200
        assert len(calls) == 2
