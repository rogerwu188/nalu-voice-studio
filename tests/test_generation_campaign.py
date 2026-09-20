from concurrent.futures import ThreadPoolExecutor

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
