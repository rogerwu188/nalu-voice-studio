#!/usr/bin/env python3
"""Exercise synthetic memory provenance over an isolated packaged loopback runtime."""
import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    if not __debug__:
        raise RuntimeError("QA assertions must be enabled; do not use Python optimization")
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None:
        raise RuntimeError("Source commit must be a full lowercase Git SHA")
    resources = args.app.resolve() / "Contents/Resources"
    binary = resources / "runtime/nalu-runtime"
    if not binary.is_file():
        raise RuntimeError("Packaged runtime missing")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    def call(path, body=None, method=None, expected=200, raw=None):
        data = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else None
        )
        request = urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "text/plain" if raw else "application/json"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            value = json.loads(response.read())
            if response.code != expected:
                raise RuntimeError(f"{path}: {response.code}, expected {expected}")
            return value

    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("NALU_") and not any(
            marker in key.upper() for marker in ("TOKEN", "SECRET", "API_KEY", "CREDENTIAL")
        )
    }
    environment.update(
        NALU_RUNTIME_PORT=str(port), NALU_ALLOW_PAID_SUBMISSION="false",
        NALU_ALLOW_PUBLICATION="false",
        NALU_REPOSITORY_ROOT=str(resources / "runtime-resources"),
    )
    with tempfile.TemporaryDirectory(prefix="nalu-memory-provenance-") as temporary:
        root = Path(temporary)

        def start(label):
            process = subprocess.Popen([str(binary)], env=environment | {
                "NALU_DATABASE_PATH": str(root / f"{label}.sqlite3"),
                "NALU_DATA_ROOT": str(root / label),
            }, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(240):
                    if process.poll() is not None:
                        raise RuntimeError("Isolated runtime exited")
                    try:
                        call("/health")
                        return process
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.25)
                raise RuntimeError("Isolated runtime startup timeout")
            except BaseException:
                stop(process)
                raise

        def stop(process):
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        process = start("original")
        try:
            project = call("/v1/projects", {"title": "Synthetic memory QA"}, expected=201)
            prefix = f"/v1/projects/{project['id']}"
            asset = call(prefix + "/asset-imports?filename=fixture.txt&kind=source_document&name=fixture",
                         raw=b"Synthetic year 1982", expected=201)
            card = call(prefix + "/memory-cards", {
                "asset_id": asset["id"], "title": "Synthetic memory",
                "ocr_text": "Synthetic year 1982", "approximate_date": "1982",
                "allowed_use": "reference_only",
            }, expected=201)
            path = f"/v1/memory-cards/{card['id']}"
            approval = {"confirmed_by": "QA fixture", "reviewed_revision": 1,
                        "review_channel": "visual",
                        "spoken_confirmation": "Synthetic visual QA confirmation"}
            call(path + "/confirm", approval)
            changed = call(path, {"approximate_date": "1983", "source_channel": "visual",
                                 "change_summary": "Synthetic correction"}, method="PATCH")
            assert changed["confirmation_status"] == "draft"
            history = call(path + "/revisions")
            receipts = call(path + "/confirmations")
            backup = call(prefix + "/export")
        finally:
            stop(process)
        process = start("restored")
        try:
            call("/v1/project-imports", backup, expected=201)
            assert call(prefix + "/memory-cards?confirmed_only=true") == []
            restored = call(prefix + "/memory-cards")[0]
            assert restored["ocr_text"] == "Synthetic year 1982"
            assert restored["approximate_date"] == "1983"
            assert restored["current_revision"] == 2
            assert restored["confirmation_status"] == "draft"
            assert call(path + "/revisions") == history
            assert call(path + "/confirmations") == receipts
            call(path + "/confirm", approval, expected=409)
            narrative = call(path, {
                "allowed_use": "story_development", "source_channel": "visual",
                "change_summary": "Synthetic fixture permitted for story QA only",
            }, method="PATCH")
            call(path + "/confirm", approval | {
                "reviewed_revision": narrative["current_revision"]
            })
            other_asset = call(
                prefix + "/asset-imports?filename=second.txt&kind=source_document&name=second",
                raw=b"Synthetic conflicting year 1985", expected=201,
            )
            other = call(prefix + "/memory-cards", {
                "asset_id": other_asset["id"], "title": "Synthetic memory",
                "approximate_date": "1985", "allowed_use": "story_development",
            }, expected=201)
            other_path = f"/v1/memory-cards/{other['id']}"
            assert call(other_path + "/conflicts")["blocking"] is True
            call(other_path + "/confirm", approval, expected=409)
            corrected = call(other_path, {
                "approximate_date": "1983", "source_channel": "visual",
                "change_summary": "Synthetic conflict correction",
            }, method="PATCH")
            assert corrected["confirmation_status"] == "draft"
            assert call(other_path + "/conflicts")["blocking"] is False
            assert [item["id"] for item in call(
                prefix + "/memory-cards?confirmed_only=true"
            )] == [card["id"]]
            call(other_path + "/confirm", approval, expected=409)
            assert call(other_path + "/confirmations") == []
            call(other_path + "/confirm", approval | {"reviewed_revision": 2})
            assert len(call(prefix + "/memory-cards?confirmed_only=true")) == 2
        finally:
            stop(process)
    evidence = {
        "schema_version": "nalu.memory-provenance-qa/v1", "status": "PASS",
        "source_commit": args.source_commit,
        "runtime_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "runtime_mode": "packaged", "network_scope": "loopback only",
        "restored_revision": 2, "original_ocr_preserved": True,
        "history_preserved": True, "stale_confirmation_rejected": True,
        "conflict_resolution_requires_fresh_confirmation": True,
        "paid_call_performed": False, "native_ui_acceptance": False,
        "human_voice_acceptance": False, "project_complete": False,
    }
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
