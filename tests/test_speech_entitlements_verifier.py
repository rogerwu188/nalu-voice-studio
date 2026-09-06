import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify-speech-entitlements.py"
SPEECH = "com.apple.security.personal-information.speech-recognition"
AUDIO = "com.apple.security.device.audio-input"


@pytest.mark.parametrize("value,valid", [
    ({SPEECH: True, AUDIO: True}, True),
    ({SPEECH: True}, False),
    ({AUDIO: True}, False),
    ({SPEECH: False, AUDIO: True}, False),
    ({SPEECH: "true", AUDIO: True}, False),
    ({SPEECH: 1, AUDIO: True}, False),
    ({"com": {"apple": {"security": {"personal-information": {
        "speech-recognition": True}}}}, AUDIO: True}, False),
    ([], False),
])
def test_exact_boolean_entitlements(tmp_path, value, valid):
    path = tmp_path / "entitlements.plist"
    path.write_bytes(plistlib.dumps(value))
    result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, check=False)
    assert (result.returncode == 0) is valid


def test_missing_and_corrupt_plist_fail(tmp_path):
    path = tmp_path / "missing.plist"
    for data in (None, b"not a plist"):
        if data is not None:
            path.write_bytes(data)
        result = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, check=False)
        assert result.returncode != 0
