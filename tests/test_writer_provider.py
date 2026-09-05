import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.writer_provider import WriterProviderVerification


class DeterministicWriterVerifier:
    def __init__(self, *, failure: bool = False, wrong_model: bool = False):
        self.failure = failure
        self.wrong_model = wrong_model
        self.calls = 0

    def lookup_writer_task(self, **request) -> WriterProviderVerification:
        self.calls += 1
        if self.failure:
            raise RuntimeError("simulated unexpected transport failure")
        return WriterProviderVerification(
            provider=request["provider"],
            model_id="wrong-model" if self.wrong_model else request["model_id"],
            session_or_task_id=request["session_or_task_id"],
            state="completed",
            receipt_sha256=request["receipt_sha256"],
            started_at="2026-09-03T20:00:00+00:00",
            completed_at="2026-09-03T20:01:00+00:00",
            evidence={"source": "deterministic-read-only-fixture", "authenticated": True},
        )


def api_client(tmp_path: Path, verifier=None) -> TestClient:
    return TestClient(
        create_app(
            tmp_path / "test.sqlite3",
            tmp_path / "data",
            writer_provider_verifier=verifier,
        )
    )


def create_artifact_bound_writer_script(api: TestClient) -> tuple[str, str, dict, dict]:
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "远端 Writer 核验", "planned_episode_count": 1}},
    ).json()
    project_id = plan["project"]["id"]
    episode_id = plan["episodes"][0]["id"]
    content = "远端 Writer 生成的权威输出"
    declaration = {
        "provider": "anthropic",
        "model_id": "claude-opus-4-1-20250805",
        "session_or_task_id": "writer-task-provider-001",
        "input_bundle_sha256": "a" * 64,
        "writer_rules_sha256": "b" * 64,
        "started_at": "2026-09-03T20:00:00+00:00",
        "completed_at": "2026-09-03T20:01:00+00:00",
    }
    receipt = {
        "schema": "qingshan.canonical_writer_run_receipt.v1",
        "status": "COMPLETED",
        "writer_run_id": "WRITER-E1-V1-PROVIDER001",
        "episode": "E1",
        "version": 1,
        "agent_id": "qingshan-claude-writer-agent",
        **declaration,
        "input_bundle": {"sha256": declaration["input_bundle_sha256"]},
        "writer_rules": {"combined_sha256": declaration["writer_rules_sha256"]},
        "authority_output": {"sha256": hashlib.sha256(content.encode()).hexdigest()},
    }
    receipt_bytes = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
    declaration["receipt_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    script = api.post(
        f"/v1/episodes/{episode_id}/scripts",
        json={
            "content": content,
            "summary_for_voice_review": "远端 Writer 剧本",
            "authoring": {
                "origin": "external_ai_generated",
                "external_writer": declaration,
            },
        },
    ).json()
    artifact = api.post(
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}"
        "/writer-receipt-reconciliations",
        content=receipt_bytes,
        headers={"Content-Type": "application/octet-stream"},
        params={"reconciled_by": "本地 QA"},
    )
    assert artifact.status_code == 201
    return project_id, episode_id, script, artifact.json()


