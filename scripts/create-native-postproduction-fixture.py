#!/usr/bin/env python3
"""Build isolated synthetic postproduction QA data, never call real providers."""

import json
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_image_review import test_exact_saved_frame_preview_and_versioned_user_review


def validate_fixture(root):
    """Reject an unusable or revoked fixture before advertising it for native QA."""
    with TestClient(create_app(root / "nalu.sqlite3", root / "data")) as api:
        base = "/v1/production-runs/run_frame_review"
        run = api.get(base)
        assert run.status_code == 200 and run.json()["status"] == "qa_review", run.text
        integrity = api.get(base + "/rendered-output-integrity")
        assert integrity.status_code == 200, integrity.text
        repair = api.get(base + "/postproduction-repair-plan")
        assert repair.status_code == 200 and repair.json()["repair_tasks"], repair.text
        return repair.json()["plan_sha256"]


def main():
    root = Path(tempfile.mkdtemp(prefix="nalu-native-postproduction-")).resolve()
    with pytest.MonkeyPatch.context() as patches:
        test_exact_saved_frame_preview_and_versioned_user_review(
            root, patches, "video_assemble_stage_render", preserve_native_fixture=True)
    # The fixture's closed SQLite database becomes the isolated app's database.
    (root / "db").rename(root / "nalu.sqlite3")
    plan_sha = validate_fixture(root)
    print(json.dumps({"application_support": str(root),
                      "repair_plan_sha256": plan_sha,
                      "provider_execution_verified": False,
                      "real_story_or_master_accepted": False}))


if __name__ == "__main__":
    main()
