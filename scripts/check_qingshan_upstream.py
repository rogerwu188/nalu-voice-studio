#!/usr/bin/env python3
"""Verify the pinned Qingshan import and optionally discover a newer release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs" / "qingshan-upstream.json"
VENDOR_ROOT = ROOT / "vendor" / "qingshan"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vendor_digest() -> str:
    rows = []
    tracked = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "vendor/qingshan"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for relative in sorted(tracked):
        path = ROOT / relative
        rows.append(f"{sha256(path)}  {path.relative_to(VENDOR_ROOT)}\n")
    return hashlib.sha256("".join(rows).encode()).hexdigest()


def verify(manifest: dict) -> list[str]:
    failures = []
    if manifest.get("schema_version") != "nalu.qingshan-upstream/v1":
        failures.append("unsupported upstream manifest schema")
    if vendor_digest() != manifest.get("vendor_content_sha256"):
        failures.append("vendor tree differs from the reviewed upstream snapshot")
    for name, capability in manifest.get("capabilities", {}).items():
        path = VENDOR_ROOT / capability["path"]
        if not path.is_file():
            failures.append(f"missing capability {name}: {capability['path']}")
        elif sha256(path) != capability["sha256"]:
            failures.append(f"capability hash mismatch: {name}")
    if not (VENDOR_ROOT / "LICENSE").is_file():
        failures.append("reviewed upstream license is absent")
    return failures


def latest_release(repository: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Nalu-Upstream-Audit"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-latest", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures = verify(manifest)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"Pinned Qingshan snapshot verified: {manifest['release']} @ {manifest['commit']}")

    if args.check_latest:
        latest = latest_release(manifest["repository"])
        tag = latest["tag_name"]
        available = tag != manifest["release"]
        write_output("update_available", str(available).lower())
        write_output("latest_tag", tag)
        write_output("latest_url", latest["html_url"])
        print(f"Latest upstream release: {tag}; update_available={available}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
