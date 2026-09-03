from __future__ import annotations

import sqlite3

import pytest
from nalu_runtime.database import Database


def test_database_connection_commits_and_closes_on_success(tmp_path) -> None:
    database = Database(tmp_path / "nalu.sqlite3")

    with database.connect() as connection:
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")
        connection.execute("INSERT INTO example VALUES ('saved')")
        leaked_reference = connection

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        leaked_reference.execute("SELECT 1")

    with sqlite3.connect(database.path) as verifier:
        assert verifier.execute("SELECT value FROM example").fetchone() == ("saved",)


def test_database_connection_rolls_back_and_closes_on_failure(tmp_path) -> None:
    database = Database(tmp_path / "nalu.sqlite3")
    with database.connect() as connection:
        connection.execute("CREATE TABLE example (value TEXT NOT NULL)")

    with (
        pytest.raises(RuntimeError, match="stop transaction"),
        database.connect() as connection,
    ):
        connection.execute("INSERT INTO example VALUES ('not saved')")
        failed_reference = connection
        raise RuntimeError("stop transaction")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        failed_reference.execute("SELECT 1")

    with sqlite3.connect(database.path) as verifier:
        assert verifier.execute("SELECT COUNT(*) FROM example").fetchone() == (0,)


def test_repeated_database_contexts_close_even_when_callers_retain_references(
    tmp_path,
) -> None:
    database = Database(tmp_path / "nalu.sqlite3")
    retained_connections: list[sqlite3.Connection] = []

    for _ in range(128):
        with database.connect() as connection:
            assert connection.execute("SELECT 1").fetchone()[0] == 1
            retained_connections.append(connection)

    assert len(retained_connections) == 128
    for connection in retained_connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")
