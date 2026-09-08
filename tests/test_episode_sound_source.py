import hashlib
from types import SimpleNamespace as NS

import pytest
from nalu_runtime.episode_sound_source import EpisodeSoundSourceRequest, EpisodeSoundSourceService
from nalu_runtime.repository import ConflictError


@pytest.mark.parametrize("change", [None, "foreign", "scope", "revoked", "regranted", "child", "archived", "hash", "symlink"])
def test_sound_asset_binding_requires_live_exact_authorization(tmp_path, change):
    path = tmp_path / "assets/project/source.wav"
    path.parent.mkdir(parents=True)
    raw = b"file identity fixture; decode is tested in the full render fixture"
    path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    asset = NS(id="asset", project_id="project", kind="archive_audio", consent_granted=True,
               episode_id=None, season_id=None, guardian_approved=True, local_uri=path.as_uri(), metadata={"sha256": sha})
    project = NS(id="project", audience_mode="child", archived_at=None)
    consent = NS(id="grant", action_type="granted", statement="fixture consent", recorded_by="qa")
    repo = NS(get_project=lambda _: project, get_episode=lambda _: NS(id="episode", season_id="season"),
              get_asset=lambda _: asset, list_asset_consent_records=lambda _: [consent])
    run = NS(project_id="project", episode_id="episode")
    request = EpisodeSoundSourceRequest(sound_plan_id="sound", expected_sound_plan_sha256=sha,
                                       layer="music", asset_id="asset", expected_asset_sha256=sha)
    if change == "foreign":
        asset.project_id = "other"
    elif change == "scope":
        asset.episode_id = "other"
    elif change == "revoked":
        consent.action_type = "revoked"
    elif change == "regranted":
        consent.id = "new-grant"
    elif change == "child":
        asset.guardian_approved = False
    elif change == "archived":
        project.archived_at = "now"
    elif change == "hash":
        path.write_bytes(b"changed")
    elif change == "symlink":
        link = path.parent / "alias.wav"
        link.symlink_to(path)
        asset.local_uri = link.as_uri()
    service = EpisodeSoundSourceService(repo, tmp_path)
    if change is None:
        assert service.asset_source(run, request, "grant") == (path, raw, "grant")
    else:
        with pytest.raises(ConflictError):
            service.asset_source(run, request, "grant")


@pytest.mark.parametrize("field,value", [("layer", "dialogue"), ("gain_db", float("nan")),
    ("source_in_seconds", float("inf")), ("source_in_seconds", -1), ("gain_db", 13)])
def test_sound_source_request_cannot_bypass_existing_dialogue_or_numeric_limits(field, value):
    request = {"sound_plan_id": "sound", "expected_sound_plan_sha256": "a" * 64,
               "layer": "music", "asset_id": "asset", "expected_asset_sha256": "a" * 64}
    with pytest.raises(ValueError):
        EpisodeSoundSourceRequest(**{**request, field: value})
