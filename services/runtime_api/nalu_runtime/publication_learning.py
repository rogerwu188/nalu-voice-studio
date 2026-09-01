from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


class PublicationVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class PublicationVerification:
    platform: Literal["youtube", "bilibili"]
    remote_publication_id: str
    remote_state: Literal["published"]
    release_manifest_sha256: str
    published_at: str
    channel_reference: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class PublicationMetricsVerification:
    platform: Literal["youtube", "bilibili"]
    remote_publication_id: str
    window_start: str
    window_end: str
    views: int
    unique_viewers: int
    watch_time_seconds: int
    average_view_duration_seconds: float
    completion_rate: float
    likes: int
    comments: int
    shares: int
    followers_gained: int
    evidence: dict[str, Any]


class PublicationLearningVerifier(Protocol):
    def lookup_publication(
        self,
        *,
        platform: str,
        remote_publication_id: str,
        channel_reference: str,
        release_manifest_sha256: str,
    ) -> PublicationVerification: ...

    def lookup_metrics(
        self,
        *,
        platform: str,
        remote_publication_id: str,
        window_start: str,
        window_end: str,
    ) -> PublicationMetricsVerification: ...


class DisabledPublicationLearningVerifier:
    def lookup_publication(
        self,
        *,
        platform: str,
        remote_publication_id: str,
        channel_reference: str,
        release_manifest_sha256: str,
    ) -> PublicationVerification:
        raise PublicationVerificationError(
            "no authorized publication verification provider is configured"
        )

    def lookup_metrics(
        self,
        *,
        platform: str,
        remote_publication_id: str,
        window_start: str,
        window_end: str,
    ) -> PublicationMetricsVerification:
        raise PublicationVerificationError(
            "no authorized publication metrics provider is configured"
        )
