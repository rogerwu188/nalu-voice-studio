#!/usr/bin/env python3
"""Execute a statically verified Qingshan candidate's registered test contract."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from runpy import run_path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "configs" / "qingshan-candidate-audit.json"
SENSITIVE_ENV_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL")
TEST_COUNT = re.compile(r"Ran (\d+) tests?")
SKIPPED_COUNT = re.compile(r"skipped=(\d+)")


def safe_environment(checkout: Path) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS)
    }
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "QINGSHAN_ENGINE_ROOT": str(checkout),
        }
    )
    for name in (
        "GIGGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "YOUTUBE_CLIENT_SECRETS",
    ):
        environment.pop(name, None)
    return environment


def run_command(checkout: Path, arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "qingshan_engine.cli", *arguments],
        cwd=checkout,
        env=safe_environment(checkout),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    output = "\n".join(value for value in (result.stdout, result.stderr) if value)
    test_counts = [int(value) for value in TEST_COUNT.findall(output)]
    skipped_counts = [int(value) for value in SKIPPED_COUNT.findall(output)]
    return {
        "command": ["python", "-m", "qingshan_engine.cli", *arguments],
        "returncode": result.returncode,
        "test_count": sum(test_counts),
        "skipped_count": sum(skipped_counts),
        "output": output,
    }


def execute_registered_tests(checkout: Path) -> dict[str, Any]:
    manifest = json.loads(
        (checkout / "configs" / "PORTABLE_CORE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    doctor = run_command(checkout, ["doctor", "--profile", "core"])
    portable = run_command(checkout, ["test"])
    writer = run_command(checkout, ["writer-doctor"])
    failures = []
    for name, result in (("doctor", doctor), ("portable", portable), ("writer", writer)):
        if result["returncode"] != 0:
            failures.append(f"{name}_exit:{result['returncode']}")
    return {
        "registered_test_execution_performed": True,
        "registered_test_status": "PASS" if not failures else "FAIL",
        "registered_test_module_count": len(manifest.get("portable_test_modules") or []),
        "registered_portable_test_count": portable["test_count"],
        "registered_portable_skipped_count": portable["skipped_count"],
        "registered_writer_test_count": writer["test_count"],
        "registered_test_failures": failures,
        "commands": [doctor["command"], portable["command"], writer["command"]],
    }


def compare_test_evidence(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    fields = (
        "registered_test_execution_performed",
        "registered_test_status",
        "registered_test_module_count",
        "registered_portable_test_count",
        "registered_portable_skipped_count",
        "registered_writer_test_count",
        "registered_test_failures",
    )
    return [
        f"candidate registered-test drift: {field}"
        for field in fields
        if actual.get(field) != expected.get(field)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    auditor = run_path(str(ROOT / "scripts" / "audit_qingshan_candidate.py"))

    with tempfile.TemporaryDirectory(prefix="nalu-qingshan-tests-") as temporary:
        checkout = args.checkout or Path(temporary) / "candidate"
        if args.checkout is None:
            auditor["clone_candidate"](expected, checkout)
        static_audit = auditor["audit_checkout"](checkout.resolve(), expected)
        failures = auditor["compare_audit"](static_audit, expected)
        evidence: dict[str, Any] = {
            "registered_test_execution_performed": False,
            "registered_test_status": "NOT_RUN",
        }
        if not failures:
            evidence = execute_registered_tests(checkout.resolve())
            failures.extend(compare_test_evidence(evidence, expected))

    result = {
        "schema_version": "nalu.qingshan-registered-test-audit/v1",
        "status": "PASS" if not failures else "FAIL",
        "candidate_release": expected.get("candidate_release"),
        "candidate_commit": static_audit.get("candidate_commit"),
        "static_public_interface_status": static_audit.get("public_interface_status"),
        "test_evidence": evidence,
        "failures": failures,
    }
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Qingshan registered tests {result['status']}")
        for failure in failures:
            print(f"- {failure}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
