"""Pinned QingShan image protocol; called only by a durable authorized submitter."""

import base64
import hashlib
import json
import re
import ssl
from collections.abc import Callable

import certifi
import httpx

from .repository import ConflictError
from .writer_transport import unique_object


def image_payload(request: dict) -> tuple[str, dict]:
    required = {"prompt", "generate_count", "model", "aspect_ratio", "resolution", "watermark"}
    if (set(request) - required - {"reference_images"} or not required <= set(request)
            or request["model"] != "gpt-image-2-pro" or type(request["generate_count"]) is not int
            or request["generate_count"] != 1 or request["watermark"] is not False
            or request["resolution"] != "1K"
            or request["aspect_ratio"] not in {"16:9", "9:16", "1:1", "3:4", "4:3"}
            or not isinstance(request["prompt"], str) or not request["prompt"].strip()
            or len(request["prompt"]) > 10_000):
        raise ConflictError("unsupported or unbounded image request")
    references = request.get("reference_images", [])
    if not isinstance(references, list) or len(references) > 9:
        raise ConflictError("unsupported reference image count")
    size = 0
    for ref in references:
        if not isinstance(ref, dict) or set(ref) != {"base64"} or not isinstance(ref["base64"], str):
            raise ConflictError("image references must be explicit local bytes")
        size += len(ref["base64"])
        if size > 20_000_000:
            raise ConflictError("image references exceed transport limit")
        try:
            raw = base64.b64decode(ref["base64"], validate=True)
            if not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
                raise ValueError("unsupported image")
        except ValueError:
            raise ConflictError("unsupported reference image encoding") from None
    payload = {key: request[key] for key in required}
    if references:
        payload["reference_images"] = references
    return "https://giggle.pro/api/v1/generation/" + ("image-to-image" if references else "text-to-image"), payload


class ImageAcceptanceUnconfirmed(RuntimeError):
    pass


class GiggleImageTransport:
    """Does not grant authority. The callback must validate durable intent and approval.

    Reference signature checks are transport checks, not decoding, identity,
    consent, scope or entry-state QA. Those must precede this boundary.
    """

    def __init__(self, secret: Callable[[], str], *, authorize: Callable[[str, str], None],
                 transport: httpx.BaseTransport | None = None):
        self.secret, self.authorize, self.transport = secret, authorize, transport

    def submit(self, request: dict, *, intent_id: str) -> dict:
        endpoint, payload = image_payload(request)
        if not re.fullmatch(r"[a-f0-9]{64}", intent_id):
            raise ConflictError("durable image intent identity required")
        raw_request = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        request_sha = hashlib.sha256(endpoint.encode() + b"\0" + raw_request).hexdigest()
        # There is deliberately no default authorization and no public HTTP route.
        self.authorize(intent_id, request_sha)
        try:
            key = self.secret()
            if not isinstance(key, str) or not key.strip() or len(key) > 1024 or "\r" in key or "\n" in key:
                raise ValueError("credential unavailable")
            with (httpx.Client(transport=self.transport, timeout=90, follow_redirects=False, trust_env=False,
                               verify=ssl.create_default_context(cafile=certifi.where())) as client,
                  client.stream("POST", endpoint, content=raw_request, headers={
                      "Content-Type": "application/json", "x-auth": key, "Idempotency-Key": intent_id}) as response):
                if response.status_code != 200:
                    raise ValueError("acceptance unconfirmed")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000:
                        raise ValueError("response limit")
            result = json.loads(raw, object_pairs_hook=unique_object)
            task_id = result.get("data", {}).get("task_id")
            if (type(result.get("code")) is not int or result["code"] != 200
                    or not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,240}", task_id)
                    or key.encode() in raw):
                raise ValueError("invalid acceptance")
            return {"provider_task_id": task_id, "endpoint": endpoint, "request_sha256": request_sha,
                    "response_sha256": hashlib.sha256(raw).hexdigest(), "http_status": 200,
                    "image_generated": False, "billing_verified": False}
        except Exception:  # noqa: BLE001 -- never leak credentials/provider response
            raise ImageAcceptanceUnconfirmed("image acceptance unconfirmed; do not automatically resubmit") from None
