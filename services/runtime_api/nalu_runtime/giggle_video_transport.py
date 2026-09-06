"""Giggle SD2 image submission; invoked only by the approved durable submitter."""

import base64
import hashlib
import json
import re
import ssl
from collections.abc import Callable

import certifi
import httpx

from .remote_submitter import AmbiguousPaidProviderResponse, PaidProviderAcceptance
from .repository import ConflictError


def seedance_image_payload(request: dict) -> dict:
    """Preserve the approved prompt and prove supplied frame bytes match its anchor.

    This path deliberately rejects multi-reference payloads instead of dropping
    their media. The separately reviewed omni adapter must handle those.
    """
    video = request.get("video_transport")
    if not isinstance(video, dict) or set(video) != {"mode", "start_frame", "aspect_ratio"}:
        raise ConflictError("SD2 requires an explicit image transport contract")
    if video["mode"] != "image_to_video_start_frame":
        raise ConflictError("unsupported SD2 transport mode")
    for key in ("images", "audios", "videos", "end_frame", "reference_assets"):
        if request.get(key):
            raise ConflictError("additional references require the omni transport")
    frame = video["start_frame"]
    if not isinstance(frame, dict) or set(frame) != {"base64"}:
        raise ConflictError("SD2 image path requires digest-bound local frame bytes")
    encoded = frame["base64"]
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 14_000_000:
        raise ConflictError("SD2 start frame exceeds the local transport limit")
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise ConflictError("invalid start frame encoding") from None
    if not decoded or hashlib.sha256(decoded).hexdigest() != request.get("opening_anchor", {}).get("frame_sha256"):
        raise ConflictError("start frame differs from the approved opening anchor")
    prompt = request.get("prompt")
    duration = request.get("duration_seconds")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 10_000:
        raise ConflictError("invalid approved SD2 prompt")
    if type(duration) is not int or not 4 <= duration <= 15:
        raise ConflictError("SD2 duration must be an integer from 4 to 15")
    if request.get("model") != "seedance-2.0-pro" or request.get("provider_model_id") != "seedance-2.0-pro":
        raise ConflictError("wrong SD2 model identity")
    if request.get("native_resolution_contract") != "720p" or request.get("delivery_resolution_contract") != "720p":
        raise ConflictError("SD2 transport cannot change the approved native resolution")
    if video["aspect_ratio"] not in {"16:9", "9:16", "1:1", "3:4", "4:3"}:
        raise ConflictError("unsupported SD2 aspect ratio")
    return {"prompt": prompt, "model": "seedance-2.0-pro", "duration": duration,
            "aspect_ratio": video["aspect_ratio"], "resolution": "720p",
            "generating_count": 1, "start_frame": {"base64": encoded}}


class GiggleSeedanceImageTransport:
    provider_name = "giggle"
    supports_idempotency = False
    requires_single_attempt = True
    endpoint = "https://giggle.pro/api/v1/generation/image-to-video"

    def __init__(self, secret: Callable[[], str], *, transport: httpx.BaseTransport | None = None,
                 before_submit: Callable[[], None] | None = None):
        self.secret = secret
        self.transport = transport
        self.before_submit = before_submit

    def post_paid_task(self, *, request: dict, idempotency_key: str) -> PaidProviderAcceptance:
        payload = seedance_image_payload(request)
        if re.fullmatch(r"[a-f0-9]{64}", idempotency_key) is None:
            raise ConflictError("missing durable SD2 submission identity")
        if self.before_submit is not None:
            self.before_submit()
        try:
            key = self.secret()
            if not isinstance(key, str) or not key.strip() or len(key) > 1024 or "\n" in key or "\r" in key:
                raise ValueError("credential unavailable")
            with (
                httpx.Client(transport=self.transport, timeout=90, follow_redirects=False,
                             trust_env=False, verify=ssl.create_default_context(cafile=certifi.where())) as client,
                client.stream("POST", self.endpoint, json=payload,
                              headers={"x-auth": key, "Idempotency-Key": idempotency_key}) as response,
            ):
                if response.status_code != 200:
                    raise ValueError("provider rejected response")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000:
                        raise ValueError("response limit")
            result = json.loads(raw)
            task_id = result.get("data", {}).get("task_id")
            if result.get("code") != 200 or not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 240:
                raise ValueError("missing task identity")
            return PaidProviderAcceptance(provider_task_id=task_id,
                receipt={"response_sha256": hashlib.sha256(raw).hexdigest(),
                         "provider_task_id": task_id, "http_status": 200})
        except Exception:  # noqa: BLE001 -- secret callbacks and HTTP errors may contain credentials
            # No raw provider errors, response body or credentials enter logs/receipts.
            raise AmbiguousPaidProviderResponse("GIGGLE_ACCEPTANCE_UNCONFIRMED",
                                                {"automatic_resubmit": False}) from None
