#!/usr/bin/env python3
"""Explicit, single-attempt Hops writer QA; never runs in ordinary CI."""

import argparse
import hashlib
import json
import plistlib
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx
from nalu_runtime.interactive_story import StoryAnswer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-authorized-text-request", action="store_true")
    parser.add_argument("--evidence-directory", type=Path, required=True)
    args = parser.parse_args()
    if not args.execute_authorized_text_request:
        parser.error("explicit authorization flag required; this may consume text API credits")
    args.evidence_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    database = sqlite3.connect(args.evidence_directory / "writer-attempt.sqlite3")
    database.execute("CREATE TABLE IF NOT EXISTS attempt (id TEXT PRIMARY KEY, state TEXT, evidence TEXT)")
    attempt = "nalu-hops-narration-qa-v1"
    if database.execute("SELECT 1 FROM attempt WHERE id=?", (attempt,)).fetchone():
        print("Existing attempt retained; no automatic repeat request.")
        return 2
    settings = plistlib.loads(subprocess.run(
        ["defaults", "export", "studio.nalu.voice", "-"], capture_output=True, check=True).stdout)
    endpoint = str(settings.get("nalu.ai-service-base-url", "")).rstrip("/")
    if endpoint != "https://hopsapi.com/v1":
        print("Configured endpoint differs from authorized Hops destination; no request sent.")
        return 2
    model_data = settings.get("nalu.ai-models.v1." + endpoint)
    model = json.loads(model_data)["research"] if model_data else "gpt-5.4-mini"
    # The secret is captured in memory only; never print it or error bodies.
    try:
        key_result = subprocess.run(["security", "find-generic-password",
            "-s", "studio.nalu.voice.provider-credentials", "-a", "openai-realtime-api-key", "-w"],
            capture_output=True, timeout=20, check=False)
    except subprocess.TimeoutExpired:
        print("Keychain access pending; no provider request sent.")
        return 2
    if key_result.returncode != 0 or not key_result.stdout.strip():
        print("Keychain credential unavailable to QA process; no provider request sent.")
        return 2
    key = key_result.stdout.decode().strip()
    root = Path(__file__).resolve().parents[1]
    swift = (root / "apps/macos/Sources/NaluVoiceStudio/InteractiveStoryWriter.swift").read_text()
    instructions = swift.split('static let instructions = """', 1)[1].split('"""', 1)[0].strip()
    text = "这是虚构的测试故事，不是真实家庭资料：六岁的我跟外婆到海边认星星，后来我记住了北斗星。请写第一集的一个短场景，有动作和对白。"
    state = {"revision": 1, "turns": [{"turn_id": attempt, "text": text,
        "source_mode": "narrated_story", "status": "pending"}], "summary": "", "episode_drafts": []}
    body = {"model": model, "store": False, "max_completion_tokens": 8000,
        "response_format": {"type": "json_object"}, "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False)}]}
    encoded = json.dumps(body, ensure_ascii=False).encode()
    evidence = {"endpoint": endpoint, "requested_model": model, "synthetic_input": text,
        "started_at": datetime.now(UTC).isoformat(),
        "request_sha256": hashlib.sha256(encoded).hexdigest(),
        "writer_rules_sha256": hashlib.sha256(instructions.encode()).hexdigest()}
    database.execute("INSERT INTO attempt VALUES (?, 'submitted', ?)", (attempt, json.dumps(evidence)))
    database.commit()  # durable before any possibly charged request
    try:
        with httpx.Client(timeout=90, follow_redirects=False) as client:
            response = client.post(endpoint + "/chat/completions", content=encoded,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                         "Idempotency-Key": attempt})
        evidence["http_status"] = response.status_code
        evidence["completed_at"] = datetime.now(UTC).isoformat()
        response.raise_for_status()
        raw = response.text
        if key in raw:
            raise ValueError("credential echo must not be persisted")
        result = response.json()
        choice = result["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("incomplete writer result")
        answer = StoryAnswer.model_validate({"expected_revision": 1, **json.loads(choice["message"]["content"])})
        if not answer.episode_drafts or not all(d.script.strip() for d in answer.episode_drafts):
            raise ValueError("no concrete episode script")
        evidence.update(returned_model=result["model"], returned_task_id=result["id"],
                        response_json=raw, response_sha256=hashlib.sha256(response.content).hexdigest(),
                        episode_count=len(answer.episode_drafts))
        database.execute("UPDATE attempt SET state='completed', evidence=? WHERE id=?", (json.dumps(evidence), attempt))
        database.commit()
        print(json.dumps({"status": "completed", "model": result["model"],
                          "episode_count": len(answer.episode_drafts)}, ensure_ascii=False))
        return 0
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        evidence["failure_class"] = type(exc).__name__
        database.execute("UPDATE attempt SET state='needs_review', evidence=? WHERE id=?", (json.dumps(evidence), attempt))
        database.commit()
        print(json.dumps({"status": "needs_review", "http_status": evidence.get("http_status"),
                          "failure_class": type(exc).__name__, "automatically_retried": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
