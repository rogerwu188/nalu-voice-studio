import hashlib
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.repository import ConflictError, encode
from nalu_runtime.writer_execution import WriterExecution


@pytest.mark.parametrize("outcome", ["completed", "interrupted", "timeout"])
def test_export_preserves_execution_and_import_never_resubmits(tmp_path, outcome):
    original = create_app(tmp_path / "original.sqlite3", tmp_path / "original-data")
    restored = create_app(tmp_path / "restored.sqlite3", tmp_path / "restored-data")
    with TestClient(original) as source, TestClient(restored) as destination:
        project = source.post("/v1/projects", json={"title": "synthetic ledger backup"}).json()["id"]
        ledger = WriterExecution(original.state.repository.db)
        def transport(body):
            if outcome == "interrupted":
                raise SystemExit("synthetic process loss")
            if outcome == "timeout":
                raise TimeoutError("synthetic timeout")
            return b'{"id":"synthetic-response"}'
        if outcome == "completed":
            ledger.execute(project, "turn", b"request", destination="fixture", transport=transport)
        else:
            with pytest.raises((SystemExit, TimeoutError)):
                ledger.execute(project, "turn", b"request", destination="fixture", transport=transport)
        backup = source.get(f"/v1/projects/{project}/export").json()
        assert backup["schema_version"] == "nalu.project-export/v24"
        assert len(backup["payload"]["writer_executions"]) == 1
        result = destination.post("/v1/project-imports", json=backup)
        assert result.status_code == 201, result.text
        with restored.state.repository.db.connect() as connection:
            row = dict(connection.execute("SELECT * FROM writer_executions").fetchone())
        assert row["state"] == "ambiguous"
        assert row["response_json"] == backup["payload"]["writer_executions"][0]["response_json"]
        def forbidden(body):
            pytest.fail("restored attempts must never automatically resubmit")
        with pytest.raises(ConflictError):
            WriterExecution(restored.state.repository.db).execute(
                project, "turn", b"request", destination="fixture", transport=forbidden)


def test_corrupt_response_is_rejected_even_with_recomputed_export_digest(tmp_path):
    original = create_app(tmp_path / "original.sqlite3", tmp_path / "original-data")
    target = create_app(tmp_path / "target.sqlite3", tmp_path / "target-data")
    with TestClient(original) as source, TestClient(target) as destination:
        project = source.post("/v1/projects", json={"title": "synthetic corruption"}).json()["id"]
        WriterExecution(original.state.repository.db).execute(
            project, "turn", b"request", destination="fixture", transport=lambda body: b'{}')
        backup = deepcopy(source.get(f"/v1/projects/{project}/export").json())
        backup["payload"]["writer_executions"][0]["response_json"] = '{"changed":true}'
        backup["payload_sha256"] = hashlib.sha256(encode(backup["payload"]).encode()).hexdigest()
        assert destination.post("/v1/project-imports", json=backup).status_code == 409
        assert destination.get("/v1/projects").json() == []
