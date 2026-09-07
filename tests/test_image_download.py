import io
from types import SimpleNamespace

import av
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from nalu_runtime import image_download
from nalu_runtime.app import create_app
from nalu_runtime.giggle_task_query import GiggleTaskObservation
from nalu_runtime.image_observation import ImageObservationService
from nalu_runtime.image_submission import ImageSubmissionService
from test_giggle_image_transport import request
from test_paid_submitter_boundary import paid_run


def png():
    output = io.BytesIO()
    with av.open(output, "w", format="image2pipe") as container:
        stream = container.add_stream("png", rate=1)
        stream.width, stream.height, stream.pix_fmt = 16, 16, "rgb24"
        frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    return output.getvalue()


@pytest.mark.parametrize("case", ["ok", "private_redirect", "too_large", "html", "bad_image", "encoding"])
def test_image_download_pins_public_host_and_sends_no_key(monkeypatch, case):
    calls, closed, targets = [], [], []
    def public(url):
        targets.append(url)
        if "127.0.0.1" in url:
            raise ValueError("private address")
        return SimpleNamespace(hostname="example.org", path="/image", query="signed=fixture"), "93.184.216.34"
    monkeypatch.setattr(image_download, "public_target", public)
    monkeypatch.setattr(image_download.socket, "create_connection", lambda target, **kwargs: (
        calls.append(target) or SimpleNamespace(close=lambda: None, settimeout=lambda _: None)))
    monkeypatch.setattr(image_download, "source_tls_context", lambda: SimpleNamespace(wrap_socket=lambda sock, **kwargs: sock))
    class Connection:
        def __init__(self, host, **kwargs):
            assert host == "example.org"
        def request(self, method, path, headers):
            assert method == "GET" and path == "/image?signed=fixture"
            assert set(headers) == {"Accept", "Accept-Encoding", "User-Agent"}
        def getresponse(self):
            body = io.BytesIO(b"invalid" if case == "bad_image" else png())
            headers = {"Content-Type": "text/html" if case == "html" else "image/png"}
            if case == "too_large":
                headers["Content-Length"] = str(image_download.MAX_IMAGE_BYTES + 1)
            if case == "encoding":
                headers["Content-Encoding"] = "gzip"
            if case == "private_redirect":
                headers["Location"] = "https://127.0.0.1/image"
            return SimpleNamespace(status=302 if case == "private_redirect" else 200,
                getheader=lambda key, default=None: headers.get(key, default), read=body.read)
        def close(self):
            closed.append(True)
    monkeypatch.setattr(image_download.http.client, "HTTPSConnection", Connection)
    if case == "ok":
        assert image_download.inspect_image(image_download.download_image("https://example.org/image"))["width"] == 16
    else:
        with pytest.raises(image_download.ImageDownloadError):
            image_download.download_image("https://example.org/image")
    assert calls == [("93.184.216.34", 443)] and len(closed) == 1
    if case == "private_redirect":
        assert len(targets) == 2


@pytest.mark.parametrize("case", ["ok", "corrupt_saved", "pending", "invalid_index", "archived", "download_error"])
def test_observed_image_materializes_once_and_survives_restart(tmp_path, monkeypatch, case):
    db_path, root = tmp_path / "db", tmp_path / "data"
    api = TestClient(create_app(db_path, root))
    repo = api.app.state.repository
    run = paid_run(api, tmp_path, run_id="run_materialize", model="seedance-2.0-pro")
    binding = ImageSubmissionService(repo).submit(run.id, "E01-U01-entry", request(), secret=lambda: "synthetic-key",
        authorize=lambda *args: None, transport=httpx.MockTransport(lambda _: httpx.Response(200,
            json={"code": 200, "data": {"task_id": "fixture-task"}})))
    observation = ImageObservationService(repo).refresh(run.id, binding.id, SimpleNamespace(query=lambda _: GiggleTaskObservation(
        "fixture-task", "pending" if case == "pending" else "completed", ("https://example.org/image.png",), "0" * 64)))
    downloads = []
    def download(url):
        downloads.append(url)
        if case == "download_error":
            raise image_download.ImageDownloadError("safe fixture error")
        return png()
    monkeypatch.setattr("nalu_runtime.image_materialization.download_image", download)
    if case == "archived":
        with repo.db.connect() as db:
            db.execute("UPDATE projects SET archived_at='2026-09-07' WHERE id=?", (run.project_id,))
    endpoint = f"/v1/production-runs/{run.id}/image-observations/{observation.id}/materialize"
    assert api.post(endpoint, headers={"Origin": "https://example.org"}).status_code == 403
    result = api.post(endpoint, params={"result_index": 3 if case == "invalid_index" else 0})
    if case in {"pending", "invalid_index", "archived", "download_error"}:
        assert result.status_code == (502 if case == "download_error" else 409), result.text
        assert len(downloads) == (1 if case == "download_error" else 0)
        return
    assert result.status_code == 200, result.text
    record = result.json()["payload"]
    assert record["image_downloaded"] is True and record["visual_semantics_verified"] is False
    assert record["billing_verified"] is False and record["master_accepted"] is False
    path = root / "runs" / run.id / "generated-images" / record["filename"]
    assert path.read_bytes() == png() and path.stat().st_mode & 0o777 == 0o600
    assert not list(path.parent.glob(".image-*"))
    if case == "corrupt_saved":
        path.write_bytes(b"changed")
    reopened = TestClient(create_app(db_path, root))
    second = reopened.post(endpoint)
    if case == "corrupt_saved":
        assert second.status_code == 409
    else:
        assert second.json()["id"] == result.json()["id"]
    assert len(downloads) == 1
