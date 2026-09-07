"""Synthetic HTTP journey, not real-provider or installed macOS acceptance."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


@pytest.mark.parametrize("source_mode", ["narrated_story", "web_source"])
def test_source_to_revised_two_episode_production_package(tmp_path, monkeypatch, source_mode):
    source_text = "合成回忆：外婆和六岁的我住在海边。"
    source_url = "https://example.com/family-story"
    monkeypatch.setattr("nalu_runtime.app.read_public_source", lambda url: {
        "requested_url": url, "url": url, "text": source_text,
        "truncated": False, "scope": "single_page_excerpt",
    })
    calls = []
    drafts = [{"episode_number": n, "title": f"海边第{n}集", "outline": "祖孙的回忆",
               "script": f"第{n}集：外婆带六岁的我来到码头。"} for n in (1, 2)]

    def serve(request):
        context = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(context)
        assert source_text in json.dumps(context, ensure_ascii=False)
        if len(calls) == 2:
            assert context["episode_drafts"] == drafts
            assert context["turns"][-1]["text"] == "只把第二集改成在灯塔见面，第一集不要动。"
        updated = drafts if len(calls) == 1 else [dict(drafts[1], script="第二集：祖孙在灯塔见面。")]
        return httpx.Response(200, json={"id": f"fixture-writing-{len(calls)}", "model": "fixture-model",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "reply": "请核对这版剧本。", "summary": source_text,
                "episode_drafts": updated, "outcome": "answered"}, ensure_ascii=False)}}]})

    def application():
        return create_app(tmp_path / "db", tmp_path / "data", writer_http_transport=httpx.MockTransport(serve))

    with TestClient(application()) as client:
        plan = client.post("/v1/project-plans", json={"project": {
            "title": "合成两来源旅程", "planned_episode_count": 2}}).json()
        project_id = plan["project"]["id"]
        path = f"/v1/projects/{project_id}/interactive-story"
        revision = 0
        if source_mode == "web_source":
            source = client.get(f"/v1/projects/{project_id}/source-text", params={"url": source_url})
            assert source.status_code == 200
            assert client.post(path + "/turns", json={"turn_id": "lookup", "expected_revision": revision,
                "text": f"请从{source_url}找资料，写成两集", "source_mode": source_mode}).status_code == 200
            saved = client.post(path + "/turns/lookup/answer", json={"expected_revision": 1,
                "reply": source.json()["text"] + "\n来源：" + source_url, "episode_drafts": []})
            assert saved.status_code == 200
            revision = saved.json()["revision"]
        for turn_id, text in [("write", source_text + "请写成两集" if source_mode == "narrated_story"
                               else "请用刚才找到的资料写成两集"),
                              ("revise", "只把第二集改成在灯塔见面，第一集不要动。")]:
            pending = client.post(path + "/turns", json={"turn_id": turn_id, "expected_revision": revision,
                "text": text, "source_mode": source_mode})
            assert pending.status_code == 200
            answer = client.post(path + f"/turns/{turn_id}/generate", json={
                "expected_revision": pending.json()["revision"], "model": "fixture-model"},
                headers={"X-Nalu-Writer-Key": "synthetic-test-key"})
            assert answer.status_code == 200, answer.text
            state = answer.json()
            revision = state["revision"]
        assert state["episode_drafts"][0] == drafts[0]
        assert state["episode_drafts"][1]["script"] == "第二集：祖孙在灯塔见面。"
        assert len(calls) == 2

    # Restart must restore the reviewed writing context without another AI call.
    with TestClient(application()) as client:
        assert client.get(path).json() == state
        for number, episode in enumerate(plan["episodes"], 1):
            script_path = f"/v1/episodes/{episode['id']}/scripts"
            content = state["episode_drafts"][number - 1]["script"]
            result = client.post(script_path, json={"content": content, "summary_for_voice_review": content,
                "authoring": {"origin": "external_ai_generated",
                              "external_writer": state["draft_writers"][str(number)]}})
            assert result.status_code == 201, result.text
            script = result.json()
            assert script["approved_at"] is None
            version_path = script_path + f"/{script['revision']}"
            receipt = client.post(version_path + "/writer-receipt-reconciliations",
                content=state["draft_receipts"][str(number)].encode(),
                headers={"Content-Type": "application/octet-stream"}, params={"reconciled_by": "synthetic QA"})
            assert receipt.status_code == 201, receipt.text
            assert client.post(version_path + "/approve", json={"approved_by": "synthetic QA"}).status_code == 200
            run = client.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True})
            assert run.status_code == 201, run.text
            package = json.loads(Path(run.json()["package_path"]).read_text())
            assert package["approved_script"]["content"] == content
            assert state["episode_drafts"][2 - number]["script"] not in json.dumps(package, ensure_ascii=False)
        assert len(calls) == 2
