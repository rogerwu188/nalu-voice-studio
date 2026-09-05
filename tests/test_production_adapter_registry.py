import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from nalu_runtime.production_adapters import ProductionAdapterRegistry
from nalu_runtime.repository import ConflictError


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reseal(manifest: dict) -> dict:
    manifest = deepcopy(manifest)
    manifest.pop("registry_sha256", None)
    manifest["registry_sha256"] = canonical_sha256(manifest)
    return manifest


def write_manifest(tmp_path: Path, manifest: dict) -> Path:
    path = tmp_path / "production-adapters.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return path


def source_manifest() -> dict:
    return json.loads(
        Path("configs/production-adapters.json").read_text(encoding="utf-8")
    )


def test_registry_routes_only_capability_approved_formats() -> None:
    registry = ProductionAdapterRegistry(source_manifest())
    assert registry.registry_version == "2026.09.05.1"
    assert registry.resolve("short_drama_series", "auto") == "qingshan-short-drama"
    assert registry.resolve("animation_series", "auto") == "qingshan-short-drama"
    assert registry.resolve("commercial_campaign", "auto") == "unassigned"
    assert registry.resolve("documentary_series", "auto") == "unassigned"
    assert registry.resolve("short_drama_series", "unassigned") == "unassigned"
    with pytest.raises(ConflictError, match="not registered"):
        registry.resolve("short_drama_series", "unknown-pipeline")
    with pytest.raises(ConflictError, match="does not support"):
        registry.resolve("documentary_series", "qingshan-short-drama")
    registry.validate_runtime_binding(
        "qingshan-short-drama",
        runtime_driver="qingshan",
        adapter_version="1.7.0",
        requested_models=("MiniMax-H3", "seedance-2.0-pro"),
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"runtime_driver": "other"}, "runtime driver binding drift"),
        ({"adapter_version": "1.8.0"}, "version binding drift"),
        ({"requested_models": ("seedance-2.0-pro",)}, "model binding drift"),
    ],
)
def test_registry_rejects_runtime_binding_drift(
    overrides: dict, message: str
) -> None:
    registry = ProductionAdapterRegistry(source_manifest())
    binding = {
        "runtime_driver": "qingshan",
        "adapter_version": "1.7.0",
        "requested_models": ("MiniMax-H3", "seedance-2.0-pro"),
    }
    binding.update(overrides)
    with pytest.raises(RuntimeError, match=message):
        registry.validate_runtime_binding("qingshan-short-drama", **binding)


def test_registry_rejects_tamper_and_resealed_capability_drift(tmp_path: Path) -> None:
    tampered = source_manifest()
    tampered["adapters"][0]["capabilities"].remove("character_continuity")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        ProductionAdapterRegistry.load(write_manifest(tmp_path, tampered))

    resealed = reseal(tampered)
    with pytest.raises(RuntimeError, match="capability drift"):
        ProductionAdapterRegistry.load(write_manifest(tmp_path, resealed))

    quarantined = source_manifest()
    quarantined["adapters"][0]["status"] = "QUARANTINED"
    with pytest.raises(RuntimeError, match="default adapter is unavailable"):
        ProductionAdapterRegistry.load(write_manifest(tmp_path, reseal(quarantined)))


def test_registry_rejects_unknown_or_incomplete_format_topology(tmp_path: Path) -> None:
    missing = source_manifest()
    missing["format_routes"].pop("commercial_campaign")
    with pytest.raises(RuntimeError, match="format coverage is incomplete"):
        ProductionAdapterRegistry.load(write_manifest(tmp_path, reseal(missing)))

    unknown = source_manifest()
    unknown["format_routes"]["unsupported_format"] = unknown["format_routes"].pop(
        "commercial_campaign"
    )
    with pytest.raises(RuntimeError, match="format coverage is incomplete"):
        ProductionAdapterRegistry.load(write_manifest(tmp_path, reseal(unknown)))
