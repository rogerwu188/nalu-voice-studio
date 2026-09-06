import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.repository import ConflictError
from nalu_runtime.writer_execution import WriterExecution


def test_writer_execution_commits_before_transport_and_replays_after_restart(tmp_path):
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "synthetic ledger"}).json()["id"]
        db = app.state.repository.db
        ledger = WriterExecution(db)
        calls = []

        def transport(body):
            with db.connect() as connection:
                assert connection.execute("SELECT state FROM writer_executions").fetchone()[0] == "submitting"
            calls.append(body)
            return b'{"id":"synthetic-response"}'

        kwargs = {"destination": "https://provider.invalid/v1", "transport": transport}
        result = ledger.execute(project, "turn", b"request", **kwargs)
        assert WriterExecution(db).execute(project, "turn", b"request", **kwargs) == result
        assert len(calls) == 1
        with pytest.raises(ConflictError):
            ledger.execute(project, "turn", b"changed", **kwargs)
        with pytest.raises(ConflictError):
            ledger.execute(project, "turn", b"request", destination="https://other.invalid", transport=transport)


def test_ambiguous_execution_never_retries_or_persists_exception_secrets(tmp_path):
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "synthetic failure"}).json()["id"]
        db = app.state.repository.db
        calls = []

        def transport(body):
            calls.append(body)
            raise TimeoutError("secret-must-not-be-recorded")

        with pytest.raises(TimeoutError):
            WriterExecution(db).execute(project, "turn", b"request", destination="fixture", transport=transport)
        with pytest.raises(ConflictError):
            WriterExecution(db).execute(project, "turn", b"request", destination="fixture", transport=transport)
        with db.connect() as connection:
            row = dict(connection.execute("SELECT * FROM writer_executions").fetchone())
        assert row["state"] == "ambiguous"
        assert "secret-must-not-be-recorded" not in str(row)
        assert len(calls) == 1


def test_inflight_duplicate_does_not_send_a_second_request(tmp_path):
    app = create_app(tmp_path / "db", tmp_path / "data")
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"title": "synthetic concurrent"}).json()["id"]
        db = app.state.repository.db
        started, release = threading.Event(), threading.Event()

        def transport(body):
            started.set()
            assert release.wait(5)
            return b'{}'

        def execute():
            return WriterExecution(db).execute(project, "turn", b"request", destination="fixture", transport=transport)

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(execute)
            assert started.wait(5)
            try:
                with pytest.raises(ConflictError):
                    execute()
            finally:
                release.set()
            assert pending.result() == b'{}'
