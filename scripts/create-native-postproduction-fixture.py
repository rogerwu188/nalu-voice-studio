#!/usr/bin/env python3
"""Build isolated synthetic postproduction QA data, never call real providers."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_image_review import test_exact_saved_frame_preview_and_versioned_user_review


def main():
    root = Path(tempfile.mkdtemp(prefix="nalu-native-postproduction-")).resolve()
    with pytest.MonkeyPatch.context() as patches:
        test_exact_saved_frame_preview_and_versioned_user_review(
            root, patches, "video_assemble_stage_render", preserve_native_fixture=True)
    # The fixture's closed SQLite database becomes the isolated app's database.
    (root / "db").rename(root / "nalu.sqlite3")
    print(json.dumps({"application_support": str(root),
                      "provider_execution_verified": False,
                      "real_story_or_master_accepted": False}))


if __name__ == "__main__":
    main()
