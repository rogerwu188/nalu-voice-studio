import importlib.util
import plistlib
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx


def test_live_qa_redacts_unauthorized_response_and_does_not_retry(tmp_path, monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / "scripts/qa-live-story-writer.py"
    spec = importlib.util.spec_from_file_location("live_story_qa", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    secret = "fixture-secret-never-log"
    calls = []
    def command(args, **kwargs):
        output = plistlib.dumps({"nalu.ai-service-base-url": "https://hopsapi.com/v1"}) if args[0] == "defaults" else secret.encode()
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr=b"")
    monkeypatch.setattr(module.subprocess, "run", command)
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            calls.append(url)
            assert kwargs["headers"]["Authorization"] == "Bearer " + secret
            return httpx.Response(401, text=secret, request=httpx.Request("POST", url))
    monkeypatch.setattr(module.httpx, "Client", Client)
    monkeypatch.setattr(sys, "argv", [str(path), "--execute-authorized-text-request",
        "--evidence-directory", str(tmp_path)])
    assert module.main() == 1
    assert module.main() == 2
    assert len(calls) == 1
    assert secret not in capsys.readouterr().out
    with sqlite3.connect(tmp_path / "writer-attempt.sqlite3") as database:
        state, evidence = database.execute("SELECT state,evidence FROM attempt").fetchone()
    assert state == "needs_review"
    assert secret not in evidence
