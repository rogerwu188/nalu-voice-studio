from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .postproduction_lineage_qa import audio_energy_fingerprint


class SemanticRecognizerError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalSemanticRecognition:
    transcript: str
    segments: list[dict[str, Any]]
    recognizer_id: str
    recognizer_version: str
    locale: str
    generated_at: str
    source_master_sha256: str
    decoded_audio_fingerprint: str
    recognizer_executable_sha256: str
    local_recognition: bool = True
    network_used: bool = False


class LocalSemanticRecognizer(Protocol):
    def recognize(
        self, master_path: Path, *, source_master_sha256: str
    ) -> LocalSemanticRecognition: ...


class DisabledLocalSemanticRecognizer:
    """Fail-closed default until a reviewed local recognizer is registered."""

    def recognize(
        self, master_path: Path, *, source_master_sha256: str
    ) -> LocalSemanticRecognition:
        del master_path, source_master_sha256
        raise SemanticRecognizerError("approved local semantic recognizer is not configured")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class AppleSpeechRecognizer:
    """Execute the packaged Apple Speech helper without a network fallback."""

    def __init__(self, binary_path: Path, timeout_seconds: int = 900):
        self.binary_path = binary_path.resolve()
        self.timeout_seconds = timeout_seconds

    def recognize(
        self, master_path: Path, *, source_master_sha256: str
    ) -> LocalSemanticRecognition:
        if not self.binary_path.is_file() or not os.access(self.binary_path, os.X_OK):
            raise SemanticRecognizerError("packaged Apple Speech recognizer is unavailable")
        executable_sha256 = _file_sha256(self.binary_path)
        request = {
            "schema_version": "nalu.apple-speech-request/v1",
            "master_path": str(master_path.resolve()),
            "source_master_sha256": source_master_sha256,
            "locale": "zh-CN",
            "requires_on_device_recognition": True,
            "network_fallback_allowed": False,
        }
        environment = {
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(master_path.parent),
            "LANG": "zh_CN.UTF-8",
        }
        try:
            completed = subprocess.run(
                [str(self.binary_path)],
                input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                cwd=master_path.parent,
                env=environment,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SemanticRecognizerError(
                "Apple on-device speech recognition could not complete"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace")[:1000]
            raise SemanticRecognizerError(
                f"Apple on-device speech recognition failed: {detail}"
            )
        if len(completed.stdout) > 8 * 1024 * 1024:
            raise SemanticRecognizerError("Apple Speech recognizer output exceeded safety limit")
        try:
            response = json.loads(completed.stdout)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise SemanticRecognizerError("Apple Speech recognizer returned invalid JSON") from exc
        if response.get("schema_version") != "nalu.apple-speech-result/v1":
            raise SemanticRecognizerError("Apple Speech recognizer returned unsupported evidence")
        if (
            response.get("source_master_sha256") != source_master_sha256
            or response.get("locale") != "zh-CN"
            or response.get("local_recognition") is not True
            or response.get("network_used") is not False
        ):
            raise SemanticRecognizerError("Apple Speech recognizer violated local execution policy")
        transcript = response.get("transcript")
        segments = response.get("segments")
        generated_at = response.get("generated_at")
        recognizer_version = response.get("recognizer_version")
        if (
            not isinstance(transcript, str)
            or not transcript.strip()
            or not isinstance(segments, list)
            or not segments
            or not isinstance(generated_at, str)
            or not generated_at
            or not isinstance(recognizer_version, str)
            or not recognizer_version
        ):
            raise SemanticRecognizerError("Apple Speech recognizer returned incomplete evidence")
        if _file_sha256(self.binary_path) != executable_sha256:
            raise SemanticRecognizerError("Apple Speech recognizer changed during execution")
        try:
            decoded_audio_fingerprint = audio_energy_fingerprint(master_path)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SemanticRecognizerError(
                "sealed master audio could not be fingerprinted after recognition"
            ) from exc
        return LocalSemanticRecognition(
            transcript=transcript,
            segments=segments,
            recognizer_id="apple-speech-on-device",
            recognizer_version=recognizer_version,
            locale="zh-CN",
            generated_at=generated_at,
            source_master_sha256=source_master_sha256,
            decoded_audio_fingerprint=decoded_audio_fingerprint,
            recognizer_executable_sha256=executable_sha256,
            local_recognition=True,
            network_used=False,
        )
