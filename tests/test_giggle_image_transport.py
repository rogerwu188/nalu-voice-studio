import base64
import hashlib
import json

import httpx
import pytest
from nalu_runtime.giggle_image_transport import (
    GiggleImageTransport,
    ImageAcceptanceUnconfirmed,
    image_payload,
)
from nalu_runtime.repository import ConflictError


def request():
    return {"prompt": "合成首帧：空房间的窗前，一束晨光。", "model": "gpt-image-2-pro",
            "resolution": "1K", "aspect_ratio": "16:9", "generate_count": 1, "watermark": False}


@pytest.mark.parametrize("mode", ["text", "reference", "unauthorized", "http_error", "missing_id", "secret_echo", "duplicate_json", "redirect"])
def test_fixed_image_transport_has_mandatory_authority_and_no_retry(mode):
    payload = request()
    if mode == "reference":
        # Only the transport signature check, not a decoded-image or consent fixture.
        payload["reference_images"] = [{"base64": base64.b64encode(b"\x89PNG\r\n\x1a\nfixture").decode()}]
    posts, approvals = [], []
    def authorize(intent, digest):
        approvals.append((intent, digest))
        if mode == "unauthorized":
            raise ConflictError("no reviewed image request")
    def provider(incoming):
        posts.append(incoming)
        assert len(approvals) == 1
        assert incoming.headers["x-auth"] == "synthetic-image-secret"
        assert incoming.url.host == "giggle.pro"
        assert incoming.url.path.endswith("image-to-image" if mode == "reference" else "text-to-image")
        assert hashlib.sha256(str(incoming.url).encode() + b"\0" + incoming.content).hexdigest() == approvals[0][1]
        assert json.loads(incoming.content)["generate_count"] == 1
        if mode == "redirect":
            return httpx.Response(307, headers={"Location": "https://untrusted.invalid"})
        if mode == "duplicate_json":
            return httpx.Response(200, content=b'{"code":200,"code":200,"data":{"task_id":"abc"}}')
        return httpx.Response(500 if mode == "http_error" else 200,
            json={"code": 200, "data": {"task_id": None if mode == "missing_id" else "synthetic-image-task"},
                  "message": "synthetic-image-secret" if mode == "secret_echo" else "ok"})
    transport = GiggleImageTransport(lambda: "synthetic-image-secret", authorize=authorize,
                                     transport=httpx.MockTransport(provider))
    if mode == "unauthorized":
        with pytest.raises(ConflictError):
            transport.submit(payload, intent_id="a" * 64)
        assert not posts
    elif mode in {"text", "reference"}:
        result = transport.submit(payload, intent_id="a" * 64)
        assert result["provider_task_id"] == "synthetic-image-task"
        assert result["image_generated"] is False and result["billing_verified"] is False
        assert "synthetic-image-secret" not in json.dumps(result)
        assert len(posts) == 1
    else:
        with pytest.raises(ImageAcceptanceUnconfirmed) as error:
            transport.submit(payload, intent_id="a" * 64)
        assert "synthetic-image-secret" not in str(error.value)
        assert len(posts) == 1


@pytest.mark.parametrize("patch", [{"generate_count": 2}, {"generate_count": True}, {"model": "unreviewed-model"},
                                  {"prompt": " "}, {"resolution": "4K"}, {"reference_images": [{"url": "https://invalid"}]},
                                  {"reference_images": [{"base64": "invalid"}]}, {"authority": True}])
def test_unsupported_image_payload_is_rejected_locally(patch):
    with pytest.raises(ConflictError):
        image_payload({**request(), **patch})
