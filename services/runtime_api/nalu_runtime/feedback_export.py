from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit


class FeedbackExportPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class FeedbackExportPolicy:
    schema_version: str = "nalu.feedback-export-policy/v1"
    enabled: bool = False
    administrator_authorized: bool = False
    provider: str = "github_issues"
    endpoint: str = ""
    repository: str = ""
    max_payload_bytes: int = 65536

    @classmethod
    def load(cls, path: Path) -> FeedbackExportPolicy:
        try:
            value = json.loads(path.read_text())
            policy = cls(
                schema_version=value["schema_version"],
                enabled=value["enabled"],
                administrator_authorized=value["administrator_authorized"],
                provider=value["provider"],
                endpoint=value["endpoint"],
                repository=value["repository"],
                max_payload_bytes=value["max_payload_bytes"],
            )
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise FeedbackExportPolicyError("feedback export policy is unreadable") from exc
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.schema_version != "nalu.feedback-export-policy/v1":
            raise FeedbackExportPolicyError("unsupported feedback export policy")
        if self.provider != "github_issues" or not 1024 <= self.max_payload_bytes <= 262144:
            raise FeedbackExportPolicyError("feedback export policy has invalid bounds")
        if not self.enabled:
            if self.administrator_authorized or self.endpoint or self.repository:
                raise FeedbackExportPolicyError("disabled export policy must not retain a target")
            return
        if not self.administrator_authorized:
            raise FeedbackExportPolicyError("enabled export requires administrator authorization")
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/api/issues"
        ):
            raise FeedbackExportPolicyError("issue endpoint must be exact credential-free HTTPS")
        owner = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
        name = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?"
        if not re.fullmatch(f"{owner}/{name}", self.repository):
            raise FeedbackExportPolicyError("issue repository must be owner/name")


@dataclass(frozen=True)
class IssueTrackerReceipt:
    remote_issue_id: str
    remote_issue_url: str
    response: dict[str, Any]


class IssueTrackerTransport(Protocol):
    def create_issue(
        self,
        *,
        endpoint: str,
        repository: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> IssueTrackerReceipt: ...


class DisabledIssueTrackerTransport:
    def create_issue(
        self,
        *,
        endpoint: str,
        repository: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> IssueTrackerReceipt:
        raise FeedbackExportPolicyError("no authorized issue tracker transport is configured")
