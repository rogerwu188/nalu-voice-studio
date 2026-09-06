import sqlite3
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def test_concurrent_script_adoption_is_atomic_and_survives_restart(tmp_path):
    database, data = tmp_path / "db", tmp_path / "data"
    with TestClient(create_app(database, data)) as client:
        plan = client.post("/v1/project-plans", json={"project": {
            "title": "重复采用测试", "planned_episode_count": 2}}).json()
        first, second = [ep["id"] for ep in plan["episodes"]]
        path = f"/v1/episodes/{first}/scripts"
        request = {"content": "合成故事正文", "summary_for_voice_review": "合成审阅",
                   "authoring": {"origin": "user_text"}, "idempotency_key": "same-adoption"}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: client.post(path, json=request), range(4)))
        assert all(result.status_code == 201 for result in results)
        assert {result.json()["revision"] for result in results} == {1}
        assert len(client.get(path).json()) == 1
        assert client.post(path, json={**request, "content": "不同正文"}).status_code == 409
        assert client.post(f"/v1/episodes/{second}/scripts", json=request).status_code == 201
    with TestClient(create_app(database, data)) as client:
        replay = client.post(path, json=request)
        assert replay.status_code == 201
        assert replay.json()["revision"] == 1
        assert len(client.get(path).json()) == 1
        # Omitting a retry key still allows an intentional new authoring version.
        fresh = client.post(path, json={k: v for k, v in request.items() if k != "idempotency_key"})
        assert fresh.json()["revision"] == 2
        approved = client.post(path + "/2/approve", json={"approved_by": "synthetic QA"})
        assert approved.status_code == 200
        assert client.post(path, json=request).json()["revision"] == 1
        assert client.get(f"/v1/episodes/{first}").json()["approved_script_revision"] == 2
        deleted = client.request("DELETE", f"/v1/projects/{plan['project']['id']}", json={
            "confirmation_title": "重复采用测试", "requested_by": "synthetic QA",
            "delete_production_snapshots": True})
        assert deleted.status_code == 200
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM idempotent_operations WHERE scope LIKE 'script-revision:%'").fetchone()[0] == 0
