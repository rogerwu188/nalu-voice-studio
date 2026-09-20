import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from nalu_runtime.database import Database
from nalu_runtime.generation_campaign import GenerationCampaign
from nalu_runtime.repository import ConflictError


def ledger(tmp_path):
    db = Database(tmp_path / "campaign.sqlite")
    db.initialize()
    campaign = GenerationCampaign(db)
    campaign.authorize("test", "a" * 64, 10000)
    return campaign


def test_three_media_share_one_allowance_and_restart(tmp_path):
    campaign = ledger(tmp_path)
    for n, media in enumerate(("audio", "image", "video"), 1):
        campaign.reserve("test", str(n) * 64, str(n) * 64, media, 3000, "b" * 64)
    restarted = ledger(tmp_path)
    with pytest.raises(ConflictError, match="aggregate"):
        restarted.reserve("test", "4" * 64, "4" * 64, "audio", 1001, "b" * 64)
    restarted.reserve("test", "4" * 64, "4" * 64, "audio", 1000, "b" * 64)


def test_replay_does_not_resubmit_or_reset_authority(tmp_path):
    campaign = ledger(tmp_path)
    args = ("test", "1" * 64, "2" * 64, "video", 10000, "b" * 64)
    campaign.reserve(*args)
    campaign.claim_dispatch("test", "1" * 64, "2" * 64)
    campaign = ledger(tmp_path)
    campaign.reserve(*args)
    with pytest.raises(ConflictError, match="previously dispatched"):
        campaign.claim_dispatch("test", "1" * 64, "2" * 64)
    with pytest.raises(ConflictError):
        campaign.authorize("test", "a" * 64, 20000)
    with pytest.raises(ConflictError):
        campaign.reserve("test", "3" * 64, "2" * 64, "video", 10000, "b" * 64)


def test_parallel_reservations_cannot_overspend(tmp_path):
    campaign = ledger(tmp_path)

    def reserve(n):
        try:
            campaign.reserve("test", str(n) * 64, str(n) * 64, "image", 6000, "b" * 64)
            return True
        except ConflictError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve, (1, 2))) == 1


@pytest.mark.parametrize("cost", [True, 0, -1, 1.5])
def test_invalid_cost_rejected(tmp_path, cost):
    with pytest.raises(ConflictError):
        ledger(tmp_path).reserve("test", "1" * 64, "2" * 64, "audio", cost, "b" * 64)


@pytest.mark.parametrize("outcome", ["success", "timeout", "wrong_media", "changed_request"])
def test_image_network_boundary_consumes_exact_reservation_once(tmp_path, outcome):
    from nalu_runtime.giggle_image_transport import ImageAcceptanceUnconfirmed, image_payload

    campaign = ledger(tmp_path)
    request = {"prompt": "A quiet garden", "model": "gpt-image-2-pro", "resolution": "1K",
               "aspect_ratio": "1:1", "generate_count": 1, "watermark": False}
    endpoint, payload = image_payload(request)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(endpoint.encode() + b"\0" + raw).hexdigest()
    campaign.reserve("test", "1" * 64, digest,
                     "audio" if outcome == "wrong_media" else "image", 100, "b" * 64)
    posts = []

    def provider(incoming):
        posts.append(incoming)
        if outcome == "timeout":
            raise httpx.ReadTimeout("ambiguous")
        return httpx.Response(200, json={"code": 200, "data": {"task_id": "test-task"}})

    adapter = campaign.image_transport("test", lambda: "fixture-secret",
                                       transport=httpx.MockTransport(provider))
    if outcome == "changed_request":
        request["prompt"] = "A different garden"
    if outcome in {"wrong_media", "changed_request"}:
        with pytest.raises(ConflictError):
            adapter.submit(request, intent_id="1" * 64)
        assert not posts
        return
    if outcome == "timeout":
        with pytest.raises(ImageAcceptanceUnconfirmed):
            adapter.submit(request, intent_id="1" * 64)
    else:
        assert campaign.submit_image("test", lambda: "fixture-secret", request, "1" * 64,
            transport=httpx.MockTransport(provider))["provider_task_id"] == "test-task"
        assert ledger(tmp_path).accepted_task("test", "1" * 64)["provider_task_id"] == "test-task"
    restarted = ledger(tmp_path).image_transport("test", lambda: "fixture-secret",
                                                transport=httpx.MockTransport(provider))
    with pytest.raises(ConflictError):
        restarted.submit(request, intent_id="1" * 64)
    assert len(posts) == 1


def test_acceptance_is_write_once_and_campaign_scoped(tmp_path):
    campaign = ledger(tmp_path)
    campaign.reserve("test", "1" * 64, "2" * 64, "audio", 100, "b" * 64)
    with pytest.raises(ConflictError):
        campaign.record_acceptance("test", "1" * 64, "task", "c" * 64)
    campaign.claim_dispatch("test", "1" * 64, "2" * 64)
    campaign.record_acceptance("test", "1" * 64, "task", "c" * 64)
    campaign.record_acceptance("test", "1" * 64, "task", "c" * 64)
    assert campaign.accepted_task("other", "1" * 64) is None
    with pytest.raises(ConflictError):
        campaign.record_acceptance("test", "1" * 64, "different-task", "c" * 64)
    with pytest.raises(ConflictError):
        campaign.record_acceptance("test", "1" * 64, "task", "d" * 64)


def test_video_campaign_claim_matches_wire_bytes_and_prevents_replay(tmp_path):
    from nalu_runtime.giggle_video_transport import (
        GiggleSeedanceImageTransport,
        seedance_image_payload,
    )
    from test_giggle_video_transport import request_fixture

    campaign = ledger(tmp_path)
    request = request_fixture()
    payload = seedance_image_payload(request)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(GiggleSeedanceImageTransport.endpoint.encode() + b"\0" + raw).hexdigest()
    campaign.reserve("test", "5" * 64, digest, "video", 130, "b" * 64)
    posts = []

    def provider(incoming):
        assert incoming.content == raw
        posts.append(incoming)
        return httpx.Response(200, json={"code": 200, "data": {"task_id": "video-test"}})

    adapter = campaign.video_transport("test", lambda: "fixture-secret",
                                       transport=httpx.MockTransport(provider))
    assert adapter.post_paid_task(request=request, idempotency_key="5" * 64).provider_task_id == "video-test"
    with pytest.raises(ConflictError):
        adapter.post_paid_task(request=request, idempotency_key="5" * 64)
    assert len(posts) == 1
