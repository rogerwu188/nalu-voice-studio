import hashlib
from types import SimpleNamespace

import pytest
from nalu_runtime.episode_dialogue import EpisodeDialogueService, EpisodeMixPreparationRequest
from nalu_runtime.models import PostproductionShotSource
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_preparation import digest


def fixture(monkeypatch):
    sha = "a" * 64
    shot = PostproductionShotSource(shot_id="shot", source_relative_path="provider-results/shot.mp4",
        source_sha256=sha, source_task_id="task", source_receipt_sha256=sha,
        source_in_seconds=0, source_out_seconds=1)
    sound = {"edit_id": "edit", "cues": [{"shot_index": 0}]}
    lineage = {"sound_plan_id": "sound", "sound_plan_sha256": sha,
               "lineage_sha256": sha, "sources": [{"caption_review_sha256": sha}]}
    files = {name: {"relative_path": f"provider-results/adopted-dialogue/{sha}/{name}", "sha256": sha}
             for name in ["dialogue.wav", "captions.vtt"]}
    payload = {"lineage": lineage, "files": files}
    payload["staging_sha256"] = digest(payload)
    receipt = SimpleNamespace(id="stage", run_id="run", event_type="episode_dialogue_staged", payload=payload)
    events = {"stage": receipt, "sound": SimpleNamespace(payload=sound),
              "edit": SimpleNamespace(payload={"shots": [shot.model_dump(mode="json")], "frame_rate": 24})}
    service = EpisodeDialogueService(SimpleNamespace(get_run_event=lambda identity: events[identity]), "/unused")
    monkeypatch.setattr(service, "stage", lambda *args: receipt)
    dialogue = SimpleNamespace(layer="dialogue", source_relative_path=files["dialogue.wav"]["relative_path"],
        source_sha256=sha, source_in_seconds=0, source_cue_sha256s=[digest(sound["cues"][0])])
    request = SimpleNamespace(adopted_dialogue_staging_id="stage", expected_dialogue_staging_sha256=payload["staging_sha256"],
        audio_layers=[dialogue], captions_source_relative_path=files["captions.vtt"]["relative_path"],
        captions_source_sha256=sha, subtitle_contract_sha256=digest([sha]), shots=[shot], frame_rate=24)
    return service, request


def test_current_adopted_inputs_match_materializer(monkeypatch):
    service, request = fixture(monkeypatch)
    assert service.validate_materialization("run", request).id == "stage"


@pytest.mark.parametrize("field,value", [("captions_source_sha256", "b" * 64),
    ("subtitle_contract_sha256", "b" * 64), ("frame_rate", 30), ("shots", []),
    ("expected_dialogue_staging_sha256", "b" * 64)])
def test_materializer_rejects_changed_adopted_inputs(monkeypatch, field, value):
    service, request = fixture(monkeypatch)
    setattr(request, field, value)
    with pytest.raises(ConflictError):
        service.validate_materialization("run", request)


def test_materializer_rejects_shifted_dialogue(monkeypatch):
    service, request = fixture(monkeypatch)
    request.audio_layers[0].source_in_seconds = 0.5
    with pytest.raises(ConflictError):
        service.validate_materialization("run", request)


def test_prepare_mix_fills_adopted_inputs_without_professional_fields(monkeypatch, tmp_path):
    service, current = fixture(monkeypatch)
    service.repository.get_run = lambda _: SimpleNamespace(package_path=str(tmp_path / "package.json"))
    exports = tmp_path / "qingshan-workspace/exports/provider-results"
    exports.mkdir(parents=True)
    raw = b"synthetic file identity fixture, not decoded audio"
    sha = hashlib.sha256(raw).hexdigest()
    layers = []
    for layer in ("music", "ambience", "sfx", "foley"):
        (exports / f"{layer}.wav").write_bytes(raw)
        layers.append({"layer": layer, "source_relative_path": f"provider-results/{layer}.wav",
            "source_sha256": sha, "source_cue_sha256s": ["a" * 64]})
    selected = EpisodeMixPreparationRequest(staging_id="stage", expected_staging_sha256=current.expected_dialogue_staging_sha256,
        requested_by="synthetic-qa", sound_layers=layers, width=64, height=64)
    prepared = service.prepare_mix("run", selected)
    assert prepared.adopted_dialogue_staging_id == "stage"
    assert prepared.shots == current.shots
    assert prepared.audio_layers[0].layer == "dialogue"
    assert prepared.audio_layers[0].source_in_seconds == 0
    assert prepared.subtitle_contract_sha256 == current.subtitle_contract_sha256
    assert prepared.captions_source_relative_path == current.captions_source_relative_path
    assert prepared.frame_rate == 24
    (exports / "music.wav").write_bytes(b"changed")
    with pytest.raises(ConflictError, match="missing or changed"):
        service.prepare_mix("run", selected)
