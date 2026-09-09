from types import SimpleNamespace

import pytest
from nalu_runtime.repair_video_candidates import same_referenced_assets
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_preparation import VideoPreparationService
from nalu_runtime.video_tail import VideoTailService


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


def test_saved_tail_preserves_repair_scope_and_exact_receipt(tmp_path, monkeypatch):
    event = SimpleNamespace(run_id="parent", event_type="video_tail_extracted",
                            payload={"review_id": "review"})
    service = VideoTailService(SimpleNamespace(get_run_event=lambda _: event), tmp_path)
    calls = []

    def derive(run_id, review_id, *, _repair_target=None):
        calls.append((run_id, review_id, _repair_target))
        return dict(event.payload), b"png"

    monkeypatch.setattr(service, "_derive", derive)
    assert service.read_saved("parent", "tail", _repair_target="child") == (event, b"png")
    assert calls == [("parent", "review", "child")]
    with pytest.raises(ConflictError):
        service.read_saved("another", "tail", _repair_target="child")
    assert len(calls) == 1
    monkeypatch.setattr(service, "_derive", lambda *args, **kwargs: ({"changed": True}, b"png"))
    with pytest.raises(ConflictError):
        service.read_saved("parent", "tail", _repair_target="child")
