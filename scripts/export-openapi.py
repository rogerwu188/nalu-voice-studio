#!/usr/bin/env python3
"""Export or verify the committed Runtime API contract."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from nalu_runtime.app import create_app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "openapi.json"


def rendered_contract() -> str:
    with tempfile.TemporaryDirectory(prefix="nalu-openapi-") as directory:
        root = Path(directory)
        schema = create_app(root / "contract.sqlite3", root / "data").openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_contract()
    if args.check:
        if not CONTRACT.exists() or CONTRACT.read_text(encoding="utf-8") != rendered:
            print("OpenAPI contract is stale; run scripts/export-openapi.py")
            return 1
        print("OpenAPI contract is current")
        return 0
    CONTRACT.write_text(rendered, encoding="utf-8")
    print(f"Wrote {CONTRACT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
