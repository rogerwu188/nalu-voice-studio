#!/usr/bin/env python3
"""Reproduce a quarantined Qingshan audit without executing upstream code."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "configs" / "qingshan-candidate-audit.json"
REQUIRED_GATE_FIELDS = {
    "gate_id",
    "stage",
    "implementation_type",
    "code_paths",
    "test_paths",
    "parameters",
    "authorization_ref",
    "last_backtest_date",
}
LIVE_PREFIXES = ("build_", "compile_", "episode_", "submit_")
BLOCKING_MARKERS = ("BLOCK_SUBMIT", "FAIL_CLOSED", "FAIL_HARD")
PUBLIC_PACKAGE = "qingshan-short-drama-engine"
PUBLIC_CLI_ENTRYPOINT = "qingshan_engine.cli:main"
FORBIDDEN_PUBLIC_IMPORTS = {"agentcut", "backlot_os", "backlotos"}


def run_git(checkout: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_tree_digest(checkout: Path) -> str:
    rows: list[str] = []
    for relative in sorted(run_git(checkout, "-c", "core.quotePath=false", "ls-files").splitlines()):
        path = checkout / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"tracked candidate path is not a regular file: {relative}")
        rows.append(f"{sha256(path)}  {relative}\n")
    if not rows:
        raise ValueError("candidate checkout has no tracked files")
    return hashlib.sha256("".join(rows).encode()).hexdigest()


def literal_assignment(path: Path, name: str) -> ast.AST | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return node.value
    return None


def declared_runtime_gate_ids(path: Path) -> set[str]:
    value = literal_assignment(path, "RUNTIME_GATE_IDS")
    if isinstance(value, ast.Call) and value.args:
        value = value.args[0]
    if not isinstance(value, (ast.Set, ast.List, ast.Tuple)):
        return set()
    return {
        item.value
        for item in value.elts
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def declared_runtime_gate_bindings(path: Path) -> dict[str, str]:
    value = literal_assignment(path, "RUNTIME_GATE_BINDINGS")
    if not isinstance(value, ast.Dict):
        return {}
    result: dict[str, str] = {}
    for key, item in zip(value.keys, value.values):
        if (
            isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and isinstance(item, ast.Constant)
            and isinstance(item.value, str)
        ):
            result[key.value] = item.value
    return result


def parsed_tree(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def called_function_names(path: Path) -> set[str]:
    tree = parsed_tree(path)
    if tree is None:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def imported_tool_modules(path: Path) -> set[str]:
    tree = parsed_tree(path)
    if tree is None:
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[-1] for alias in node.names)
    return modules


def executable_runtime_gate_ids(path: Path) -> set[str]:
    declared = declared_runtime_gate_ids(path)
    calls = called_function_names(path)
    if path.name == "episode_stage_gate_runner.py":
        return declared if "execute_gate" in calls else set()
    bindings = declared_runtime_gate_bindings(path)
    return {gate_id for gate_id in declared if bindings.get(gate_id) in calls}


def live_unregistered_blockers(registry: dict[str, Any], base: Path) -> list[str]:
    declared = {
        path
        for gate in registry.get("gates", [])
        for path in (gate.get("code_paths") or [])
    }
    tools_dir = base / "tools"
    imported_by_live: dict[str, list[str]] = {}
    for caller in tools_dir.glob("*.py"):
        if caller.name.startswith(LIVE_PREFIXES):
            for module in imported_tool_modules(caller):
                imported_by_live.setdefault(module, []).append(str(caller.relative_to(base)))
    failures: list[str] = []
    for path in sorted(tools_dir.glob("*.py")):
        if not (path.stem.endswith("_gate") or path.stem.endswith("_guard")):
            continue
        callers = imported_by_live.get(path.stem) or []
        if not callers:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        relative = str(path.relative_to(base))
        if any(marker in text for marker in BLOCKING_MARKERS) and relative not in declared:
            failures.append(
                f"UNREGISTERED_BLOCKER_IN_LIVE_PATH:{relative}:"
                f"callers={','.join(sorted(callers))}"
            )
    return failures


def imported_roots(path: Path) -> set[str]:
    tree = parsed_tree(path)
    if tree is None:
        return set()
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def validate_public_interface(base: Path) -> dict[str, Any]:
    """Validate the installable public engine surface without importing it."""
    failures: list[str] = []
    pyproject_path = base / "pyproject.toml"
    portable_manifest_path = base / "configs" / "PORTABLE_CORE_MANIFEST.json"
    package_dir = base / "qingshan_engine"
    version = ""
    entrypoint = ""

    try:
        text = pyproject_path.read_text(encoding="utf-8")
        project_match = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
        scripts_match = re.search(r"(?ms)^\[project\.scripts\]\s*(.*?)(?=^\[|\Z)", text)
        if project_match is None or scripts_match is None:
            raise ValueError("required project sections are absent")
        project = project_match.group(1)
        scripts = scripts_match.group(1)

        def string_value(section: str, key: str) -> str:
            match = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"\s*$', section)
            return match.group(1) if match else ""

        version = string_value(project, "version")
        entrypoint = string_value(scripts, "qingshan")
        if string_value(project, "name") != PUBLIC_PACKAGE:
            failures.append("public_interface:unexpected_package_name")
        if entrypoint != PUBLIC_CLI_ENTRYPOINT:
            failures.append("public_interface:missing_stable_cli_entrypoint")
        if re.search(r'(?m)^\s*license\s*=\s*\{\s*file\s*=\s*"LICENSE"\s*\}\s*$', project) is None:
            failures.append("public_interface:missing_mit_license_binding")
        if re.search(r"(?m)^\s*dependencies\s*=\s*\[\s*\]\s*$", project) is None:
            failures.append("public_interface:core_has_required_third_party_dependencies")
    except (OSError, ValueError):
        failures.append("public_interface:invalid_pyproject")

    for relative in ("LICENSE", "qingshan_engine/__init__.py", "qingshan_engine/cli.py"):
        if not (base / relative).is_file():
            failures.append(f"public_interface:missing_path:{relative}")

    for path in sorted(package_dir.glob("*.py")):
        for imported in sorted(imported_roots(path) & FORBIDDEN_PUBLIC_IMPORTS):
            failures.append(f"public_interface:private_import:{path.relative_to(base)}:{imported}")

    manifest_sha256 = ""
    try:
        manifest = json.loads(portable_manifest_path.read_text(encoding="utf-8"))
        manifest_sha256 = sha256(portable_manifest_path)
        if manifest.get("schema") != "qingshan.portable_core_manifest.v1":
            failures.append("public_interface:invalid_portable_manifest_schema")
        if manifest.get("version") != version:
            failures.append("public_interface:portable_manifest_version_mismatch")
        required = manifest.get("required_files")
        if not isinstance(required, list) or not required:
            failures.append("public_interface:portable_manifest_has_no_required_files")
        else:
            for relative in required:
                if not isinstance(relative, str) or Path(relative).is_absolute():
                    failures.append(f"public_interface:nonportable_required_path:{relative}")
                elif not (base / relative).is_file():
                    failures.append(f"public_interface:missing_required_path:{relative}")
    except (OSError, json.JSONDecodeError):
        failures.append("public_interface:invalid_portable_manifest")

    return {
        "public_interface_status": "PASS" if not failures else "FAIL",
        "public_interface_version": version,
        "public_cli_entrypoint": entrypoint,
        "portable_core_manifest_sha256": manifest_sha256,
        "public_interface_failures": failures,
    }


def validate_registry(registry: dict[str, Any], base: Path) -> dict[str, Any]:
    failures: list[str] = []
    seen: set[str] = set()
    gates = registry.get("gates", [])
    runner_contracts: dict[str, set[str]] = {}
    if not gates:
        failures.append("registry_has_no_gates")
    runtime_bindings: dict[str, list[str]] = {}
    for gate in gates:
        gate_id = gate.get("gate_id", "UNKNOWN")
        failures.extend(
            f"missing_field:{gate_id}:{field}"
            for field in sorted(REQUIRED_GATE_FIELDS - set(gate))
        )
        if gate_id in seen:
            failures.append(f"duplicate_gate_id:{gate_id}")
        seen.add(gate_id)
        gate_type = gate.get("implementation_type")
        if gate_type == "CODED":
            if "stage_runner_paths" not in gate:
                failures.append(f"missing_coded_field:{gate_id}:stage_runner_paths")
            if not gate.get("code_paths"):
                failures.append(f"coded_gate_missing_code:{gate_id}")
            if not gate.get("test_paths"):
                failures.append(f"coded_gate_missing_tests:{gate_id}")
            runners = gate.get("stage_runner_paths") or []
            if not runners:
                failures.append(f"coded_gate_missing_stage_runner:{gate_id}")
            paths = gate.get("code_paths", []) + gate.get("test_paths", []) + runners
            for relative in paths:
                if Path(relative).is_absolute():
                    failures.append(f"nonportable_absolute_path:{gate_id}:{relative}")
                elif not (base / relative).is_file():
                    failures.append(f"missing_path:{gate_id}:{relative}")
            actual: list[str] = []
            for runner in runners:
                runner_path = base / runner
                ids = runner_contracts.setdefault(runner, executable_runtime_gate_ids(runner_path))
                if gate_id in ids:
                    actual.append(runner)
            runtime_bindings[gate_id] = actual
            if not actual:
                failures.append(f"coded_gate_orphaned_from_runtime:{gate_id}")
        elif gate_type == "MANUAL_GATE":
            checklist = gate.get("manual_checklist_path")
            if not checklist:
                failures.append(f"manual_gate_missing_checklist:{gate_id}")
            elif Path(checklist).is_absolute():
                failures.append(f"nonportable_absolute_path:{gate_id}:{checklist}")
            elif not (base / checklist).is_file():
                failures.append(f"missing_path:{gate_id}:{checklist}")
        else:
            failures.append(f"invalid_implementation_type:{gate_id}:{gate_type}")
    failures.extend(live_unregistered_blockers(registry, base))
    return {
        "status": "PASS" if not failures else "FAIL",
        "gate_count": len(gates),
        "coded_gate_count": len(runtime_bindings),
        "runtime_bound_count": sum(bool(value) for value in runtime_bindings.values()),
        "failures": failures,
    }


def audit_checkout(checkout: Path, expected: dict[str, Any]) -> dict[str, Any]:
    registry_path = checkout / expected["gate_registry_path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    integrity = validate_registry(registry, checkout)
    public_interface = validate_public_interface(checkout)
    return {
        "candidate_release": expected["candidate_release"],
        "candidate_commit": run_git(checkout, "rev-parse", "HEAD"),
        "candidate_tree_sha256": tracked_tree_digest(checkout),
        "gate_registry_sha256": sha256(registry_path),
        **public_interface,
        **integrity,
    }


def compare_audit(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    mapping = {"status": "integrity_status"}
    fields = (
        "candidate_release",
        "candidate_commit",
        "candidate_tree_sha256",
        "gate_registry_sha256",
        "public_interface_status",
        "public_interface_version",
        "public_cli_entrypoint",
        "portable_core_manifest_sha256",
        "public_interface_failures",
        "gate_count",
        "coded_gate_count",
        "runtime_bound_count",
        "status",
        "failures",
    )
    return [
        f"candidate audit drift: {field}"
        for field in fields
        if actual.get(field) != expected.get(mapping.get(field, field))
    ]


def clone_candidate(expected: dict[str, Any], destination: Path) -> None:
    repository = expected["repository"]
    if not repository.replace("-", "").replace("_", "").replace("/", "").isalnum():
        raise ValueError("candidate repository contains unsupported characters")
    subprocess.run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            expected["candidate_release"],
            "--",
            f"https://github.com/{repository}.git",
            str(destination),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="nalu-qingshan-audit-") as temporary:
        checkout = args.checkout or Path(temporary) / "candidate"
        if args.checkout is None:
            clone_candidate(expected, checkout)
        actual = audit_checkout(checkout.resolve(), expected)
    failures = compare_audit(actual, expected)
    result = {"status": "PASS" if not failures else "FAIL", "failures": failures, "audit": actual}
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Qingshan isolated candidate audit {result['status']}")
        for failure in failures:
            print(f"- {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
