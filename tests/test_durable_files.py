from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from nalu_runtime import secure_files


def test_publish_exclusive_text_syncs_file_and_directory_and_survives_reopen(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "evidence.json"
    encoded = '{"status":"PASS","digest":"bound"}\n'
    real_fsync = secure_files.os.fsync
    synced_kinds: list[str] = []

    def observe_fsync(descriptor: int) -> None:
        target = Path(f"/dev/fd/{descriptor}")
        synced_kinds.append("directory" if target.resolve().is_dir() else "file")
        real_fsync(descriptor)

    with patch.object(secure_files.os, "fsync", side_effect=observe_fsync):
        secure_files.publish_exclusive_text(destination, encoded)

    assert destination.read_text(encoding="utf-8") == encoded
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == hashlib.sha256(
        encoded.encode()
    ).hexdigest()
    assert "file" in synced_kinds
    assert synced_kinds.count("directory") >= 2
    assert list(tmp_path.glob(".*.tmp")) == []


def test_publish_exclusive_text_preserves_existing_artifact_and_cleans_temporary_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "evidence.json"
    secure_files.publish_exclusive_text(destination, "first\n")

    with pytest.raises(FileExistsError):
        secure_files.publish_exclusive_text(destination, "second\n")

    assert destination.read_text(encoding="utf-8") == "first\n"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_replace_text_durably_syncs_replacement_and_reopens_exact_bytes(tmp_path: Path) -> None:
    destination = tmp_path / "mutable-report.json"
    destination.write_text("old\n", encoding="utf-8")
    encoded = '{"status":"FAIL","revision":2}\n'
    real_fsync = secure_files.os.fsync
    synced_kinds: list[str] = []

    def observe_fsync(descriptor: int) -> None:
        target = Path(f"/dev/fd/{descriptor}")
        synced_kinds.append("directory" if target.resolve().is_dir() else "file")
        real_fsync(descriptor)

    with patch.object(secure_files.os, "fsync", side_effect=observe_fsync):
        secure_files.replace_text_durably(destination, encoded)

    reopened = destination.read_bytes()
    assert reopened == encoded.encode()
    assert hashlib.sha256(reopened).hexdigest() == hashlib.sha256(encoded.encode()).hexdigest()
    assert "file" in synced_kinds
    assert synced_kinds.count("directory") >= 2
    assert list(tmp_path.glob(".*.tmp")) == []


def test_replace_text_durably_cleans_temporary_file_when_promotion_fails(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "mutable-report.json"
    destination.write_text("old\n", encoding="utf-8")

    with (
        patch.object(secure_files.os, "replace", side_effect=OSError("disk promotion failed")),
        pytest.raises(OSError, match="disk promotion failed"),
    ):
        secure_files.replace_text_durably(destination, "new\n")

    assert destination.read_text(encoding="utf-8") == "old\n"
    assert list(tmp_path.glob(".*.tmp")) == []
