from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


class GateRegistryAuditError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_validator(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("nalu_pinned_qingshan_gate_registry", path)
    if spec is None or spec.loader is None:
        raise GateRegistryAuditError("cannot load pinned Qingshan gate registry validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "validate", None)):
        raise GateRegistryAuditError("pinned Qingshan gate registry validator has no validate()")
    return module


def _nonportable_registry_failures(registry: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for gate in registry.get("gates") or []:
        gate_id = str(gate.get("gate_id") or "UNKNOWN")
        candidates = [
            *(gate.get("code_paths") or []),
            *(gate.get("test_paths") or []),
            *(gate.get("stage_runner_paths") or []),
        ]
        if gate.get("manual_checklist_path"):
            candidates.append(gate["manual_checklist_path"])
        for value in candidates:
            path = Path(str(value))
            if path.is_absolute():
                failures.append(f"nonportable_absolute_path:{gate_id}:{path}")
    return failures


def _audit_gate_registry_uncached(
    repository_root: Path,
    vendor_root: Path,
    *,
    upstream_release: str,
    upstream_commit: str,
) -> dict[str, Any]:
    """Run Qingshan's own integrity check and strictly classify a pinned quarantine."""
    quarantine_path = repository_root / "configs" / "qingshan-gate-registry-quarantine.json"
    try:
        quarantine = json.loads(quarantine_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateRegistryAuditError("gate registry quarantine is missing or invalid") from exc

    registry_relative = Path(str(quarantine.get("gate_registry_path") or ""))
    registry_path = vendor_root / registry_relative
    validator_path = vendor_root / "tools" / "gate_registry_v3_check.py"
    if registry_relative.is_absolute():
        raise GateRegistryAuditError("gate registry quarantine path must be relative")
    if not registry_path.is_file() or not validator_path.is_file():
        raise GateRegistryAuditError("pinned gate registry or validator is absent")

    registry_sha256 = _sha256(registry_path)
    validator_sha256 = _sha256(validator_path)
    quarantine_binding_valid = all(
        (
            quarantine.get("upstream_release") == upstream_release,
            quarantine.get("upstream_commit") == upstream_commit,
            quarantine.get("gate_registry_sha256") == registry_sha256,
            quarantine.get("gate_registry_validator_sha256") == validator_sha256,
        )
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    upstream_report = _load_validator(validator_path).validate(registry, vendor_root)
    validator_failures = [
        str(value) for value in upstream_report.get("failures") or []
    ]
    # Qingshan's validator treats an absolute test path as available on the original
    # developer Mac and missing elsewhere. Normalize that host-dependent result into one
    # deterministic portability failure on every machine.
    validator_failures = [
        value
        for value in validator_failures
        if not (
            value.startswith("missing_path:")
            and Path(value.split(":", 2)[-1]).is_absolute()
        )
    ]
    actual_failures = sorted(
        {*validator_failures, *_nonportable_registry_failures(registry)}
    )
    known_failures = sorted(str(value) for value in quarantine.get("known_failures") or [])
    new_failures = sorted(set(actual_failures) - set(known_failures))
    resolved_failures = sorted(set(known_failures) - set(actual_failures))

    if not quarantine_binding_valid:
        status = "FAIL_UNREVIEWED_GATE_REGISTRY_DRIFT"
    elif upstream_report.get("status") == "PASS" and not actual_failures:
        status = "PASS_INTEGRITY"
    elif quarantine_binding_valid and actual_failures == known_failures:
        status = "QUARANTINED_KNOWN_UPSTREAM_DEFECT"
    else:
        status = "FAIL_UNREVIEWED_GATE_REGISTRY_DRIFT"

    return {
        "schema_version": "nalu.qingshan-gate-registry-audit/v1",
        "status": status,
        "upstream_release": upstream_release,
        "upstream_commit": upstream_commit,
        "registry_path": str(registry_relative),
        "registry_sha256": registry_sha256,
        "validator_sha256": validator_sha256,
        "quarantine_binding_valid": quarantine_binding_valid,
        "upstream_issue": quarantine.get("upstream_issue"),
        "gate_count": upstream_report.get("gate_count"),
        "coded_gate_count": upstream_report.get("coded_gate_count"),
        "runtime_bound_count": upstream_report.get("runtime_bound_count"),
        "actual_failures": actual_failures,
        "known_failures": known_failures,
        "new_failures": new_failures,
        "resolved_failures": resolved_failures,
        "registered_tests_eligible": status == "PASS_INTEGRITY",
        "registered_tests_executed": False,
        "paid_execution_allowed": status == "PASS_INTEGRITY",
    }


@lru_cache(maxsize=8)
def _cached_gate_registry_audit(
    repository_root: Path,
    vendor_root: Path,
    upstream_release: str,
    upstream_commit: str,
    quarantine_mtime_ns: int,
    registry_mtime_ns: int,
    validator_mtime_ns: int,
) -> dict[str, Any]:
    del quarantine_mtime_ns, registry_mtime_ns, validator_mtime_ns
    return _audit_gate_registry_uncached(
        repository_root,
        vendor_root,
        upstream_release=upstream_release,
        upstream_commit=upstream_commit,
    )


def audit_gate_registry(
    repository_root: Path,
    vendor_root: Path,
    *,
    upstream_release: str,
    upstream_commit: str,
) -> dict[str, Any]:
    """Audit immutable release resources, invalidating the cache when authorities change."""
    quarantine_path = repository_root / "configs" / "qingshan-gate-registry-quarantine.json"
    registry_path = vendor_root / "configs" / "GATE_REGISTRY_v3_20260716.json"
    validator_path = vendor_root / "tools" / "gate_registry_v3_check.py"
    try:
        result = _cached_gate_registry_audit(
            repository_root.resolve(),
            vendor_root.resolve(),
            upstream_release,
            upstream_commit,
            quarantine_path.stat().st_mtime_ns,
            registry_path.stat().st_mtime_ns,
            validator_path.stat().st_mtime_ns,
        )
    except OSError as exc:
        raise GateRegistryAuditError("gate registry audit authorities are absent") from exc
    return deepcopy(result)
