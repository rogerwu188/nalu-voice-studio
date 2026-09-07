import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from nalu_runtime.qingshan_compilers import (
    ModelCompilationError,
    ModelCompilerRegistry,
    verify_compilation,
)
from nalu_runtime.video_preparation import digest


@pytest.mark.parametrize("model", ["seedance-2.0-pro", "MiniMax-H3"])
@pytest.mark.parametrize("ratio", [None, "16:9", "9:16", "1:1", "4:3", "3:4", "0:1", "1:0", "bad", ""])
def test_compilation_preserves_project_framing_and_rejects_resealed_override(tmp_path, model, ratio):
    package = {"project": {} if ratio is None else {"aspect_ratio": ratio},
               "production_policy": {"requested_model": model},
               "episode": {"id": "episode", "episode_number": 1},
               "approved_script": {"revision": 1, "content": "合成纪录片画幅测试"}}
    package["package_sha256"] = digest(package)
    compiler = ModelCompilerRegistry()
    if ratio in {"0:1", "1:0", "bad", ""}:
        with pytest.raises(ModelCompilationError, match="aspect ratio"):
            compiler.compile(package, tmp_path)
        return
    path = compiler.compile(package, tmp_path)
    value = json.loads(path.read_text())
    assert value["planning_defaults"]["aspect_ratio"] == ("9:16" if ratio is None else ratio)
    assert not verify_compilation(path, package)
    schema = json.loads((Path(__file__).resolve().parents[1] / "contracts/qingshan-model-compilation.schema.json").read_text())
    Draft202012Validator(schema).validate(value)
    changed = deepcopy(value)
    changed["planning_defaults"]["aspect_ratio"] = "16:9" if value["planning_defaults"]["aspect_ratio"] != "16:9" else "9:16"
    changed["compilation_sha256"] = digest({k: v for k, v in changed.items() if k != "compilation_sha256"})
    path.write_text(json.dumps(changed))
    assert "model compilation planning defaults changed" in verify_compilation(path, package)
