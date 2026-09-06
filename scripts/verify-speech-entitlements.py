#!/usr/bin/env python3
"""Validate exact dotted entitlement keys, never plist key-path expressions."""

import argparse
import plistlib
import sys
from pathlib import Path

REQUIRED = (
    "com.apple.security.personal-information.speech-recognition",
    "com.apple.security.device.audio-input",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plist", type=Path)
    args = parser.parse_args()
    try:
        with args.plist.open("rb") as stream:
            value = plistlib.load(stream)
    except (OSError, ValueError, plistlib.InvalidFileException):
        print("Cannot read speech entitlements plist.", file=sys.stderr)
        return 1
    if not isinstance(value, dict) or any(value.get(key) is not True for key in REQUIRED):
        print("Speech recognizer requires boolean speech-recognition and audio-input entitlements.",
              file=sys.stderr)
        return 1
    print("Speech recognizer entitlements verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
