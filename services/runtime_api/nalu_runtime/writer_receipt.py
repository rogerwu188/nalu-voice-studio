from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

WRITER_RECEIPT_SCHEMA = "qingshan.canonical_writer_run_receipt.v1"
INTERACTIVE_RECEIPT_SCHEMA = "nalu.interactive_writer_receipt.v1"
ALLOWED_WRITER_AGENT_IDS = {
    "qingshan-claude-writer-agent",
    "qingshan-claude-writer",
}
WRITER_RUN_ID = re.compile(r"^WRITER-E[0-9]+-V[0-9]+-[A-Z0-9][A-Z0-9_-]*$")


class WriterReceiptVerificationError(ValueError):
    pass


def interactive_response_scripts(raw: str, model: str, task_id: str) -> dict[int, str]:
    """Bind returned script bytes; this is not proof of provider execution."""
    try:
        response = json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)
        if response["id"] != task_id or response["model"] != model:
            raise ValueError("identity mismatch")
        choice = response["choices"][0]
        if choice["finish_reason"] != "stop":
            raise ValueError("incomplete response")
        answer = json.loads(choice["message"]["content"], object_pairs_hook=_object_without_duplicate_keys)
        drafts = answer["episode_drafts"]
        scripts = {}
        for draft in drafts:
            number, script = draft["episode_number"], draft["script"]
            if type(number) is not int or not 1 <= number <= 500 or number in scripts:
                raise ValueError("invalid episode")
            if not isinstance(script, str) or not script.strip():
                raise ValueError("missing script")
            scripts[number] = script
        return scripts
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise WriterReceiptVerificationError("interactive writer response is invalid") from exc


def interactive_receipt(raw: str, declaration: dict, episode: int, version: int, script: str):
    raw_sha = hashlib.sha256(raw.encode()).hexdigest()
    if raw_sha != declaration["receipt_sha256"]:
        raise WriterReceiptVerificationError("interactive response digest does not match")
    scripts = interactive_response_scripts(raw, declaration["model_id"], declaration["session_or_task_id"])
    if scripts.get(episode) != script:
        raise WriterReceiptVerificationError("interactive response does not contain this script")
    receipt = {
        "schema": INTERACTIVE_RECEIPT_SCHEMA, "status": "COMPLETED",
        "writer_run_id": f"WRITER-E{episode}-V{version}-{raw_sha[:24].upper()}",
        "agent_id": "nalu-interactive-writer", "episode": f"E{episode}", "version": version,
        **{key: declaration[key] for key in ("provider", "model_id", "session_or_task_id", "started_at", "completed_at")},
        "input_bundle": {"sha256": declaration["input_bundle_sha256"]},
        "writer_rules": {"combined_sha256": declaration["writer_rules_sha256"]},
        "authority_output": {"sha256": hashlib.sha256(script.encode()).hexdigest()},
        "raw_response_json": raw,
    }
    encoded = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {**declaration, "receipt_sha256": hashlib.sha256(encoded.encode()).hexdigest()}, encoded


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WriterReceiptVerificationError(f"writer receipt repeats JSON key: {key}")
        result[key] = value
    return result


def _section_sha256(receipt: dict[str, Any], section: str, field: str) -> str:
    value = receipt.get(section)
    if not isinstance(value, dict) or not isinstance(value.get(field), str):
        raise WriterReceiptVerificationError(
            f"writer receipt is missing {section}.{field}"
        )
    return value[field]


