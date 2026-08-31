#!/usr/bin/env python3
"""Verify visual-analyzer input contracts through a bundled macOS Runtime.

The harness uses only isolated local files and loopback HTTP. It proves that a
downloaded release bundle binds confirmed character/prop authority and local
reference digests, and that an unresolved held prop fails closed. It does not
run or claim a perceptual visual analyzer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def request(
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    expected: int = 200,
    timeout: float = 120,
) -> Any:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    http_request = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    return execute_request(http_request, expected=expected, timeout=timeout)


def upload(path: str, query: dict[str, Any], content: bytes, *, content_type: str) -> Any:
    http_request = urllib.request.Request(
        BASE_URL + path + "?" + urllib.parse.urlencode(query),
        data=content,
        headers={"Content-Type": content_type},
        method="POST",
    )
    return execute_request(http_request, expected=201, timeout=120)


def execute_request(http_request: urllib.request.Request, *, expected: int, timeout: float) -> Any:
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read()
    if status != expected:
        raise RuntimeError(
            f"{http_request.full_url} returned HTTP {status}, expected {expected}: "
            f"{raw.decode(errors='replace')}"
        )
    return json.loads(raw) if raw else None


def port_is_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", PORT)) == 0


def wait_for_health(process: subprocess.Popen[bytes]) -> float:
    started_at = time.monotonic()
    for _ in range(1200):
        if process.poll() is not None:
            raise RuntimeError(f"bundled Runtime exited before health check: {process.returncode}")
        try:
            health = request("/health", timeout=0.5)
            if health.get("status") == "ok":
                return time.monotonic() - started_at
        except (OSError, RuntimeError):
            pass
        time.sleep(0.1)
    raise RuntimeError("bundled Runtime did not become healthy")


def create_entity(project_id: str, kind: str, name: str, attributes: dict[str, Any]) -> dict:
    entity = request(
        f"/v1/projects/{project_id}/library-entities",
        {
            "kind": kind,
            "name": name,
            "description": f"发布包本地视觉输入：{name}",
            "attributes": attributes,
            "source_channel": "voice",
            "change_summary": "发布包视觉分析输入验收",
        },
        expected=201,
    )
    request(
        f"/v1/library-entities/{entity['id']}/confirmations",
        {
            "confirmed_by": "本机 QA",
            "reviewed_revision": 1,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": f"我确认{name}",
        },
        expected=201,
    )
    return entity


def create_approved_episode(title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = request(
        "/v1/project-plans",
        {
            "project": {
                "title": title,
                "audience_mode": "older_adult",
                "planned_episode_count": 1,
            },
            "episode_titles": ["回家"],
        },
        expected=201,
    )
    project = plan["project"]
    episode = plan["episodes"][0]
    script = request(
        f"/v1/episodes/{episode['id']}/scripts",
        {
            "content": "林叔穿着蓝色外套，手提旧皮箱回家。",
            "summary_for_voice_review": "林叔带着旧皮箱回家。",
        },
        expected=201,
    )
    request(
        f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
        {"approved_by": "本机 QA", "spoken_confirmation": "我确认这个剧本"},
    )
    return project, episode


def load_visual_inputs(
    run: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workspace = Path(run["package_path"]).parent / "qingshan-workspace"
    task = json.loads(
        (workspace / "workflow/tasks/E01_PRODUCTION_TASK.json").read_text(encoding="utf-8")
    )
    local_visual = task["local_visual_analysis"]
    inputs_path = workspace / local_visual["inputs_path"]
    visual_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    contract_path = (
        workspace / task["required_outputs"]["visual_continuity_manifest"]["contract_path"]
    )
    visual_contract = json.loads(contract_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in visual_inputs.items() if key != "inputs_sha256"}
    if canonical_sha256(body) != visual_inputs["inputs_sha256"]:
        raise RuntimeError("visual analyzer input canonical digest is invalid")
    if local_visual["inputs_sha256"] != visual_inputs["inputs_sha256"]:
        raise RuntimeError("production task does not bind the analyzer input digest")
    if visual_contract["analyzer_inputs_sha256"] != visual_inputs["inputs_sha256"]:
        raise RuntimeError("visual continuity contract does not bind the analyzer input digest")
    manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
    manifest_entry = next(
        item for item in manifest["files"] if item["path"] == local_visual["inputs_path"]
    )
    if manifest_entry["sha256"] != sha256_file(inputs_path):
        raise RuntimeError("workspace manifest does not bind the analyzer input file")
    return local_visual, visual_inputs, visual_contract


def assert_reference(reference: dict[str, Any], expected_content: bytes) -> None:
    if reference["sha256"] != hashlib.sha256(expected_content).hexdigest():
        raise RuntimeError("reference metadata digest does not match imported bytes")
    local_uri = str(reference["local_file_uri"])
    if not local_uri.startswith("file://"):
        raise RuntimeError("reference is not bound to a managed local file URI")
    local_path = Path(urllib.parse.unquote(urllib.parse.urlparse(local_uri).path))
    if not local_path.is_file() or sha256_file(local_path) != reference["sha256"]:
        raise RuntimeError("managed reference file is missing or its bytes drifted")
    if "consent_statement" in reference:
        raise RuntimeError("sensitive consent statement leaked into analyzer inputs")


def run_positive_case() -> dict[str, Any]:
    project, episode = create_approved_episode("发布包视觉输入 READY")
    character = create_entity(
        project["id"],
        "character",
        "林叔",
        {
            "aliases": ["照片里的人"],
            "wardrobe": ["蓝色外套"],
            "space_axis": "screen-left",
            "pose": "standing",
            "held_props": ["旧皮箱"],
        },
    )
    prop = create_entity(project["id"], "prop", "旧皮箱", {"aliases": ["老皮箱"]})
    portrait_bytes = b"packaged-character-reference-fixture"
    prop_bytes = b"packaged-prop-reference-fixture"
    upload(
        f"/v1/projects/{project['id']}/asset-imports",
        {
            "filename": "lin-shu.jpg",
            "kind": "character_image",
            "name": "林叔参考照",
            "subject_name": "照片里的人",
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "仅允许本项目本地视觉分析",
        },
        portrait_bytes,
        content_type="image/jpeg",
    )
    upload(
        f"/v1/projects/{project['id']}/asset-imports",
        {
            "filename": "old-case.jpg",
            "kind": "prop_reference",
            "name": "旧皮箱参考照",
            "subject_name": "老皮箱",
        },
        prop_bytes,
        content_type="image/jpeg",
    )
    run = request(f"/v1/episodes/{episode['id']}/production-runs", {"dry_run": True}, expected=201)
    local_visual, visual_inputs, visual_contract = load_visual_inputs(run)
    if local_visual["readiness"] != "READY" or visual_inputs["unresolved"]:
        raise RuntimeError(
            f"complete visual inputs did not become READY: {visual_inputs['unresolved']}"
        )
    if visual_inputs["provider_upload_allowed"] or not visual_inputs["local_execution_only"]:
        raise RuntimeError("visual input privacy boundary was not local-only")
    subject = visual_inputs["subjects"][0]
    if subject["entity_id"] != character["id"] or subject["expected"] != {
        "identity": "林叔",
        "wardrobe": ["蓝色外套"],
        "space_axis": "screen-left",
        "pose": "standing",
        "props": ["旧皮箱"],
    }:
        raise RuntimeError("confirmed character expectations were not bound exactly")
    prop_input = visual_inputs["prop_references"][0]
    if prop_input["entity_id"] != prop["id"]:
        raise RuntimeError("confirmed prop authority was not bound")
    assert_reference(subject["references"][0], portrait_bytes)
    assert_reference(prop_input["references"][0], prop_bytes)
    if not visual_contract["authored_observations_are_not_perceptual_evidence"]:
        raise RuntimeError("contract still permits authored observations as visual evidence")
    return {
        "project_id": project["id"],
        "episode_id": episode["id"],
        "run_id": run["id"],
        "readiness": visual_inputs["readiness"],
        "inputs_sha256": visual_inputs["inputs_sha256"],
        "character_entity_id": character["id"],
        "prop_entity_id": prop["id"],
        "reference_count": len(subject["references"]) + len(prop_input["references"]),
        "provider_upload_allowed": visual_inputs["provider_upload_allowed"],
    }


def run_negative_case() -> dict[str, Any]:
    project, episode = create_approved_episode("发布包视觉输入 BLOCKED")
    character = create_entity(
        project["id"],
        "character",
        "林叔",
        {
            "wardrobe": ["蓝色外套"],
            "space_axis": "screen-left",
            "pose": "standing",
            "held_props": ["旧皮箱"],
        },
    )
    portrait_bytes = b"packaged-negative-character-reference-fixture"
    upload(
        f"/v1/projects/{project['id']}/asset-imports",
        {
            "filename": "lin-shu-negative.jpg",
            "kind": "character_image",
            "name": "林叔参考照",
            "subject_name": "林叔",
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "仅允许本项目本地视觉分析",
        },
        portrait_bytes,
        content_type="image/jpeg",
    )
    run = request(f"/v1/episodes/{episode['id']}/production-runs", {"dry_run": True}, expected=201)
    local_visual, visual_inputs, _ = load_visual_inputs(run)
    expected = [
        {
            "code": "HELD_PROP_AUTHORITY_MISSING",
            "entity_id": character["id"],
            "held_prop": "旧皮箱",
        }
    ]
    if local_visual["readiness"] != "BLOCKED" or visual_inputs["unresolved"] != expected:
        raise RuntimeError(
            f"unconfirmed held prop did not fail closed: {visual_inputs['unresolved']}"
        )
    return {
        "project_id": project["id"],
        "episode_id": episode["id"],
        "run_id": run["id"],
        "readiness": visual_inputs["readiness"],
        "inputs_sha256": visual_inputs["inputs_sha256"],
        "unresolved": visual_inputs["unresolved"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--ci-run", required=True)
    parser.add_argument("--ci-artifact-id", required=True)
    parser.add_argument("--ci-artifact-digest", required=True)
    parser.add_argument("--release-zip-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = args.app.resolve()
    work_dir = args.work_dir.resolve()
    evidence = args.evidence.resolve()
    runtime = app / "Contents/Resources/runtime/nalu-runtime"
    runtime_resources = app / "Contents/Resources/runtime-resources"
    executable = app / "Contents/MacOS/NaluVoiceStudio"
    if port_is_open():
        raise RuntimeError(f"loopback port {PORT} is already occupied")
    for required in (runtime, executable, runtime_resources / "configs/qingshan-upstream.json"):
        if not required.exists():
            raise RuntimeError(f"release bundle is missing {required}")
    work_dir.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "NALU_DATA_ROOT": str(work_dir / "runtime-data"),
            "NALU_DATABASE_PATH": str(work_dir / "runtime.sqlite3"),
            "NALU_REPOSITORY_ROOT": str(runtime_resources),
        }
    )
    log_path = work_dir / "runtime.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(runtime)], stdout=log, stderr=subprocess.STDOUT, env=environment
        )
        try:
            startup_seconds = wait_for_health(process)
            positive = run_positive_case()
            negative = run_negative_case()
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    for _ in range(50):
        if not port_is_open():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("bundled Runtime left loopback port open after termination")
    report = {
        "schema_version": "nalu.packaged-visual-inputs-qa/v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "ci_run": args.ci_run,
        "ci_artifact": {
            "id": args.ci_artifact_id,
            "digest": args.ci_artifact_digest,
            "release_zip_sha256": args.release_zip_sha256,
        },
        "bundle": {
            "path": str(app),
            "main_executable_sha256": sha256_file(executable),
            "bundled_runtime_sha256": sha256_file(runtime),
            "signature_scope": "ad-hoc; Developer ID and notarization are not claimed",
        },
        "positive_case": positive,
        "negative_case": negative,
        "claim_scope": (
            "visual analyzer input authority and fail-closed readiness only; no perceptual "
            "recognition or human visual acceptance is claimed"
        ),
        "network_scope": "loopback HTTP only; no provider, paid model, or publication call",
        "runtime_stopped_and_port_closed": True,
        "runtime_startup_seconds": round(startup_seconds, 3),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report["report_sha256"] = canonical_sha256(report)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Packaged visual input QA failed: {error}", file=sys.stderr)
        raise
