from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def test_native_publication_learning_fixture_is_isolated_and_readable(tmp_path: Path) -> None:
    root = tmp_path / "native-publication-learning"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/create-native-publication-learning-fixture.py",
            "--root",
            str(root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    evidence = json.loads(completed.stdout)
    assert evidence["status"] == "READY"
    assert evidence["production_data_modified"] is False
    assert evidence["environment"]["NALU_ENABLE_LOCAL_QA"] == "1"

    api = TestClient(create_app(root / "nalu.sqlite3", root / "data"))
    projects = api.get("/v1/projects").json()
    assert [project["id"] for project in projects] == [evidence["project_id"]]
    strategies = api.get(
        f"/v1/projects/{evidence['project_id']}/director-strategies"
    ).json()
    assert len(strategies) == 1
    assert strategies[0]["production_started"] is False
    assert strategies[0]["publication_performed"] is False
    metrics = api.get(f"/v1/publication-metrics/{evidence['metrics_id']}").json()
    assert metrics["completion_rate"] == 0.52
    assert metrics["external_write_performed"] is False
    assert metrics["publication_performed"] is False
    assert metrics["production_performed"] is False


def test_native_publication_learning_fixture_refuses_nonempty_root(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    (root / "do-not-touch.txt").write_text("preserve", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/create-native-publication-learning-fixture.py",
            "--root",
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert (root / "do-not-touch.txt").read_text(encoding="utf-8") == "preserve"
