#!/usr/bin/env python3
"""Start the packaged runtime process and verify it over real loopback HTTP."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = 18765
BASE_URL = f"http://127.0.0.1:{PORT}"


def request(path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read())


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nalu-http-smoke-") as directory:
        root = Path(directory)
        environment = os.environ.copy()
        environment["NALU_DATA_ROOT"] = str(root / "data")
        environment["NALU_DATABASE_PATH"] = str(root / "nalu.sqlite3")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "nalu_runtime.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            env=environment,
        )
        try:
            for _ in range(40):
                try:
                    status, health = request("/health")
                    if status == 200 and health["status"] == "ok":
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("runtime did not become healthy")

            status, openapi = request("/openapi.json")
            materialization_route = (
                "/v1/production-runs/{run_id}/postproduction-materializations"
            )
            if status != 200 or materialization_route not in openapi["paths"]:
                raise RuntimeError("postproduction materialization route is absent over HTTP")

            status, project = request("/v1/projects", {"title": "HTTP smoke project"})
            if status != 201 or not project["id"].startswith("prj_"):
                raise RuntimeError("project creation failed over HTTP")
            print("Real HTTP smoke test passed")
            return 0
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
