import hashlib
import importlib.util
from pathlib import Path

import pytest


def load_evidence_module():
    path = Path(__file__).resolve().parents[1] / "scripts/packaged_qa_evidence.py"
    spec = importlib.util.spec_from_file_location("packaged_qa_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_zip_digest_is_recomputed_and_mismatch_fails_closed(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    release_zip = tmp_path / "release.zip"
    release_zip.write_bytes(b"downloaded-release")
    expected = hashlib.sha256(release_zip.read_bytes()).hexdigest()

    assert evidence.verify_release_zip(release_zip, expected) == expected
    with pytest.raises(RuntimeError, match="does not match"):
        evidence.verify_release_zip(release_zip, "0" * 64)
    with pytest.raises(RuntimeError, match="exactly 64"):
        evidence.verify_release_zip(release_zip, "not-a-digest")


def test_evidence_identifiers_require_complete_digests() -> None:
    evidence = load_evidence_module()
    evidence.validate_evidence_identifiers(
        artifact_digest=f"sha256:{'a' * 64}", source_commit="b" * 40
    )

    with pytest.raises(RuntimeError, match="artifact digest"):
        evidence.validate_evidence_identifiers(
            artifact_digest="trusted", source_commit="b" * 40
        )
    with pytest.raises(RuntimeError, match="source commit"):
        evidence.validate_evidence_identifiers(
            artifact_digest=f"sha256:{'a' * 64}", source_commit="main"
        )


@pytest.mark.parametrize("duration_seconds", [2, 3, 59, 60, 301, 1800])
def test_editorial_fixture_never_uses_whole_source_passthrough(
    duration_seconds: int,
) -> None:
    evidence = load_evidence_module()
    _long_soak, source_duration, ranges = evidence.editorial_fixture_layout(
        duration_seconds
    )

    assert sum(end - start for start, end in ranges) == duration_seconds
    assert all(not (start <= 0.05 and end >= source_duration - 0.05) for start, end in ranges)
    assert all(0 <= start < end <= source_duration for start, end in ranges)
