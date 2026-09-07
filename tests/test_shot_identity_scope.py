from copy import deepcopy

import pytest
from nalu_runtime.repository import ConflictError
from nalu_runtime.shot_identity_scope import compile_identity_scope
from nalu_runtime.video_preparation import digest


def character(identity, name, assets=None):
    return {"entity_id": identity, "kind": "character", "stable_name": name, "confirmed_revision": 1,
            "revision": {"entity_id": identity, "revision": 1, "name": name, "source_asset_ids": assets or []}}


@pytest.mark.parametrize("case", ["ok", "photo", "missing", "ambiguous", "count", "tampered", "unconfirmed", "duplicate", "malformed"])
def test_reviewed_people_resolve_to_sealed_project_identities(case):
    package = {"resolved_library": [character("person-grandma", "外婆", ["photo-1"]), character("person-son", "儿子")]}
    plan = {"visual_assets": [{"key": "grandma", "kind": "character_image", "name": "外婆", "existing_asset_id": None}]}
    shot = {"visual_asset_keys": ["grandma"], "director": {"visible_character_counts": {"grandma": 1}, "props": []}}
    if case == "photo":
        plan["visual_assets"][0].update(name="老照片里的她", existing_asset_id="photo-1")
    if case == "missing":
        package["resolved_library"] = []
    if case == "ambiguous":
        package["resolved_library"].append(character("different-grandma", "外婆"))
    if case == "count":
        shot["director"]["visible_character_counts"]["grandma"] = 2
    if case == "unconfirmed":
        package["resolved_library"][0]["confirmed_revision"] = None
    if case == "duplicate":
        plan["visual_assets"].append({**plan["visual_assets"][0], "key": "grandma-again"})
        shot["visual_asset_keys"].append("grandma-again")
        shot["director"]["visible_character_counts"]["grandma-again"] = 1
    if case == "malformed":
        package["resolved_library"].append(None)
    package["package_sha256"] = digest(package)
    if case == "tampered":
        package["resolved_library"].clear()
    before = deepcopy(package)
    if case not in {"ok", "photo"}:
        with pytest.raises(ConflictError):
            compile_identity_scope(plan, shot, package, package["package_sha256"])
    else:
        result = compile_identity_scope(plan, shot, package, package["package_sha256"])
        assert result["visible_character_ids"] == ["person-grandma"]
        assert result["visible_living_entity_instance_total"] == 1
        assert result["absent_episode_entities"] == [{"entity_id": "person-son", "forbidden_provider_terms": ["儿子"]}]
        assert result["episode_character_catalog_sha256"] == digest(["person-grandma", "person-son"])
        assert result["reference_identity_bindings"] == []  # No invented uploaded reference index.
    assert package == before
