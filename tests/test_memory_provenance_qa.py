import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/qa-memory-provenance.py"


def test_optimized_python_cannot_emit_false_pass(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    result = subprocess.run(
        [sys.executable, "-O", str(SCRIPT), "--app", str(tmp_path),
         "--evidence", str(evidence), "--source-commit", "1" * 40],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert "QA assertions must be enabled" in result.stderr
    assert not evidence.exists()


def test_short_source_identity_is_rejected_before_runtime_launch(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--app", str(tmp_path),
         "--evidence", str(evidence), "--source-commit", "abcdef0"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert "Source commit must be a full lowercase Git SHA" in result.stderr
    assert not evidence.exists()
