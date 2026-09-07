from types import SimpleNamespace

import pytest
from nalu_runtime.repository import ConflictError
from nalu_runtime.shot_planning import ShotDraft, ShotPlan, ShotPlanningService, VisualAssetDraft


@pytest.mark.parametrize("case", ["new", "linked", "unknown_link", "wrong_kind", "source", "duplicate_key",
                                  "unknown_design", "duplicate_design", "missing_scene", "extra_scene", "unused", "unselected_link"])
def test_reference_designs_are_source_bound_not_fabricated_materials(case):
    source = "外婆站在海边。"
    person = VisualAssetDraft(key="grandma", kind="character_image", name="外婆", description="外貌和服装待确认",
                              source_excerpt=source)
    scene = VisualAssetDraft(key="beach", kind="scene_reference", name="海边", description="岸边，具体时段待确认",
                             source_excerpt=source)
    shot = ShotDraft(source_excerpt=source, scene="海边", duration_seconds=15, entry_state="站在岸边",
                     action="看海", exit_state="望向海面", camera="中景", dialogue_or_narration="", sound="海浪",
                     image_prompt="站在岸边的首帧", video_prompt="抬头看海", reference_asset_ids=[],
                     visual_asset_keys=["grandma", "beach"], transition="scene_start")
    plan = ShotPlan(summary="海边", shots=[shot], visual_assets=[person, scene])
    assets = []
    if case in {"linked", "unknown_link", "wrong_kind", "unselected_link"}:
        person.existing_asset_id = "asset-real"
        shot.reference_asset_ids = [] if case == "unselected_link" else ["asset-real"]
        if case != "unknown_link":
            assets = [{"id": "asset-real", "kind": "scene_reference" if case == "wrong_kind" else "character_image"}]
    if case == "source":
        person.source_excerpt = "不是剧本原文"
    if case == "duplicate_key":
        scene.key = person.key
    if case == "unknown_design":
        shot.visual_asset_keys.append("not-in-plan")
    if case == "duplicate_design":
        shot.visual_asset_keys.append("grandma")
    if case == "missing_scene":
        shot.visual_asset_keys.remove("beach")
    if case in {"extra_scene", "unused"}:
        plan.visual_assets.append(scene.model_copy(update={"key": "another-beach"}))
        if case == "extra_scene":
            shot.visual_asset_keys.append("another-beach")
    episode = SimpleNamespace(target_seconds=15, episode_number=1)
    if case not in {"new", "linked"}:
        with pytest.raises(ConflictError):
            ShotPlanningService.tasks_for_plan(plan, episode, {"content": source}, assets)
        return
    tasks = ShotPlanningService.tasks_for_plan(plan, episode, {"content": source}, assets)
    assert tasks[0]["reference_designs_to_create"] == (["grandma", "beach"] if case == "new" else ["beach"])
    assert shot.reference_asset_ids == ([] if case == "new" else ["asset-real"])
    assert not hasattr(person, "qa_passed")
