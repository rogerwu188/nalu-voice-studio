import io
from types import SimpleNamespace

import av
import numpy as np
import pytest
from nalu_runtime import video_download


def mp4(frames=12, rate=12):
    output = io.BytesIO()
    with av.open(output, "w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=rate)
        stream.width, stream.height, stream.pix_fmt = 32, 32, "yuv420p"
        for index in range(frames):
            frame = av.VideoFrame.from_ndarray(np.full((32, 32, 3), index % 255, dtype=np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return output.getvalue()


def motion_mp4(frames=24, rate=24):
    """Deterministic changing pixels for technical QA, not narrative footage."""
    output = io.BytesIO()
    rng = np.random.default_rng(42)
    with av.open(output, "w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=rate)
        stream.width, stream.height, stream.pix_fmt = 32, 32, "yuv420p"
        for _ in range(frames):
            pixels = rng.integers(40, 220, size=(32, 32, 3), dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return output.getvalue()


def test_video_inspection_is_decoding_not_creative_or_audio_acceptance():
    report = video_download.inspect_video(mp4())
    assert report["width"] == report["height"] == 32
    assert report["decoded_frame_count"] == 12
    assert report["duration_seconds"] == 1
    assert report["extension"] == "mp4" and len(report["sha256"]) == 64
    assert not report["master_accepted"] and not report["visual_semantics_verified"] and not report["audio_verified"]


@pytest.mark.parametrize("case", ["html", "truncated", "single_frame", "too_long", "frame_budget", "pixel_budget"])
def test_invalid_or_over_budget_media_is_rejected(monkeypatch, case):
    raw = mp4()
    if case == "html":
        raw = b"<html>provider error with private details</html>"
    elif case == "truncated":
        raw = raw[:len(raw) // 2]
    elif case == "single_frame":
        raw = mp4(frames=1)
    elif case == "too_long":
        raw = mp4(frames=31, rate=1)
    elif case == "frame_budget":
        monkeypatch.setattr(video_download, "MAX_VIDEO_FRAMES", 3)
    elif case == "pixel_budget":
        monkeypatch.setattr(video_download, "MAX_DECODED_PIXELS", 100)
    with pytest.raises(video_download.VideoDownloadError) as error:
        video_download.inspect_video(raw)
    assert "private details" not in str(error.value)


@pytest.mark.parametrize("case", ["ok", "binary", "private_redirect", "too_large", "html", "bad_video", "encoding", "incomplete"])
def test_video_download_pins_each_public_target_and_never_sends_credentials(monkeypatch, case):
    calls, closed, targets = [], [], []
    def public(url):
        targets.append(url)
        if "127.0.0.1" in url:
            raise ValueError("private address")
        return SimpleNamespace(hostname="example.org", path="/video", query="signed=private-fixture"), "93.184.216.34"
    monkeypatch.setattr(video_download, "public_target", public)
    monkeypatch.setattr(video_download.socket, "create_connection", lambda target, **kwargs: (
        calls.append(target) or SimpleNamespace(close=lambda: None, settimeout=lambda _: None)))
    monkeypatch.setattr(video_download, "source_tls_context", lambda: SimpleNamespace(wrap_socket=lambda sock, **kwargs: sock))
    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "example.org"
        def request(self, method, path, headers):
            assert method == "GET" and path == "/video?signed=private-fixture"
            assert set(headers) == {"Accept", "Accept-Encoding", "User-Agent"}
        def getresponse(self):
            raw = b"invalid" if case == "bad_video" else mp4()
            body = io.BytesIO(raw)
            headers = {"Content-Type": "text/html" if case == "html" else
                       ("application/octet-stream" if case == "binary" else "video/mp4")}
            if case == "too_large":
                headers["Content-Length"] = str(video_download.MAX_VIDEO_BYTES + 1)
            if case == "incomplete":
                headers["Content-Length"] = str(len(raw) + 1)
            if case == "encoding":
                headers["Content-Encoding"] = "gzip"
            if case == "private_redirect":
                headers["Location"] = "https://127.0.0.1/video"
            return SimpleNamespace(status=302 if case == "private_redirect" else 200,
                getheader=lambda key, default=None: headers.get(key, default), read=body.read)
        def close(self):
            closed.append(True)
    monkeypatch.setattr(video_download.http.client, "HTTPSConnection", Connection)
    if case in {"ok", "binary"}:
        assert video_download.inspect_video(video_download.download_video("https://example.org/video"))["decoded_frame_count"] == 12
    else:
        with pytest.raises(video_download.VideoDownloadError) as error:
            video_download.download_video("https://example.org/video")
        assert "private-fixture" not in str(error.value)
    assert calls == [("93.184.216.34", 443)] and len(closed) == 1
    if case == "private_redirect":
        assert len(targets) == 2
