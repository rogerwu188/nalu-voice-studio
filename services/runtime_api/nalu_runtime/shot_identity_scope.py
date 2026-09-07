"""Resolve reviewed shot characters against the sealed, confirmed project catalog."""

from .qingshan_compilers import PROVIDER_SCOPE_SCHEMA, _canonical_sha256
from .repository import ConflictError


def compile_identity_scope(plan: dict, shot: dict, package: dict, package_sha: str) -> dict:
    if (package.get("package_sha256") != package_sha
            or _canonical_sha256({k: v for k, v in package.items() if k != "package_sha256"}) != package_sha):
        raise ConflictError("character scope requires the intact production package")
    library = package.get("resolved_library")
    if not isinstance(library, list) or any(not isinstance(row, dict) for row in library):
        raise ConflictError("production package needs its confirmed character catalog")
    characters = [row for row in library if isinstance(row, dict) and row.get("kind") == "character"]
    ids = [row.get("entity_id") for row in characters]
    if any(not isinstance(identity, str) or not identity for identity in ids) or len(ids) != len(set(ids)):
        raise ConflictError("confirmed character catalog has invalid identities")
    if any(type(row.get("confirmed_revision")) is not int or row["confirmed_revision"] < 1
           or not isinstance(row.get("revision"), dict)
           or row["revision"].get("entity_id") != row["entity_id"]
           or row["revision"].get("revision") != row["confirmed_revision"]
           or not isinstance(row["revision"].get("source_asset_ids", []), list) for row in characters):
        raise ConflictError("character catalog is missing confirmed revision bindings")
    selected = set(shot.get("visual_asset_keys", []))
    designs = [item for item in plan.get("visual_assets", [])
               if item.get("kind") == "character_image" and item.get("key") in selected]
    counts = (shot.get("director") or {}).get("visible_character_counts", {})
    if set(counts) != {item["key"] for item in designs}:
        raise ConflictError("shot character count differs from its reviewed designs")
    visible = []
    for design in designs:
        candidates = []
        for entity in characters:
            revision = entity.get("revision") or {}
            names = {entity.get("stable_name"), revision.get("name")}
            linked = design.get("existing_asset_id")
            if design.get("name") in names or (linked and linked in revision.get("source_asset_ids", [])):
                candidates.append(entity["entity_id"])
        if len(candidates) != 1:
            raise ConflictError("shot character needs unambiguous confirmed project identity: " + design["name"])
        if type(counts[design["key"]]) is not int or counts[design["key"]] != 1:
            raise ConflictError("multiple instances require separate confirmed character identities; do not drop people")
        if candidates[0] in visible:
            raise ConflictError("two shot designs resolve to the same character; reconcile before production")
        visible.append(candidates[0])
    absent = []
    for entity in characters:
        if entity["entity_id"] in visible:
            continue
        revision = entity.get("revision") or {}
        terms = sorted({term for term in (entity.get("stable_name"), revision.get("name"))
                        if isinstance(term, str) and term.strip()})
        absent.append({"entity_id": entity["entity_id"], "forbidden_provider_terms": terms})
    props = [prop["design_key"] for prop in (shot.get("director") or {}).get("props", [])]
    return {"schema_version": PROVIDER_SCOPE_SCHEMA, "status": "LOCKED",
            "production_package_sha256": package_sha, "episode_character_catalog_sha256": _canonical_sha256(sorted(ids)),
            "visible_character_ids": visible, "visible_entity_instance_counts": dict.fromkeys(visible, 1),
            "exclusive_visible_living_entity_set": True, "visible_living_entity_instance_total": len(visible),
            "background_population_count": 0, "unbound_visible_living_entity_count": 0,
            "visible_prop_ids": props, "reference_identity_bindings": [], "absent_episode_entities": absent,
            "provider_reads_episode_global_contract_directly": False}