def test_writer_provider_reconciliation_is_read_only_idempotent_and_packaged(
    tmp_path: Path,
) -> None:
    verifier = DeterministicWriterVerifier()
    api = api_client(tmp_path, verifier)
    project_id, episode_id, script, artifact = create_artifact_bound_writer_script(api)
    endpoint = (
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}"
        "/writer-provider-reconciliation"
    )
    request = {
        "writer_receipt_record_sha256": artifact["record_sha256"],
        "confirmation_text": "我确认只读核验 Writer 任务",
    }
    assert api.post(endpoint, json=request).status_code == 409
    assert verifier.calls == 0
    assert (
        api.post(
            endpoint,
            json={**request, "confirmation_text": "帮我看看"},
            headers={"Idempotency-Key": "writer-provider-check-001"},
        ).status_code
        == 409
    )
    assert verifier.calls == 0
    response = api.post(
        endpoint,
        json=request,
        headers={"Idempotency-Key": "writer-provider-check-001"},
    )
    assert response.status_code == 201
    record = response.json()
    assert record["provider_execution_verified"] is True
    assert record["read_only_verification_performed"] is True
    assert record["generation_performed_by_runtime"] is False
    assert record["paid_generation_performed_by_runtime"] is False
    assert record["external_write_performed"] is False
    assert record["writer_receipt_record_sha256"] == artifact["record_sha256"]
    assert verifier.calls == 1
    assert (
        api.post(
            endpoint,
            json=request,
            headers={"Idempotency-Key": "writer-provider-check-001"},
        ).json()
        == record
    )
    assert verifier.calls == 1
    assert (
        api.post(
            endpoint,
            json=request,
            headers={"Idempotency-Key": "writer-provider-check-002"},
        ).status_code
        == 409
    )
    assert verifier.calls == 1

    approved = api.post(
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认这个剧本"},
    )
    assert approved.status_code == 200
    run = api.post(
        f"/v1/episodes/{episode_id}/production-runs",
        json={"dry_run": True, "requested_model": "seedance-2.0-pro"},
    )
    assert run.status_code == 201
    package = json.loads(Path(run.json()["package_path"]).read_text(encoding="utf-8"))
    assert package["writer_provider_reconciliation"] == record

    backup = api.get(f"/v1/projects/{project_id}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v23"
    assert len(backup["payload"]["script_writer_provider_reconciliations"]) == 1
    restored = api_client(tmp_path / "restored")
    assert restored.post("/v1/project-imports", json=backup).status_code == 201
    assert restored.get(endpoint).json() == record

    compatible_v21 = deepcopy(backup)
    compatible_v21["schema_version"] = "nalu.project-export/v21"
    compatible_v21["payload"].pop("production_route_decisions")
    compatible_v21["payload"].pop("script_writer_provider_reconciliations")
    compatible_v21["payload_sha256"] = hashlib.sha256(
        json.dumps(compatible_v21["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert (
        api_client(tmp_path / "restored-v21")
        .post("/v1/project-imports", json=compatible_v21)
        .status_code
        == 201
    )

    tampered = deepcopy(backup)
    row = tampered["payload"]["script_writer_provider_reconciliations"][0]
    body = json.loads(row["record_json"])
    body["provider_execution_verified"] = False
    row["record_json"] = json.dumps(body, ensure_ascii=False, sort_keys=True)
    row["record_sha256"] = hashlib.sha256(row["record_json"].encode()).hexdigest()
    tampered["payload_sha256"] = hashlib.sha256(
        json.dumps(tampered["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert (
        api_client(tmp_path / "tampered")
        .post("/v1/project-imports", json=tampered)
        .status_code
        == 409
    )


def test_writer_provider_failure_is_quarantined_without_automatic_retry(tmp_path: Path) -> None:
    verifier = DeterministicWriterVerifier(failure=True)
    api = api_client(tmp_path, verifier)
    project_id, episode_id, script, artifact = create_artifact_bound_writer_script(api)
    endpoint = (
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}"
        "/writer-provider-reconciliation"
    )
    request = {
        "writer_receipt_record_sha256": artifact["record_sha256"],
        "confirmation_text": "我确认只读核验 Writer 任务",
    }
    headers = {"Idempotency-Key": "writer-provider-ambiguous-001"}
    first = api.post(endpoint, json=request, headers=headers)
    assert first.status_code == 409
    assert "quarantined" in first.text
    assert verifier.calls == 1
    assert api.post(endpoint, json=request, headers=headers).status_code == 409
    assert verifier.calls == 1
    assert api.get(endpoint).status_code == 409

    backup = api.get(f"/v1/projects/{project_id}/export").json()
    row = backup["payload"]["script_writer_provider_reconciliations"][0]
    assert row["state"] == "ambiguous"
    assert row["record_json"] is None
    assert row["record_sha256"] is None
    restored = api_client(tmp_path / "restored-ambiguous")
    assert restored.post("/v1/project-imports", json=backup).status_code == 201
    assert restored.get(endpoint).status_code == 409


def test_writer_provider_mismatch_and_database_tampering_fail_closed(tmp_path: Path) -> None:
    verifier = DeterministicWriterVerifier(wrong_model=True)
    api = api_client(tmp_path, verifier)
    _, episode_id, script, artifact = create_artifact_bound_writer_script(api)
    endpoint = (
        f"/v1/episodes/{episode_id}/scripts/{script['revision']}"
        "/writer-provider-reconciliation"
    )
    assert (
        api.post(
            endpoint,
            json={
                "writer_receipt_record_sha256": artifact["record_sha256"],
                "confirmation_text": "我确认只读核验 Writer 任务",
            },
            headers={"Idempotency-Key": "writer-provider-mismatch-001"},
        ).status_code
        == 409
    )
    assert verifier.calls == 1

    successful_path = tmp_path / "successful"
    successful_verifier = DeterministicWriterVerifier()
    successful = api_client(successful_path, successful_verifier)
    _, successful_episode, successful_script, successful_artifact = (
        create_artifact_bound_writer_script(successful)
    )
    successful_endpoint = (
        f"/v1/episodes/{successful_episode}/scripts/{successful_script['revision']}"
        "/writer-provider-reconciliation"
    )
    assert (
        successful.post(
            successful_endpoint,
            json={
                "writer_receipt_record_sha256": successful_artifact["record_sha256"],
                "confirmation_text": "我确认只读核验 Writer 任务",
            },
            headers={"Idempotency-Key": "writer-provider-tamper-001"},
        ).status_code
        == 201
    )
    with sqlite3.connect(successful_path / "test.sqlite3") as connection:
        connection.execute(
            "UPDATE script_writer_provider_reconciliations SET updated_at = ? "
            "WHERE episode_id = ? AND script_revision = ?",
            ("2099-01-01T00:00:00+00:00", successful_episode, successful_script["revision"]),
        )
    assert successful.get(successful_endpoint).status_code == 409
