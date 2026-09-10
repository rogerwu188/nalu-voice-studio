import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_rejected_edit_stops_qa_before_assets_or_render(tmp_path, monkeypatch, capsys):
    path = Path(__file__).parents[1] / "scripts/verify-repair-mix.py"
    spec = importlib.util.spec_from_file_location("repair_mix_qa_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "nalu-native-postproduction-guard"
    root.mkdir()
    (root / "nalu.sqlite3").touch()
    sound = SimpleNamespace(event_type="episode_sound_plan_drafted", payload={
        "edit_id": "edit", "edit_sha256": "a" * 64, "edit_review_id": "old-review"})
    repo = SimpleNamespace(list_run_events=lambda run: [sound])
    app = SimpleNamespace(state=SimpleNamespace(repository=repo))
    monkeypatch.setattr(module, "create_app", lambda *args: app)

    class Client:
        def __init__(self, app):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            pytest.fail("rejected edit must not invoke any write endpoint")

    monkeypatch.setattr(module, "TestClient", Client)

    def reject(self, run, edit, sha, review):
        assert (run, edit, sha, review) == ("child", "edit", "a" * 64, "old-review")
        raise module.ConflictError("reload the current edit confirmation before postproduction")

    monkeypatch.setattr(module.EpisodeEditReviewService, "approved", reject)
    monkeypatch.setattr(module, "AssetService", lambda *args: pytest.fail("must not import audio"))
    monkeypatch.setattr("sys.argv", [str(path), str(root), "child", "--synthetic-sound", "--render"])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["failed_stage"] == "edit_approval"
    assert result["assets_imported"] is False
    assert result["render_started"] is False
    assert result["real_master_accepted"] is False
