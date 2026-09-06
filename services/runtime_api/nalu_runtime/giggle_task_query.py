"""Bounded read-only Giggle task observation, separate from billing acceptance."""

import hashlib
import json
import re
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

import certifi
import httpx


class GiggleTaskQueryError(ValueError):
    pass


@dataclass(frozen=True)
class GiggleTaskObservation:
    task_id: str
    status: str
    result_urls: tuple[str, ...]
    response_sha256: str
    billing_verified: bool = False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response field")
        result[key] = value
    return result


class GiggleTaskQuery:
    endpoint = "https://giggle.pro/api/v1/generation/task/query"

    def __init__(self, secret: Callable[[], str], *, transport: httpx.BaseTransport | None = None):
        self.secret = secret
        self.transport = transport

    def query(self, task_id: str) -> GiggleTaskObservation:
        if not isinstance(task_id, str) or re.fullmatch(r"[A-Za-z0-9_.:-]{1,240}", task_id) is None:
            raise GiggleTaskQueryError("invalid saved task identity")
        try:
            key = self.secret()
            if not isinstance(key, str) or not key.strip() or len(key) > 1024 or "\n" in key or "\r" in key:
                raise ValueError("credential unavailable")
            with (
                httpx.Client(transport=self.transport, timeout=30, follow_redirects=False,
                             trust_env=False, verify=ssl.create_default_context(cafile=certifi.where())) as client,
                client.stream("GET", self.endpoint, params={"task_id": task_id},
                              headers={"x-auth": key}) as response,
            ):
                if response.status_code != 200:
                    raise ValueError("query response unavailable")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000:
                        raise ValueError("query response exceeds limit")
            result = json.loads(raw, object_pairs_hook=_unique_object)
            if type(result.get("code")) is not int or result["code"] != 200:
                raise ValueError("query not successful")
            data = result["data"]
            if data.get("task_id", task_id) != task_id:
                raise ValueError("query returned another task")
            status = data["status"]
            if status not in {"pending", "processing", "completed", "failed", "error"}:
                raise ValueError("unknown task status")
            urls = data.get("urls", [])
            if not isinstance(urls, list) or len(urls) > 4:
                raise ValueError("invalid task result list")
            for url in urls:
                if not isinstance(url, str) or len(url) > 16000 or key in unquote(url):
                    raise ValueError("invalid result URL")
                parsed = urlsplit(url)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError("unsafe result URL")
            if status == "completed" and not urls:
                raise ValueError("completed task has no output")
            # URLs are candidates, not downloaded or accepted masters. A separate
            # bounded downloader must validate each redirect/host and media bytes.
            return GiggleTaskObservation(task_id, status, tuple(urls) if status == "completed" else (),
                                         hashlib.sha256(raw).hexdigest())
        except Exception:  # noqa: BLE001 -- keep provider/key callback details out of surfaced errors
            raise GiggleTaskQueryError("Giggle task query could not be verified; do not resubmit") from None
