"""Bounded public short-shot retrieval; downloading is not billing or creative QA."""

import hashlib
import http.client
import io
import math
import socket
import time
from urllib.parse import urljoin

import av

from .source_reader import public_target, source_tls_context

MAX_VIDEO_BYTES = 128_000_000
MAX_SHOT_SECONDS = 30
MAX_VIDEO_FRAMES = 1800
MAX_DECODED_PIXELS = 2_000_000_000


class VideoDownloadError(ValueError):
    pass


def inspect_video(raw: bytes):
    try:
        if not 12 <= len(raw) <= MAX_VIDEO_BYTES or raw[4:8] != b"ftyp":
            raise ValueError("not a bounded MP4")
        with av.open(io.BytesIO(raw), format="mp4", options={"protocol_whitelist": "pipe", "enable_drefs": "0"}) as container:
            if len(container.streams.video) != 1:
                raise ValueError("one video stream required")
            stream = container.streams.video[0]
            codec = stream.codec_context
            if codec.name not in {"h264", "hevc", "av1"} or not 0 < codec.width * codec.height <= 4096 * 2160:
                raise ValueError("unsupported video")
            if stream.duration is None or stream.time_base is None:
                raise ValueError("missing duration")
            duration = float(stream.duration * stream.time_base)
            if not math.isfinite(duration) or not 0 < duration <= MAX_SHOT_SECONDS:
                raise ValueError("invalid short-shot duration")
            count, pixels = 0, 0
            first_time = last_time = None
            deadline = time.monotonic() + 45
            for frame in container.decode(stream):
                count += 1
                pixels += frame.width * frame.height
                if (count > MAX_VIDEO_FRAMES or pixels > MAX_DECODED_PIXELS or time.monotonic() > deadline
                        or frame.width != codec.width or frame.height != codec.height or frame.time is None):
                    raise ValueError("decode budget or geometry changed")
                timestamp = float(frame.time)
                if not math.isfinite(timestamp) or (last_time is not None and timestamp <= last_time):
                    raise ValueError("invalid frame timeline")
                if first_time is None:
                    first_time = timestamp
                last_time = timestamp
            if count < 2 or last_time - first_time > MAX_SHOT_SECONDS:
                raise ValueError("not a decodable moving-video sequence")
            # A truncated stream cannot masquerade as the declared duration.
            cadence = (last_time - first_time) / (count - 1)
            if abs((last_time - first_time + cadence) - duration) > max(0.25, cadence * 2):
                raise ValueError("decoded duration differs from container")
            return {"sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                    "width": codec.width, "height": codec.height, "duration_seconds": duration,
                    "decoded_frame_count": count, "codec": codec.name, "extension": "mp4",
                    "visual_semantics_verified": False, "audio_verified": False, "master_accepted": False}
    except Exception:  # noqa: BLE001 -- no private decoder paths/URLs in user-facing errors
        raise VideoDownloadError("result is not a bounded decodable short MP4; production was not retried") from None


def download_video(url: str) -> bytes:
    deadline = time.monotonic() + 120
    try:
        for _ in range(4):
            parsed, ip = public_target(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("deadline")
            connection = http.client.HTTPSConnection(parsed.hostname, timeout=min(15, remaining))
            try:
                raw_socket = socket.create_connection((ip, 443), timeout=min(15, remaining))
                try:
                    connection.sock = source_tls_context().wrap_socket(raw_socket, server_hostname=parsed.hostname)
                except Exception:
                    raw_socket.close()
                    raise
                path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
                connection.request("GET", path, headers={"Accept": "video/mp4,application/octet-stream",
                    "Accept-Encoding": "identity", "User-Agent": "Nalu-VideoReader/1.0"})
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError("invalid redirect")
                    url = urljoin(url, location)
                    continue
                if response.status != 200 or response.getheader("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("invalid response")
                if response.getheader("Content-Type", "").split(";")[0].strip().lower() not in {"video/mp4", "application/octet-stream"}:
                    raise ValueError("invalid media type")
                length = response.getheader("Content-Length")
                if length is not None and not 0 < int(length) <= MAX_VIDEO_BYTES:
                    raise ValueError("result too large")
                raw = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("deadline")
                    if connection.sock is not None:
                        connection.sock.settimeout(min(15, remaining))
                    chunk = response.read(min(64_000, MAX_VIDEO_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_VIDEO_BYTES:
                        raise ValueError("result too large")
                if length is not None and len(raw) != int(length):
                    raise ValueError("incomplete response")
                result = bytes(raw)
                inspect_video(result)
                return result
            finally:
                connection.close()
        raise ValueError("redirect limit")
    except Exception:  # noqa: BLE001 -- signed result URLs and network errors remain private
        raise VideoDownloadError("video result could not be downloaded safely; no generation was retried") from None
