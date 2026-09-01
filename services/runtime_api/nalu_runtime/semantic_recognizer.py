from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


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
