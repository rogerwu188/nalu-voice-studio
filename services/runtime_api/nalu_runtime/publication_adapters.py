from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ReleasePackage


@dataclass(frozen=True)
class PublicationDryRunAdapter:
    platform: str
    version: str
    caption_delivery: str
    cover_delivery: str

    def compile(self, package: ReleasePackage, channel_reference: str) -> dict[str, Any]:
        artifacts = {artifact.kind: artifact for artifact in package.artifacts}
        missing = [kind for kind in ("master_video", "captions", "cover") if kind not in artifacts]
        if missing:
            raise ValueError(f"release package is missing required artifacts: {', '.join(missing)}")
        master = artifacts["master_video"]
        captions = artifacts["captions"]
        cover = artifacts["cover"]
        if master.media_type != "video/mp4":
            raise ValueError("publication dry-run requires an MP4 master")
        if captions.media_type != "text/vtt":
            raise ValueError("publication dry-run requires WebVTT captions")
        if cover.media_type not in {"image/jpeg", "image/png"}:
            raise ValueError("publication dry-run requires a JPEG or PNG cover")
        return {
            "platform": self.platform,
            "adapter_version": self.version,
            "channel_reference": channel_reference,
            "release_manifest_sha256": package.manifest_sha256,
            "media": {
                "master": master.model_dump(mode="json"),
                "captions": captions.model_dump(mode="json"),
                "cover": cover.model_dump(mode="json"),
            },
            "delivery": {
                "captions": self.caption_delivery,
                "cover": self.cover_delivery,
            },
            "operations": [
                "validate immutable release package",
                "validate platform-specific media mapping",
                "prepare duplicate-guard fingerprint",
            ],
            "network_operations": [],
        }


PUBLICATION_DRY_RUN_ADAPTERS = {
    "youtube": PublicationDryRunAdapter(
        platform="youtube",
        version="nalu.youtube-dry-run/v1",
        caption_delivery="webvtt_sidecar",
        cover_delivery="custom_thumbnail",
    ),
    "bilibili": PublicationDryRunAdapter(
        platform="bilibili",
        version="nalu.bilibili-dry-run/v1",
        caption_delivery="webvtt_conversion_boundary",
        cover_delivery="cover_upload",
    ),
}


def publication_adapter(platform: str) -> PublicationDryRunAdapter:
    try:
        return PUBLICATION_DRY_RUN_ADAPTERS[platform]
    except KeyError as exc:
        raise ValueError(f"unsupported publication platform: {platform}") from exc
