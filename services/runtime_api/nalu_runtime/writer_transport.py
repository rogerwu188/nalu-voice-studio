"""Bounded Hops chat-completion transport for runtime-owned writer attempts."""

import json
import ssl
from collections.abc import Callable

import certifi
import httpx

from .interactive_story import StoryAnswer


class WriterTransportError(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WriterTransportError("writer_duplicate_json_key")
        result[key] = value
    return result


def validate_writer_response(raw: bytes) -> None:
    try:
        root = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(root, dict):
            raise WriterTransportError("writer_invalid_response")
        if not all(isinstance(root.get(key), str) and 3 <= len(root[key]) <= limit
                   for key, limit in (("id", 240), ("model", 160))):
            raise WriterTransportError("writer_missing_identity")
        choices = root.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise WriterTransportError("writer_invalid_choices")
        choice = choices[0]
        if choice.get("finish_reason") != "stop":
            raise WriterTransportError("writer_incomplete_response")
        message = choice["message"]
        if message.get("refusal") or message.get("tool_calls"):
            raise WriterTransportError("writer_non_script_response")
        body = json.loads(message["content"], object_pairs_hook=unique_object)
        if not isinstance(body, dict) or set(body) - {"reply", "summary", "episode_drafts", "outcome"}:
            raise WriterTransportError("writer_invalid_answer")
        answer = StoryAnswer(expected_revision=1, **body)
        drafts = answer.episode_drafts
        if (answer.outcome != "answered" or not answer.reply.strip() or len(drafts) > 3
                or len({draft.episode_number for draft in drafts}) != len(drafts)
                or any(not draft.script.strip() for draft in drafts)):
            raise WriterTransportError("writer_invalid_drafts")
    except (ValueError, TypeError, KeyError, AttributeError):
        # Do not propagate provider content or validation exception input values.
        raise WriterTransportError("writer_invalid_response") from None


class HopsWriterTransport:
    endpoint = "https://hopsapi.com/v1/chat/completions"

    def __init__(self, secret: Callable[[], str], *, transport: httpx.BaseTransport | None = None):
        self._secret = secret
        self._transport = transport

    def __call__(self, body: bytes) -> bytes:
        try:
            if not 0 < len(body) <= 1_100_000:
                raise WriterTransportError("writer_context_size")
            request = json.loads(body, object_pairs_hook=unique_object)
            if (not isinstance(request, dict) or request.get("store") is not False
                    or not isinstance(request.get("model"), str) or not request["model"].strip()
                    or set(request) - {"model", "store", "max_completion_tokens", "response_format", "messages"}
                    or request.get("response_format") != {"type": "json_object"}
                    or not isinstance(request.get("messages"), list)
                    or type(request.get("max_completion_tokens")) is not int
                    or not 1 <= request["max_completion_tokens"] <= 8000):
                raise WriterTransportError("writer_invalid_request")
            key = self._secret()
            if not key or "\n" in key or "\r" in key:
                raise WriterTransportError("writer_credential_unavailable")
            with httpx.Client(transport=self._transport, follow_redirects=False, trust_env=False,  # noqa: SIM117
                              timeout=90, verify=ssl.create_default_context(cafile=certifi.where())) as client:
                with client.stream("POST", self.endpoint, content=body,
                                   headers={"Authorization": f"Bearer {key}",
                                            "Content-Type": "application/json"}) as response:
                    if response.status_code != 200:
                        raise WriterTransportError(f"writer_http_{response.status_code}")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            raise WriterTransportError("writer_response_size")
                        chunks.append(chunk)
                    raw = b"".join(chunks)
            validate_writer_response(raw)
            return raw
        except WriterTransportError:
            raise
        except Exception:  # noqa: BLE001 - secret providers may raise errors containing credentials
            raise WriterTransportError("writer_transport_failed") from None
