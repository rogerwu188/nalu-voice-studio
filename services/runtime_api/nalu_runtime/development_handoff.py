from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit


class DevelopmentHandoffPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class DevelopmentHandoffPolicy:
    schema_version: str = "nalu.development-handoff-policy/v1"
    enabled: bool = False
    administrator_authorized: bool = False
    provider: str = "development_agent"
    endpoint: str = ""
    max_payload_bytes: int = 65536

    @classmethod
    def load(cls, path: Path) -> DevelopmentHandoffPolicy:
        try:
            value = json.loads(path.read_text())
            policy = cls(
                schema_version=value["schema_version"],
                enabled=value["enabled"],
                administrator_authorized=value["administrator_authorized"],
                provider=value["provider"],
                endpoint=value["endpoint"],
                max_payload_bytes=value["max_payload_bytes"],
            )
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise DevelopmentHandoffPolicyError(
                "development handoff policy is unreadable"
            ) from exc
        policy.validate()
        return policy

    def validate(self) -> None:
        if self.schema_version != "nalu.development-handoff-policy/v1":
            raise DevelopmentHandoffPolicyError("unsupported development handoff policy")
        if self.provider != "development_agent" or not 1024 <= self.max_payload_bytes <= 262144:
            raise DevelopmentHandoffPolicyError("development handoff policy has invalid bounds")
        if not self.enabled:
            if self.administrator_authorized or self.endpoint:
                raise DevelopmentHandoffPolicyError(
                    "disabled development handoff policy must not retain a target"
                )
            return
        if not self.administrator_authorized:
            raise DevelopmentHandoffPolicyError(
                "enabled development handoff requires administrator authorization"
            )
        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/api/development-work-orders"
        ):
            raise DevelopmentHandoffPolicyError(
                "development handoff endpoint must be exact credential-free HTTPS"
            )


@dataclass(frozen=True)
class DevelopmentHandoffTransportReceipt:
    remote_task_id: str
    remote_task_url: str
    response: dict[str, Any]


class DevelopmentHandoffTransport(Protocol):
    def submit_work_order(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> DevelopmentHandoffTransportReceipt: ...


class DisabledDevelopmentHandoffTransport:
    def submit_work_order(
        self,
        *,
        endpoint: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> DevelopmentHandoffTransportReceipt:
        raise DevelopmentHandoffPolicyError(
            "no authorized development handoff transport is configured"
        )
