from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .repository import ConflictError

REGISTRY_SCHEMA = "nalu.production-adapter-registry/v1"
CREATIVE_FORMATS = {
    "short_drama_series",
    "animation_series",
    "commercial_campaign",
    "documentary_series",
}


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ProductionAdapterRegistry:
    """Versioned authority for creative-format production-line routing."""

    def __init__(self, manifest: dict[str, Any]):
        self._manifest = manifest
        self._validate_manifest()
        self._adapters = {
            str(adapter["adapter_id"]): adapter for adapter in manifest["adapters"]
        }
        self._routes = manifest["format_routes"]

    @classmethod
    def load(cls, path: Path) -> ProductionAdapterRegistry:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("production adapter registry is missing or unsafe")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("production adapter registry is unreadable") from exc
        if not isinstance(manifest, dict):
            raise TypeError("production adapter registry must be an object")
        return cls(manifest)

    @property
    def registry_version(self) -> str:
        return str(self._manifest["registry_version"])

    def resolve(self, creative_format: str, requested_pipeline: str) -> str:
        route = self._route(creative_format)
        if requested_pipeline == "auto":
            requested_pipeline = route["default_adapter_id"] or "unassigned"
        if requested_pipeline == "unassigned":
            return requested_pipeline
        self._require_compatible(route, creative_format, requested_pipeline)
        return requested_pipeline

    def require_execution_route(
        self, creative_format: str, production_pipeline: str
    ) -> dict[str, Any]:
        route = self._route(creative_format)
        if production_pipeline in {"auto", "unassigned"}:
            raise ConflictError(
                "this project has no approved production adapter; choose a supported pipeline"
            )
        return self._require_compatible(route, creative_format, production_pipeline)

    def validate_runtime_binding(
        self,
        adapter_id: str,
        *,
        runtime_driver: str,
        adapter_version: str,
        requested_models: tuple[str, ...],
    ) -> None:
        """Fail startup when registry claims drift from the bundled implementation."""
        adapter = self._adapters.get(adapter_id)
        if adapter is None or adapter["status"] != "ACTIVE":
            raise RuntimeError("production adapter runtime binding is unavailable")
        if adapter["runtime_driver"] != runtime_driver:
            raise RuntimeError("production adapter runtime driver binding drift")
        if adapter["adapter_version"] != adapter_version:
            raise RuntimeError("production adapter version binding drift")
        if set(adapter["requested_models"]) != set(requested_models):
            raise RuntimeError("production adapter model binding drift")

    def _route(self, creative_format: str) -> dict[str, Any]:
        route = self._routes.get(creative_format)
        if not isinstance(route, dict):
            raise ConflictError("creative format has no registered production route")
        return route

    def _require_compatible(
        self,
        route: dict[str, Any],
        creative_format: str,
        adapter_id: str,
    ) -> dict[str, Any]:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise ConflictError("production adapter is not registered")
        if adapter["status"] != "ACTIVE":
            raise ConflictError("production adapter is not active")
        if creative_format not in adapter["creative_formats"]:
            raise ConflictError("production adapter does not support this creative format")
        missing = sorted(
            set(route["required_capabilities"]) - set(adapter["capabilities"])
        )
        if missing:
            raise ConflictError(
                "production adapter is missing required capabilities: " + ", ".join(missing)
            )
        return adapter

    def _validate_manifest(self) -> None:
        expected_keys = {
            "schema_version",
            "registry_version",
            "adapters",
            "format_routes",
            "registry_sha256",
        }
        if set(self._manifest) != expected_keys:
            raise RuntimeError("production adapter registry fields are invalid")
        if self._manifest.get("schema_version") != REGISTRY_SCHEMA:
            raise RuntimeError("production adapter registry schema is unsupported")
        if not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}\.[0-9]+", str(self._manifest.get("registry_version", ""))):
            raise RuntimeError("production adapter registry version is invalid")
        body = {
            key: value for key, value in self._manifest.items() if key != "registry_sha256"
        }
        digest = self._manifest.get("registry_sha256")
        if digest != _canonical_sha256(body):
            raise RuntimeError("production adapter registry digest mismatch")

        adapters = self._manifest.get("adapters")
        routes = self._manifest.get("format_routes")
        if not isinstance(adapters, list) or not adapters or not isinstance(routes, dict):
            raise RuntimeError("production adapter registry content is invalid")
        if set(routes) != CREATIVE_FORMATS:
            raise RuntimeError("production adapter registry format coverage is incomplete")
        adapter_ids: list[str] = []
        adapter_by_id: dict[str, dict[str, Any]] = {}
        adapter_fields = {
            "adapter_id",
            "adapter_version",
            "status",
            "runtime_driver",
            "creative_formats",
            "capabilities",
            "requested_models",
        }
        for adapter in adapters:
            if not isinstance(adapter, dict) or set(adapter) != adapter_fields:
                raise RuntimeError("production adapter entry is invalid")
            adapter_id = adapter.get("adapter_id")
            if not isinstance(adapter_id, str) or not adapter_id.strip():
                raise RuntimeError("production adapter identity is invalid")
            adapter_ids.append(adapter_id)
            adapter_by_id[adapter_id] = adapter
            if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(adapter.get("adapter_version", ""))):
                raise RuntimeError("production adapter version is invalid")
            if adapter.get("status") not in {"ACTIVE", "QUARANTINED"}:
                raise RuntimeError("production adapter status is invalid")
            if not isinstance(adapter.get("runtime_driver"), str) or not adapter["runtime_driver"]:
                raise RuntimeError("production adapter runtime driver is invalid")
            self._validate_unique_strings(adapter.get("creative_formats"), "creative formats")
            self._validate_unique_strings(adapter.get("capabilities"), "capabilities")
            self._validate_unique_strings(adapter.get("requested_models"), "models")
            if not set(adapter["creative_formats"]).issubset(CREATIVE_FORMATS):
                raise RuntimeError("production adapter creative format is unknown")
        if len(adapter_ids) != len(set(adapter_ids)):
            raise RuntimeError("production adapter identities must be unique")

        route_fields = {"default_adapter_id", "required_capabilities"}
        for creative_format, route in routes.items():
            if not isinstance(route, dict) or set(route) != route_fields:
                raise RuntimeError("production format route is invalid")
            self._validate_unique_strings(
                route.get("required_capabilities"), "required capabilities"
            )
            default_adapter_id = route.get("default_adapter_id")
            if default_adapter_id is not None:
                adapter = adapter_by_id.get(default_adapter_id)
                if adapter is None or adapter.get("status") != "ACTIVE":
                    raise RuntimeError("production format default adapter is unavailable")
                if creative_format not in adapter["creative_formats"]:
                    raise RuntimeError("production format default adapter is incompatible")
                if not set(route["required_capabilities"]).issubset(
                    adapter["capabilities"]
                ):
                    raise RuntimeError("production format default adapter capability drift")

    @staticmethod
    def _validate_unique_strings(value: object, label: str) -> None:
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise RuntimeError(f"production adapter registry {label} are invalid")
        if len(value) != len(set(value)):
            raise RuntimeError(f"production adapter registry {label} must be unique")
