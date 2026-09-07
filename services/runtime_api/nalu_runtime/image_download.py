"""Fetch public image results without provider credentials or internal network access."""

import hashlib
import http.client
import io
import socket
import time
from urllib.parse import urljoin

import av

from .source_reader import public_target, source_tls_context

MAX_IMAGE_BYTES = 15_000_000


class ImageDownloadError(ValueError):
    pass


def inspect_image(raw: bytes):
    try:
        if not raw or len(raw) > MAX_IMAGE_BYTES or not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
            raise ValueError("unsupported image")
        with av.open(io.BytesIO(raw)) as image:
            stream = image.streams.video[0]
            codec = stream.codec_context
            if codec.name not in {"png", "mjpeg"} or not 0 < codec.width * codec.height <= 16_000_000:
                raise ValueError("unsupported image dimensions")
            frame = next(image.decode(stream))
            frame.to_ndarray(format="rgb24")
            return {"sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                    "width": frame.width, "height": frame.height,
                    "extension": "png" if codec.name == "png" else "jpg"}
    except Exception:  # noqa: BLE001 -- decoder diagnostics can contain private media details
        raise ImageDownloadError("result is not a bounded decodable PNG or JPEG") from None


def download_image(url: str) -> bytes:
    deadline = time.monotonic() + 45
    try:
        for _ in range(4):
            parsed, ip = public_target(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("deadline")
            connection = http.client.HTTPSConnection(parsed.hostname, timeout=min(12, remaining))
            try:
                raw_socket = socket.create_connection((ip, 443), timeout=min(12, remaining))
                try:
                    connection.sock = source_tls_context().wrap_socket(raw_socket, server_hostname=parsed.hostname)
                except Exception:
                    raw_socket.close()
                    raise
                path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
                connection.request("GET", path, headers={"Accept": "image/png,image/jpeg",
                    "Accept-Encoding": "identity", "User-Agent": "Nalu-ImageReader/1.0"})
                response = connection.getresponse()
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    if not location:
                        raise ValueError("invalid redirect")
                    url = urljoin(url, location)
                    continue  # Every hop revalidates DNS and pins the public destination.
                if response.status != 200 or response.getheader("Content-Encoding", "identity").lower() != "identity":
                    raise ValueError("invalid response")
                if response.getheader("Content-Type", "").split(";")[0].strip().lower() not in {"image/png", "image/jpeg"}:
                    raise ValueError("not an image response")
                length = response.getheader("Content-Length")
                if length is not None and not 0 < int(length) <= MAX_IMAGE_BYTES:
                    raise ValueError("image too large")
                raw = bytearray()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ValueError("deadline")
                    if connection.sock is not None:
                        connection.sock.settimeout(min(12, remaining))
                    chunk = response.read(min(64_000, MAX_IMAGE_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if len(raw) > MAX_IMAGE_BYTES:
                        raise ValueError("image too large")
                inspect_image(bytes(raw))
                return bytes(raw)
            finally:
                connection.close()
        raise ValueError("redirect limit")
    except Exception:  # noqa: BLE001 -- don't expose signed URLs or network diagnostics
        raise ImageDownloadError("image result could not be downloaded safely; no generation was retried") from None