def verify_writer_receipt(
    receipt_bytes: bytes,
    *,
    declared_receipt_sha256: str,
    declared_provider: str,
    declared_model_id: str,
    declared_session_or_task_id: str,
    declared_input_bundle_sha256: str,
    declared_writer_rules_sha256: str,
    declared_started_at: str,
    declared_completed_at: str,
    script_content_sha256: str,
) -> dict[str, Any]:
    if not receipt_bytes or len(receipt_bytes) > 8 * 1024 * 1024:
        raise WriterReceiptVerificationError("writer receipt must be between 1 byte and 8 MiB")
    actual_receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    if actual_receipt_sha256 != declared_receipt_sha256:
        raise WriterReceiptVerificationError("writer receipt SHA-256 does not match provenance")
    try:
        receipt = json.loads(
            receipt_bytes.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WriterReceiptVerificationError("writer receipt is not valid UTF-8 JSON") from exc
    if not isinstance(receipt, dict):
        raise WriterReceiptVerificationError("writer receipt root must be an object")
    interactive = receipt.get("schema") == INTERACTIVE_RECEIPT_SCHEMA
    if not interactive and len(receipt_bytes) > 256 * 1024:
        raise WriterReceiptVerificationError("canonical writer receipt exceeds 256 KiB")
    if receipt.get("schema") not in {WRITER_RECEIPT_SCHEMA, INTERACTIVE_RECEIPT_SCHEMA}:
        raise WriterReceiptVerificationError("writer receipt schema is not supported")
    if receipt.get("status") != "COMPLETED":
        raise WriterReceiptVerificationError("writer receipt is not COMPLETED")
    writer_run_id = receipt.get("writer_run_id")
    agent_id = receipt.get("agent_id")
    if not isinstance(writer_run_id, str) or not WRITER_RUN_ID.fullmatch(writer_run_id):
        raise WriterReceiptVerificationError("writer receipt run ID is invalid")
    allowed_agents = {"nalu-interactive-writer"} if interactive else ALLOWED_WRITER_AGENT_IDS
    if agent_id not in allowed_agents:
        raise WriterReceiptVerificationError("writer receipt agent is not authorized")
    episode = receipt.get("episode")
    version = receipt.get("version")
    if not isinstance(episode, str) or not re.fullmatch(r"E[0-9]+", episode):
        raise WriterReceiptVerificationError("writer receipt episode is invalid")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise WriterReceiptVerificationError("writer receipt version is invalid")
    if not writer_run_id.startswith(f"WRITER-{episode}-V{version}-"):
        raise WriterReceiptVerificationError("writer run ID does not bind episode and version")

    exact_pairs = {
        "provider": declared_provider,
        "model_id": declared_model_id,
        "session_or_task_id": declared_session_or_task_id,
        "started_at": declared_started_at,
        "completed_at": declared_completed_at,
    }
    for field, expected in exact_pairs.items():
        if receipt.get(field) != expected:
            raise WriterReceiptVerificationError(
                f"writer receipt does not match declared {field}"
            )
    input_bundle_sha256 = _section_sha256(receipt, "input_bundle", "sha256")
    writer_rules_sha256 = _section_sha256(receipt, "writer_rules", "combined_sha256")
    authority_output_sha256 = _section_sha256(receipt, "authority_output", "sha256")
    if input_bundle_sha256 != declared_input_bundle_sha256:
        raise WriterReceiptVerificationError("writer receipt input bundle does not match")
    if writer_rules_sha256 != declared_writer_rules_sha256:
        raise WriterReceiptVerificationError("writer receipt rules do not match")
    if authority_output_sha256 != script_content_sha256:
        raise WriterReceiptVerificationError("writer receipt authority output does not match script")
    if interactive:
        scripts = interactive_response_scripts(receipt.get("raw_response_json"), declared_model_id,
                                               declared_session_or_task_id)
        script = scripts.get(int(episode[1:]))
        if script is None or hashlib.sha256(script.encode()).hexdigest() != script_content_sha256:
            raise WriterReceiptVerificationError("interactive receipt output does not match response")
    try:
        started = datetime.fromisoformat(declared_started_at)
        completed = datetime.fromisoformat(declared_completed_at)
    except ValueError as exc:
        raise WriterReceiptVerificationError("writer receipt timestamps are invalid") from exc
    if started.tzinfo is None or completed.tzinfo is None:
        raise WriterReceiptVerificationError("writer receipt timestamps require a UTC offset")
    if completed < started:
        raise WriterReceiptVerificationError("writer receipt completion precedes start")

    return {
        "receipt_sha256": actual_receipt_sha256,
        "writer_run_id": writer_run_id,
        "episode": episode,
        "version": version,
        "agent_id": agent_id,
        "provider": declared_provider,
        "model_id": declared_model_id,
        "session_or_task_id": declared_session_or_task_id,
        "input_bundle_sha256": input_bundle_sha256,
        "writer_rules_sha256": writer_rules_sha256,
        "authority_output_sha256": authority_output_sha256,
        "started_at": declared_started_at,
        "completed_at": declared_completed_at,
    }
