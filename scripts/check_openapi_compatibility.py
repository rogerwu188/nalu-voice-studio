#!/usr/bin/env python3
"""Fail when the current OpenAPI contract removes a public API surface."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "docs/openapi.json"
METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def contract_at(reference: str) -> dict[str, Any]:
    result = subprocess.run(
        ["git", "show", f"{reference}:{CONTRACT}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def compatibility_failures(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    old_paths, new_paths = old.get("paths", {}), new.get("paths", {})
    for path, old_path in old_paths.items():
        if path not in new_paths:
            failures.append(f"removed path: {path}")
            continue
        for method in METHODS.intersection(old_path):
            if method not in new_paths[path]:
                failures.append(f"removed operation: {method.upper()} {path}")

    old_schemas = old.get("components", {}).get("schemas", {})
    new_schemas = new.get("components", {}).get("schemas", {})
    for name, old_schema in old_schemas.items():
        if name not in new_schemas:
            failures.append(f"removed schema: {name}")
            continue
        old_properties = set(old_schema.get("properties", {}))
        new_properties = set(new_schemas[name].get("properties", {}))
        for field in sorted(old_properties - new_properties):
            failures.append(f"removed field: {name}.{field}")
        old_required = set(old_schema.get("required", []))
        new_required = set(new_schemas[name].get("required", []))
        for field in sorted(new_required - old_required):
            failures.append(f"new required field: {name}.{field}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Git ref containing the reviewed baseline")
    args = parser.parse_args()
    old = contract_at(args.base)
    new = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    failures = compatibility_failures(old, new)
    if failures:
        print("Unreviewed breaking OpenAPI changes detected:")
        for failure in failures:
            print(f"- {failure}")
        print("Publish a versioned /v2 contract and migration plan instead of changing /v1 in place.")
        return 1
    print(f"OpenAPI contract is backward compatible with {args.base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
