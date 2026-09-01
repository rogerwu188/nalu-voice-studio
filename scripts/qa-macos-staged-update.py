#!/usr/bin/env python3
"""Exercise the packaged updater locally without downloading or publishing a release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, check=check, capture_output=True, text=True)


def digest(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    entries = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise RuntimeError(f"protected fixture contains symlink: {item}")
        if item.is_file():
            entries.append(
                f"{item.relative_to(path)}\0{item.stat().st_size}\0{digest(item)}\n"
            )
    return hashlib.sha256("".join(entries).encode()).hexdigest()


def plist(path: Path, key: str) -> str:
    return run("/usr/libexec/PlistBuddy", "-c", f"Print :{key}", str(path)).stdout.strip()


def set_plist(path: Path, key: str, value: str) -> None:
    run("/usr/libexec/PlistBuddy", "-c", f"Set :{key} {value}", str(path))


def helper_call(helper: Path, command: str, values: dict[str, str], check: bool = True):
    arguments = [str(helper), command]
    for key, value in values.items():
        arguments.extend((f"--{key}", value))
    return run(*arguments, check=check)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    app = args.app.resolve()
    helper_in_bundle = app / "Contents/Resources/updater/nalu-update-helper"
    if not helper_in_bundle.is_file() or not os.access(helper_in_bundle, os.X_OK):
        raise RuntimeError("packaged update helper is missing")
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="nalu-staged-update-") as temporary:
        root = Path(temporary)
        live = root / "Applications/Nalu Voice Studio.app"
        candidate = root / "candidate/Nalu Voice Studio.app"
        state = root / "state"
        protected = root / "Application Support/Nalu Voice Studio"
        driver = root / "nalu-update-helper"
        shutil.copytree(app, live)
        shutil.copytree(app, candidate)
        shutil.copy2(helper_in_bundle, driver)
        driver.chmod(0o755)
        protected.mkdir(parents=True)
        (protected / "nalu.sqlite3").write_bytes(b"populated ten-episode sqlite fixture")
        (protected / "Projects").mkdir()
        (protected / "Projects/story.json").write_text(
            json.dumps({"episodes": list(range(1, 11))}, sort_keys=True), encoding="utf-8"
        )
        protected_before = digest(protected)
        old_plist = live / "Contents/Info.plist"
        candidate_plist = candidate / "Contents/Info.plist"
        old_version = plist(old_plist, "CFBundleShortVersionString")
        old_build = int(plist(old_plist, "CFBundleVersion"))
        new_version = "0.1.1"
        new_build = old_build + 1
        set_plist(candidate_plist, "CFBundleShortVersionString", new_version)
        set_plist(candidate_plist, "CFBundleVersion", str(new_build))
        run("/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(candidate))
        package = root / "Nalu-Voice-Studio-update.zip"
        run("/usr/bin/ditto", "-c", "-k", "--keepParent", str(candidate), str(package))
        signer = root / "qa-update-fixture-signer"
        sources = sorted((repository / "apps/macos/Sources/NaluUpdateCore").glob("*.swift"))
        run(
            "/usr/bin/xcrun",
            "swiftc",
            *(str(path) for path in sources),
            str(repository / "scripts/qa-update-fixture-signer.swift"),
            "-o",
            str(signer),
        )
        manifest = root / "manifest.json"
        trust = root / "trust.json"
        commit = run("git", "rev-parse", "HEAD").stdout.strip()
        now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        run(
            str(signer),
            str(package),
            str(manifest),
            str(trust),
            new_version,
            str(new_build),
            "test",
            commit,
            now,
        )
        common = {
            "manifest": str(manifest),
            "package": str(package),
            "trust-config": str(trust),
            "installed-build": str(old_build),
        }
        verified = json.loads(helper_call(driver, "verify", common).stdout)
        tampered_manifest = root / "tampered-manifest.json"
        tampered = json.loads(manifest.read_text())
        tampered["build"] = new_build + 1
        tampered_manifest.write_text(json.dumps(tampered), encoding="utf-8")
        tampered_result = helper_call(
            driver, "verify", {**common, "manifest": str(tampered_manifest)}, check=False
        )
        if tampered_result.returncode == 0:
            raise RuntimeError("tampered manifest was accepted")
        downgrade_result = helper_call(
            driver,
            "verify",
            {**common, "installed-build": str(new_build)},
            check=False,
        )
        if downgrade_result.returncode == 0:
            raise RuntimeError("replayed build was accepted")
        first = json.loads(
            helper_call(
                driver,
                "stage",
                {
                    **common,
                    "state-root": str(state),
                    "live-app": str(live),
                    "protected-data": str(protected),
                    "idempotency-key": "qa-health-timeout-0001",
                },
            ).stdout
        )
        if first["phase"] != "awaiting_health" or plist(old_plist, "CFBundleVersion") != str(
            new_build
        ):
            raise RuntimeError("candidate was not activated")
        rolled = json.loads(
            helper_call(
                driver,
                "recover",
                {"state-root": str(state), "transaction-id": first["transaction_id"]},
            ).stdout
        )
        if rolled["phase"] != "rolled_back" or plist(old_plist, "CFBundleVersion") != str(
            old_build
        ):
            raise RuntimeError("health-timeout rollback failed")
        second = json.loads(
            helper_call(
                driver,
                "stage",
                {
                    **common,
                    "state-root": str(state),
                    "live-app": str(live),
                    "protected-data": str(protected),
                    "idempotency-key": "qa-confirmed-update-0002",
                },
            ).stdout
        )
        committed = json.loads(
            helper_call(
                driver,
                "confirm",
                {"state-root": str(state), "transaction-id": second["transaction_id"]},
            ).stdout
        )
        if committed["phase"] != "committed" or plist(old_plist, "CFBundleVersion") != str(
            new_build
        ):
            raise RuntimeError("healthy update was not committed")
        if digest(protected) != protected_before:
            raise RuntimeError("protected project data changed")
        report = {
            "schema_version": "nalu.macos-staged-update-qa/v1",
            "status": "PASS",
            "runtime_mode": "packaged_update_helper",
            "old_version": old_version,
            "old_build": old_build,
            "new_version": new_version,
            "new_build": new_build,
            "manifest_sha256": verified["manifest_sha256"],
            "tampered_manifest_rejected": True,
            "downgrade_or_replay_rejected": True,
            "unconfirmed_update_rolled_back": True,
            "confirmed_update_committed": True,
            "protected_project_data_sha256": protected_before,
            "protected_project_data_preserved": True,
            "network_scope": "offline only; no download, paid model, publication or release",
        }
        report["report_sha256"] = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
