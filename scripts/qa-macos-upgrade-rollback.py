#!/usr/bin/env python3
"""Offline Runtime restart and backup rollback rehearsal; never downloads or installs an update."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"


def digest(value):
    if isinstance(value, Path):
        return hashlib.sha256(value.read_bytes()).hexdigest()
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def call(path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def need(path, body=None, code=200):
    actual, value = call(path, body)
    if actual != code:
        raise RuntimeError(f"{path}: expected {code}, got {actual}: {value}")
    return value


def launch(command, env):
    process = subprocess.Popen(command, env=env)
    for _ in range(240):
        try:
            if need("/health")["status"] == "ok":
                return process
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        if process.poll() is not None:
            raise RuntimeError(f"Runtime exited: {process.returncode}")
        time.sleep(0.25)
    process.kill()
    process.wait()
    raise RuntimeError("Runtime startup timed out")


def stop(process):
    process.terminate()
    try:
        process.wait(10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    try:
        call("/health")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return
    raise RuntimeError("Runtime is still listening after shutdown")


def snapshot(project_id):
    seasons = need(f"/v1/projects/{project_id}/seasons")
    episodes = need(f"/v1/seasons/{seasons[0]['id']}/episodes")
    result = {
        "project_id": project_id,
        "episode_numbers": [e["episode_number"] for e in episodes],
        "statuses": [e["status"] for e in episodes],
    }
    if result["episode_numbers"] != list(range(1, 11)) or set(result["statuses"]) != {
        "script_approved"
    }:
        raise RuntimeError(f"project changed: {result}")
    return result


def populate():
    project = need(
        "/v1/projects",
        {
            "title": "升级回滚验收：十集家庭故事",
            "audience_mode": "older_adult",
            "planned_episode_count": 10,
            "project_bible": {"qa_fixture": True},
        },
        201,
    )
    season = need(
        f"/v1/projects/{project['id']}/seasons",
        {"title": "第一季", "season_number": 1, "planned_episode_count": 10},
        201,
    )
    for n in range(1, 11):
        episode = need(
            f"/v1/seasons/{season['id']}/episodes",
            {"title": f"第 {n} 集", "episode_number": n, "target_seconds": 120},
            201,
        )
        script = need(
            f"/v1/episodes/{episode['id']}/scripts",
            {"content": f"第 {n} 集定稿剧本", "summary_for_voice_review": f"第 {n} 集摘要"},
            201,
        )
        need(
            f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
            {"approved_by": "upgrade-rollback-qa", "spoken_confirmation": "我确认这个剧本"},
        )
    return project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if args.app:
        resources = args.app / "Contents/Resources"
        runtime = resources / "runtime/nalu-runtime"
        analyzer = resources / "analyzers/nalu-visual-analyzer"
        if not runtime.is_file() or not analyzer.is_file() or not os.access(runtime, os.X_OK):
            raise RuntimeError("invalid packaged app")
        command = [str(runtime)]
        extra = {
            "NALU_REPOSITORY_ROOT": str(resources / "runtime-resources"),
            "NALU_VISUAL_ANALYZER_BINARY": str(analyzer),
        }
        mode = "packaged"
    else:
        command = [sys.executable, "-m", "nalu_runtime"]
        extra = {}
        mode = "source"
    with tempfile.TemporaryDirectory(prefix="nalu-upgrade-rollback-") as temporary:
        root = Path(temporary)
        db = root / "current.sqlite3"
        data = root / "current-data"
        env = os.environ | extra | {"NALU_DATABASE_PATH": str(db), "NALU_DATA_ROOT": str(data)}
        p = launch(command, env)
        try:
            project = populate()
            before = snapshot(project["id"])
            backup = need(f"/v1/projects/{project['id']}/export")
            health = need("/health")
        finally:
            stop(p)
        p = launch(command, env)
        try:
            after = snapshot(project["id"])
            health_after = need("/health")
        finally:
            stop(p)
        rollback_db = root / "rollback.sqlite3"
        rollback_data = root / "rollback-data"
        rollback_env = (
            os.environ
            | extra
            | {"NALU_DATABASE_PATH": str(rollback_db), "NALU_DATA_ROOT": str(rollback_data)}
        )
        p = launch(command, rollback_env)
        try:
            restored = need("/v1/project-imports", backup, 201)
            rolled = snapshot(restored["id"])
            restored_backup = need(f"/v1/projects/{restored['id']}/export")
        finally:
            stop(p)
        backup_sha256 = backup["payload_sha256"]
        if (
            before != after
            or before != rolled
            or backup_sha256 != restored_backup["payload_sha256"]
            or health["schema_version"] != health_after["schema_version"]
        ):
            raise RuntimeError("upgrade/rollback preservation failed")
        report = {
            "schema_version": "nalu.macos-upgrade-rollback-qa/v1",
            "status": "PASS",
            "runtime_mode": mode,
            "scope": "Runtime restart and clean backup rollback only; not a signed/notarized app update",
            "project": before,
            "schema_version_before": health["schema_version"],
            "schema_version_after_restart": health_after["schema_version"],
            "backup_sha256": backup_sha256,
            "restart_state_preserved": True,
            "clean_backup_rollback_preserved": True,
            "network_scope": "loopback only; no update download, provider, paid model or publication",
        }
        report["report_sha256"] = digest(report)
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
