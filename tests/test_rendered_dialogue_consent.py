import json
from types import SimpleNamespace as NS

import pytest
from nalu_runtime.postproduction_materializer import canonical_sha256
from nalu_runtime.rendered_dialogue_consent import validate_rendered_dialogue_consent
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_preparation import digest


@pytest.fixture
def rendered(tmp_path):
    take = {"asset_id": "audio", "expected_asset_sha256": "a" * 64, "consent_record_id": "grant"}
    take["take_sha256"] = digest(take)
    staged = {"lineage": {"sources": [{"take_id": "take", "take_sha256": take["take_sha256"]}]}}
    staged["staging_sha256"] = digest(staged)
    plan = {"run_id": "run", "request": {"adopted_dialogue_staging_id": "stage",
            "expected_dialogue_staging_sha256": staged["staging_sha256"]}}
    plan["plan_sha256"] = canonical_sha256(plan)
    package = tmp_path / "runs/run/production-package.json"
    path = package.parent / "qingshan-workspace/exports/materialized" / plan["plan_sha256"] / "materialization-plan.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(plan))
    asset = NS(id="audio", project_id="project", consent_granted=True, kind="archive_audio",
               metadata={"sha256": "a" * 64}, episode_id=None, season_id=None, guardian_approved=True)
    project = NS(archived_at=None, audience_mode="child")
    grant = NS(id="grant", action_type="granted")
    events = {"take": NS(run_id="run", event_type="episode_audio_take_attached", payload=take),
              "stage": NS(run_id="run", event_type="episode_dialogue_staged", payload=staged)}
    repo = NS(list_run_events=lambda _: [NS(event_type="postproduction_materialized", payload={"plan_sha256": plan["plan_sha256"]})],
              get_run=lambda _: NS(package_path=str(package), project_id="project", episode_id="episode"),
              get_run_event=events.__getitem__, get_project=lambda _: project,
              get_episode=lambda _: NS(id="episode", season_id="season"), get_asset=lambda _: asset,
              list_asset_consent_records=lambda _: [grant])
    return repo, tmp_path, asset, project, grant, path


def test_original_grant_remains_valid_after_render(rendered):
    repo, root, *_ = rendered
    validate_rendered_dialogue_consent(repo, root, "run")


@pytest.mark.parametrize("change", ["revoked", "regranted", "guardian", "hash", "scope", "archived", "plan"])
def test_rendered_lineage_requires_original_live_authorization(rendered, change):
    repo, root, asset, project, grant, path = rendered
    if change == "revoked":
        grant.action_type = "revoked"
    elif change == "regranted":
        grant.id = "different-grant"
    elif change == "guardian":
        asset.guardian_approved = False
    elif change == "hash":
        asset.metadata["sha256"] = "b" * 64
    elif change == "scope":
        asset.episode_id = "other-episode"
    elif change == "archived":
        project.archived_at = "now"
    elif change == "plan":
        path.write_text("{}")
    with pytest.raises(ConflictError):
        validate_rendered_dialogue_consent(repo, root, "run")
