import base64
import hashlib
import json

import httpx
import pytest
from nalu_runtime.giggle_video_transport import GiggleSeedanceImageTransport, seedance_image_payload
from nalu_runtime.remote_submitter import AmbiguousPaidProviderResponse
from nalu_runtime.repository import ConflictError


def request_fixture():
    frame = b"synthetic-frame-bytes-not-a-real-image"
    return {"model": "seedance-2.0-pro", "provider_model_id": "seedance-2.0-pro",
            "prompt": "合成测试，海浪拍岸。", "duration_seconds": 5,
            "native_resolution_contract": "720p", "delivery_resolution_contract": "720p",
            "opening_anchor": {"frame_sha256": hashlib.sha256(frame).hexdigest()},
            "video_transport": {"mode": "image_to_video_start_frame", "aspect_ratio": "16:9",
                                "start_frame": {"base64": base64.b64encode(frame).decode()}}}


def test_exact_sd2_payload_and_safe_acceptance():
    calls = []
    def serve(request):
        calls.append(request)
        assert str(request.url) == GiggleSeedanceImageTransport.endpoint
        assert request.headers["x-auth"] == "synthetic-secret"
        payload = json.loads(request.content)
        assert payload["prompt"] == request_fixture()["prompt"]
        assert payload["duration"] == 5
        assert payload["generating_count"] == 1
        assert payload["resolution"] == "720p"
        return httpx.Response(200, json={"code": 200, "data": {"task_id": "synthetic-task"}, "extra": "synthetic-secret"})
    transport = GiggleSeedanceImageTransport(lambda: "synthetic-secret", transport=httpx.MockTransport(serve))
    result = transport.post_paid_task(request=request_fixture(), idempotency_key="a" * 64)
    assert result.provider_task_id == "synthetic-task"
    assert "synthetic-secret" not in str(result.receipt)
    assert len(calls) == 1
    assert transport.requires_single_attempt and not transport.supports_idempotency


@pytest.mark.parametrize("patch", [
    {"duration_seconds": 5.5}, {"model": "MiniMax-H3"},
    {"opening_anchor": {"frame_sha256": "0" * 64}},
    {"images": [{"url": "https://example.org/extra.png"}]},
    {"native_resolution_contract": "1080p"},
])
def test_approved_contract_cannot_be_silently_changed(patch):
    with pytest.raises(ConflictError):
        seedance_image_payload({**request_fixture(), **patch})


@pytest.mark.parametrize("status,body", [(302, {}), (401, {"secret": "hidden"}),
    (200, {"code": 200, "data": {}}), (200, {"code": 500})])
def test_unconfirmed_acceptance_is_not_retried_or_leaked(status, body):
    calls = []
    def serve(request):
        calls.append(request)
        return httpx.Response(status, json=body, headers={"Location": "https://untrusted.invalid"})
    transport = GiggleSeedanceImageTransport(lambda: "hidden", transport=httpx.MockTransport(serve))
    with pytest.raises(AmbiguousPaidProviderResponse) as error:
        transport.post_paid_task(request=request_fixture(), idempotency_key="a" * 64)
    assert "hidden" not in str(error.value)
    assert len(calls) == 1
