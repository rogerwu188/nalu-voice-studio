import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

FEEDBACK_MEMBER = (
    "Nalu Voice Studio.app/Contents/Resources/runtime-resources/configs/feedback-export.json"
)
HANDOFF_MEMBER = (
    "Nalu Voice Studio.app/Contents/Resources/runtime-resources/configs/development-handoff.json"
)


def load_evidence_module():
    path = Path(__file__).resolve().parents[1] / "scripts/packaged_qa_evidence.py"
    spec = importlib.util.spec_from_file_location("packaged_qa_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def feedback_policy() -> dict[str, object]:
    return {
        "schema_version": "nalu.feedback-export-policy/v1",
        "enabled": False,
        "administrator_authorized": False,
        "provider": "github_issues",
        "endpoint": "",
        "repository": "",
        "max_payload_bytes": 65536,
    }


def handoff_policy() -> dict[str, object]:
    return {
        "schema_version": "nalu.development-handoff-policy/v1",
        "enabled": False,
        "administrator_authorized": False,
        "provider": "development_agent",
        "endpoint": "",
        "max_payload_bytes": 65536,
    }


def write_release(
    path: Path,
    *,
    feedback: dict[str, object] | None = None,
    handoff: dict[str, object] | None = None,
) -> None:
    with zipfile.ZipFile(path, "w") as release:
        release.writestr(FEEDBACK_MEMBER, json.dumps(feedback or feedback_policy()))
        release.writestr(HANDOFF_MEMBER, json.dumps(handoff or handoff_policy()))


def test_packaged_evolution_policies_are_disabled_and_target_free(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    release_path = tmp_path / "Nalu-Voice-Studio-macOS.zip"
    write_release(release_path)

    hashes = evidence.verify_controlled_evolution_policies(release_path)
    assert set(hashes) == {
        "feedback_export_policy_sha256",
        "development_handoff_policy_sha256",
    }


@pytest.mark.parametrize("boundary", ["feedback", "handoff"])
def test_enabled_or_targeted_evolution_policy_fails_closed(
    tmp_path: Path, boundary: str
) -> None:
    evidence = load_evidence_module()
    release_path = tmp_path / "Nalu-Voice-Studio-macOS.zip"
    feedback = feedback_policy()
    handoff = handoff_policy()
    if boundary == "feedback":
        feedback["enabled"] = True
        feedback["endpoint"] = "https://example.invalid/issues"
    else:
        handoff["administrator_authorized"] = True
        handoff["endpoint"] = "https://example.invalid/handoff"
    write_release(release_path, feedback=feedback, handoff=handoff)

    with pytest.raises(RuntimeError, match="disabled and target-free"):
        evidence.verify_controlled_evolution_policies(release_path)


def test_release_artifact_binds_exact_inner_zip_and_checksum(tmp_path: Path) -> None:
    evidence = load_evidence_module()
    release_path = tmp_path / "Nalu-Voice-Studio-macOS.zip"
    write_release(release_path)
    release_sha = hashlib.sha256(release_path.read_bytes()).hexdigest()
    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(release_path, release_path.name)
        archive.writestr(
            f"{release_path.name}.sha256", f"{release_sha}  dist/{release_path.name}\n"
        )
    artifact_digest = f"sha256:{hashlib.sha256(archive_path.read_bytes()).hexdigest()}"

    assert evidence.verify_release_artifact_archive(
        archive_path=archive_path,
        expected_artifact_digest=artifact_digest,
        release_zip_path=release_path,
    )["release_zip_sha256"] == release_sha

    release_path.write_bytes(b"substituted")
    with pytest.raises(RuntimeError, match="not the release embedded"):
        evidence.verify_release_artifact_archive(
            archive_path=archive_path,
            expected_artifact_digest=artifact_digest,
            release_zip_path=release_path,
        )
