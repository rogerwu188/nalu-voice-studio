#!/usr/bin/env python3
"""Rehearse multi-project planning isolation over the real loopback Runtime API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

BASE = "http://127.0.0.1:8765"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def export_digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def validate_report(report: dict[str, object]) -> dict[str, object]:
    if report.get("schema_version") != "nalu.project-plan-isolation-qa/v1":
        raise RuntimeError("planning-isolation report schema is unsupported")
    if report.get("status") != "PASS":
        raise RuntimeError("planning-isolation report did not pass")
    if not isinstance(report.get("source_commit"), str) or not SHA_PATTERN.fullmatch(
        report["source_commit"]
    ):
        raise RuntimeError("planning-isolation source commit is malformed")
    if report.get("runtime_mode") not in {"source", "packaged"}:
        raise RuntimeError("planning-isolation runtime mode is invalid")
    if report.get("project_count") != 3 or report.get("episodes_per_project") != 10:
        raise RuntimeError("planning-isolation project matrix is incomplete")
    required_true = {
        "concurrent_atomic_planning",
        "identifier_sets_disjoint",
        "cross_project_edit_isolated",
        "approved_episode_immutable",
        "export_restore_preserved",
        "structural_cross_project_restore_rejected",
    }
    if any(report.get(field) is not True for field in required_true):
        raise RuntimeError("planning-isolation safety claim failed")
    required_false = {
        "paid_call_performed",
        "publication_performed",
        "external_write_performed",
        "human_acceptance_performed",
        "project_complete",
    }
    if any(report.get(field) is not False for field in required_false):
        raise RuntimeError("planning-isolation report overclaims or performed an external write")
    if report.get("network_scope") != "loopback only":
        raise RuntimeError("planning-isolation network scope is not offline")
    if (
        not isinstance(report.get("runtime_schema_version"), str)
        or not report["runtime_schema_version"].isdigit()
    ):
        raise RuntimeError("planning-isolation Runtime schema is malformed")
    if not isinstance(report.get("project_snapshot_sha256"), str) or not DIGEST_PATTERN.fullmatch(
        report["project_snapshot_sha256"]
    ):
        raise RuntimeError("planning-isolation snapshot digest is malformed")
    backup_digests = report.get("backup_payload_sha256")
    if (
        not isinstance(backup_digests, list)
        or len(backup_digests) != 3
        or any(
            not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value)
            for value in backup_digests
        )
    ):
        raise RuntimeError("planning-isolation backup digests are malformed")
    declared_digest = report.get("report_sha256")
    body = {key: value for key, value in report.items() if key != "report_sha256"}
    if not isinstance(declared_digest, str) or declared_digest != digest(body):
        raise RuntimeError("planning-isolation canonical digest does not match")
    return report


def call(
    path: str,
    body: object | None = None,
    headers: dict[str, str] | None = None,
    method: str | None = None,
):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        BASE + path,
        data=data,
        headers=request_headers,
        method=method or ("POST" if data is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def need(
    path: str,
    body: object | None = None,
    code: int = 200,
    headers: dict[str, str] | None = None,
    method: str | None = None,
):
    actual, value = call(path, body, headers, method)
    if actual != code:
        raise RuntimeError(f"{path}: expected {code}, got {actual}: {value}")
    return value


def launch(command: list[str], environment: dict[str, str]):
    process = subprocess.Popen(command, env=environment)
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


def stop(process) -> None:
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


def snapshot(project_id: str) -> dict[str, object]:
    project = need(f"/v1/projects/{project_id}")
    seasons = need(f"/v1/projects/{project_id}/seasons")
    if len(seasons) != 1:
        raise RuntimeError("project must retain exactly one first season")
    episodes = need(f"/v1/seasons/{seasons[0]['id']}/episodes")
    if [row["episode_number"] for row in episodes] != list(range(1, 11)):
        raise RuntimeError("episode numbering is not stable")
    return {"project": project, "season": seasons[0], "episodes": episodes}


def create_plan(index: int) -> dict[str, object]:
    return need(
        "/v1/project-plans",
        {
            "project": {
                "title": f"规划隔离验收项目 {index}",
                "audience_mode": "older_adult",
                "planned_episode_count": 10,
                "project_bible": {"fixture": "project-plan-isolation", "index": index},
            },
            "season_title": "第一季",
        },
        201,
        {"Idempotency-Key": f"project-plan-isolation-{index}"},
    )


def sanitized_environment(extra: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    environment = dict(os.environ)
    removed: list[str] = []
    for name in sorted(environment):
        upper = name.upper()
        if any(marker in upper for marker in ("API_KEY", "TOKEN", "SECRET", "CREDENTIAL")):
            removed.append(name)
            environment.pop(name, None)
    environment.update(extra)
    environment.update(
        {
            "NALU_ALLOW_PAID_SUBMISSION": "false",
            "NALU_ALLOW_PUBLICATION": "false",
        }
    )
    return environment, removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if not SHA_PATTERN.fullmatch(args.source_commit):
        raise RuntimeError("source commit must be a full lowercase git SHA")

    if args.app:
        resources = args.app / "Contents/Resources"
        runtime = resources / "runtime/nalu-runtime"
        analyzer = resources / "analyzers/nalu-visual-analyzer"
        recognizer = resources / "recognizers/nalu-semantic-recognizer"
        if not runtime.is_file() or not os.access(runtime, os.X_OK):
            raise RuntimeError("invalid packaged app")
        command = [str(runtime)]
        extra = {
            "NALU_REPOSITORY_ROOT": str(resources / "runtime-resources"),
            "NALU_VISUAL_ANALYZER_BINARY": str(analyzer),
            "NALU_SEMANTIC_RECOGNIZER_BINARY": str(recognizer),
        }
        runtime_mode = "packaged"
    else:
        command = [sys.executable, "-m", "nalu_runtime"]
        extra = {}
        runtime_mode = "source"

    environment, removed_names = sanitized_environment(extra)
    with tempfile.TemporaryDirectory(prefix="nalu-project-plan-isolation-") as temporary:
        root = Path(temporary)
        current_env = environment | {
            "NALU_DATABASE_PATH": str(root / "current.sqlite3"),
            "NALU_DATA_ROOT": str(root / "current-data"),
        }
        process = launch(command, current_env)
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                plans = list(pool.map(create_plan, range(1, 4)))
            project_ids = [str(plan["project"]["id"]) for plan in plans]
            snapshots = {project_id: snapshot(project_id) for project_id in project_ids}
            all_ids = [
                {snapshot_value["project"]["id"], snapshot_value["season"]["id"]}
                | {episode["id"] for episode in snapshot_value["episodes"]}
                for snapshot_value in snapshots.values()
            ]
            if any(all_ids[left] & all_ids[right] for left in range(3) for right in range(left)):
                raise RuntimeError("project, season or episode identifiers crossed projects")

            untouched_before = {key: digest(snapshots[key]) for key in project_ids[1:]}
            first_episode = snapshots[project_ids[0]]["episodes"][0]
            second_episode = snapshots[project_ids[0]]["episodes"][1]
            need(
                f"/v1/episodes/{second_episode['id']}",
                {"title": "仅修改第一个项目", "source_transcript": "隔离验收修改"},
                method="PATCH",
            )
            untouched_after = {key: digest(snapshot(key)) for key in project_ids[1:]}
            if untouched_before != untouched_after:
                raise RuntimeError("editing one project mutated another project")

            script = need(
                f"/v1/episodes/{first_episode['id']}/scripts",
                {"content": "锁定后不可修改", "summary_for_voice_review": "锁定摘要"},
                201,
            )
            need(
                f"/v1/episodes/{first_episode['id']}/scripts/{script['revision']}/approve",
                {"approved_by": "planning-isolation-qa", "spoken_confirmation": "确认锁定"},
            )
            locked_before = need(f"/v1/episodes/{first_episode['id']}")
            rejected_code, _ = call(
                f"/v1/episodes/{first_episode['id']}",
                {"title": "不允许覆盖"},
                method="PATCH",
            )
            if rejected_code != 409 or need(f"/v1/episodes/{first_episode['id']}") != locked_before:
                raise RuntimeError("approved episode plan was not immutable")

            final_snapshots = {project_id: snapshot(project_id) for project_id in project_ids}
            backups = [need(f"/v1/projects/{project_id}/export") for project_id in project_ids]
            health = need("/health")
        finally:
            stop(process)

        restore_env = environment | {
            "NALU_DATABASE_PATH": str(root / "restored.sqlite3"),
            "NALU_DATA_ROOT": str(root / "restored-data"),
        }
        process = launch(command, restore_env)
        try:
            for backup in backups:
                need("/v1/project-imports", backup, 201)
            restored_snapshots = {project_id: snapshot(project_id) for project_id in project_ids}
            if digest(restored_snapshots) != digest(final_snapshots):
                raise RuntimeError("multi-project export and restore changed planning state")

            tampered = deepcopy(backups[0])
            tampered["payload"]["seasons"][0]["project_id"] = project_ids[1]
            tampered["payload_sha256"] = export_digest(tampered["payload"])
            tampered_code, _ = call("/v1/project-imports", tampered)
            if tampered_code != 409:
                raise RuntimeError("cross-project structural restore was not rejected")
        finally:
            stop(process)

    body = {
        "schema_version": "nalu.project-plan-isolation-qa/v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "runtime_mode": runtime_mode,
        "runtime_schema_version": health["schema_version"],
        "project_count": 3,
        "episodes_per_project": 10,
        "concurrent_atomic_planning": True,
        "identifier_sets_disjoint": True,
        "cross_project_edit_isolated": True,
        "approved_episode_immutable": True,
        "export_restore_preserved": True,
        "structural_cross_project_restore_rejected": True,
        "project_snapshot_sha256": digest(final_snapshots),
        "backup_payload_sha256": [backup["payload_sha256"] for backup in backups],
        "sanitized_environment_names": removed_names,
        "network_scope": "loopback only",
        "paid_call_performed": False,
        "publication_performed": False,
        "external_write_performed": False,
        "human_acceptance_performed": False,
        "project_complete": False,
    }
    report = {**body, "report_sha256": digest(body)}
    validate_report(report)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
