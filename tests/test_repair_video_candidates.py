from types import SimpleNamespace

import pytest

from nalu_runtime.repair_video_candidates import same_referenced_assets
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_preparation import VideoPreparationService


def test_reuse_compares_exact_references_not_unrelated_uploads():
    shot = SimpleNamespace(reference_asset_ids=["photo"])
    old = [{"id": "photo", "sha256": "old"}]
    assert same_referenced_assets(shot, old, old + [{"id": "new-music"}])
    assert not same_referenced_assets(shot, old, [{"id": "photo", "sha256": "new"}])
    assert not same_referenced_assets(shot, old, [])
    assert not same_referenced_assets(shot, old, old + old)
    assert not same_referenced_assets(shot, [], [])
    assert same_referenced_assets(SimpleNamespace(reference_asset_ids=[]), [], [{"id": "music"}])


@pytest.mark.parametrize("read_saved,target", [(False, "child"), (True, None), (True, "unrelated")])
def test_historical_access_cannot_authorize_preparation(tmp_path, read_saved, target):
    parent = SimpleNamespace(id="parent", project_id="p", episode_id="e", status="qa_review")
    repo = SimpleNamespace(get_run=lambda _: parent,
                           get_project=lambda _: SimpleNamespace(archived_at=None),
                           latest_run_for_episode=lambda _: SimpleNamespace(id="child"))
    with pytest.raises(ConflictError):
        VideoPreparationService(repo, tmp_path).validate(
            "parent", None, _read_saved=read_saved, _repair_target=target)
