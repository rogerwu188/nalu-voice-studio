"""Synthetic contract tests, never actual human viewing/acceptance evidence."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_final_qa_evidence import evidence
from test_rendered_output_immutability import client, prepare_semantic_qa_fixture


def setup_review(tmp_path):
    api = client(tmp_path)
    run, master_sha = prepare_semantic_qa_fixture(api)
    base = f"/v1/production-runs/{run['id']}"
    seal = api.get(base + "/rendered-output-integrity").json()["seal"]
    payload = evidence() | {
        "run_id": run["id"], "master_sha256": master_sha,
        "idempotency_key": "explicit-human-decision",
        "output_seal_sha256": seal["manifest_sha256"],
    }
    return api, run, base, payload


def test_failed_decision_recovers_and_blocks_completion(tmp_path):
    api, _run, base, payload = setup_review(tmp_path)
    payload["picture_passed"] = False
    assert api.post(base + "/final-human-review", json=payload).status_code == 201
    restarted = client(tmp_path)
    recovered = restarted.get(base + "/final-human-review")
    assert recovered.status_code == 200
    assert recovered.json()["picture_passed"] is False
    assert restarted.post(base + "/final-human-review", json=payload).status_code == 201
    changed = payload | {"picture_passed": True}
    assert restarted.post(base + "/final-human-review", json=changed).status_code == 409
    completion = restarted.post(base + "/complete", json={
        "output_seal_sha256": payload["output_seal_sha256"],
        "completed_by": "test", "spoken_confirmation": "我确认这份成片和人工质量检查记录",
    })
    assert completion.status_code == 409, completion.text
    repair = restarted.get(base + "/postproduction-repair-plan").json()
    assert "picture_passed" in [task["code"] for task in repair["repair_tasks"]]
    assert restarted.get(base).json()["status"] == "qa_review"


@pytest.mark.parametrize("field", ["run_id", "master_sha256", "output_seal_sha256"])
def test_wrong_binding_does_not_persist(tmp_path, field):
    api, run, base, payload = setup_review(tmp_path)
    payload[field] = "b" * 64
    assert api.post(base + "/final-human-review", json=payload).status_code == 409
    assert api.get(base + "/final-human-review").status_code == 409
    assert not (Path(run["package_path"]).parent / "final-human-qa.json").exists()


def test_tampered_review_and_changed_master_fail_closed(tmp_path):
    api, run, base, payload = setup_review(tmp_path)
    assert api.post(base + "/final-human-review", json=payload).status_code == 201
    path = Path(run["package_path"]).parent / "final-human-qa.json"
    original = path.read_bytes()
    envelope = json.loads(original)
    envelope["submission"]["picture_passed"] = False
    path.write_text(json.dumps(envelope))
    assert api.get(base + "/final-human-review").status_code == 409
    assert api.post(base + "/final-human-review", json=payload).status_code == 409
    path.write_bytes(original)
    master = path.parent / "qingshan-workspace/exports/E01_MASTER.mp4"
    master.write_bytes(master.read_bytes() + b"tampered")
    assert api.get(base + "/final-human-review").status_code == 409


def test_concurrent_conflicting_decisions_do_not_overwrite(tmp_path):
    api, _run, base, payload = setup_review(tmp_path)
    variants = [payload, payload | {"picture_passed": False, "idempotency_key": "other"}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(
            lambda value: api.post(base + "/final-human-review", json=value), variants,
        ))
    assert sorted(response.status_code for response in responses) == [201, 409]
    winner = next(i for i, response in enumerate(responses) if response.status_code == 201)
    restarted = client(tmp_path)
    assert restarted.get(base + "/final-human-review").json() == responses[winner].json()
    assert restarted.post(base + "/final-human-review", json=variants[winner]).status_code == 201
