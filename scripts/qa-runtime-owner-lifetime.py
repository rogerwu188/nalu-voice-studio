"""Exercise the exact packaged Runtime with synthetic owner pipes and local data."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from runpy import run_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if sys.flags.optimize:
        raise RuntimeError("QA assertions must be enabled")
    binary = args.app.resolve() / "Contents/Resources/runtime/nalu-runtime"
    with binary.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    scenario = run_path(str(Path(__file__).resolve().parents[1] / "tests/test_runtime_owner_pipe.py"))
    with tempfile.TemporaryDirectory(prefix="nalu-owner-lifetime-") as directory:
        scenario["rehearse_owner_lifetime"](
            Path(directory), command=[str(binary)], startup_timeout=120,
            resources=args.app.resolve() / "Contents/Resources/runtime-resources",
        )
    report = {
        "schema": "nalu.packaged-owner-lifetime/v1",
        "runtime_sha256": digest,
        "result": "PASS",
        "scope": "two packaged Runtime processes, synthetic stdin EOF, loopback only",
        "other_instance_preserved": True,
        "sqlite_integrity": "ok",
        "native_app_crash_verified": False,
        "production_job_recovery_verified": False,
        "project_complete": False,
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(report, indent=2) + "\n")
    print("Packaged owner-pipe lifetime QA passed; native app crash acceptance remains open")


if __name__ == "__main__":
    main()
