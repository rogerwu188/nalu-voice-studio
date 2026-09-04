import importlib.util
import json
import textwrap
from copy import deepcopy
from pathlib import Path


def load_checker():
    path = Path(__file__).resolve().parents[1] / "scripts/check_qingshan_upstream.py"
    spec = importlib.util.spec_from_file_location("check_qingshan_upstream", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_isolated_auditor():
    path = Path(__file__).resolve().parents[1] / "scripts/audit_qingshan_candidate.py"
    spec = importlib.util.spec_from_file_location("audit_qingshan_candidate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_registered_test_auditor():
    path = Path(__file__).resolve().parents[1] / "scripts/test_qingshan_candidate.py"
    spec = importlib.util.spec_from_file_location("test_qingshan_candidate_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_audit_is_quarantined_and_fail_closed() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())

    assert checker.verify_candidate_audit(manifest, audit) == []
    assert audit["promotion_status"] == "QUARANTINED"
    assert audit["paid_execution_allowed"] is False
    assert audit["replaces_active_pin"] is False
    assert audit["failures"] == []
    assert audit["integrity_status"] == "PASS"
    assert audit["public_interface_status"] == "FAIL"
    assert audit["public_interface_failures"] == [
        "public_interface:portable_manifest_version_mismatch"
    ]
    assert audit["public_cli_entrypoint"] == "qingshan_engine.cli:main"
    assert audit["public_cli_commands"] == [
        "doctor",
        "init",
        "release-preflight",
        "test",
        "video-preflight",
        "writer-doctor",
    ]
    assert audit["writer_v2_status"] == "PASS"
    assert audit["writer_provenance_schema"] == "qingshan.canonical_writer_provenance.v1"
    assert "default" in audit["writer_generic_model_aliases"]
    assert audit["registered_test_execution_performed"] is True
    assert audit["registered_test_status"] == "PASS"
    assert audit["registered_test_module_count"] == 33
    assert audit["registered_portable_test_count"] == 209
    assert audit["registered_portable_skipped_count"] == 1
    assert audit["registered_writer_test_count"] == 6
    assert audit["registered_test_failures"] == []


def test_latest_release_is_covered_only_by_active_or_reviewed_record() -> None:
    checker = load_checker()
    manifest = {"release": "stable"}
    audit = {"candidate_release": "reviewed"}

    assert checker.release_requires_review("stable", manifest, audit) is False
    assert checker.release_requires_review("reviewed", manifest, audit) is False
    assert checker.release_requires_review("new", manifest, audit) is True


def test_candidate_audit_rejects_false_promotion_and_unknown_failures() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())
    tampered = deepcopy(audit)
    tampered["promotion_status"] = "PROMOTED"
    tampered["paid_execution_allowed"] = True
    tampered["replaces_active_pin"] = True
    tampered["failures"] = ["ignored_failure:unsafe"]

    failures = checker.verify_candidate_audit(manifest, tampered)
    assert "candidate audit contains an unsupported failure classification" in failures
    assert "failed candidate audit must remain quarantined and fail closed" in failures


def test_candidate_audit_rejects_incomplete_registered_test_evidence() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())
    tampered = deepcopy(audit)
    tampered["registered_test_status"] = "NOT_RUN"
    tampered["registered_portable_test_count"] = 0

    assert (
        "candidate registered-test evidence is incomplete"
        in checker.verify_candidate_audit(manifest, tampered)
    )


def test_registered_test_comparison_rejects_count_drift() -> None:
    runner = load_registered_test_auditor()
    expected = {
        "registered_test_execution_performed": True,
        "registered_test_status": "PASS",
        "registered_test_module_count": 33,
        "registered_portable_test_count": 208,
        "registered_portable_skipped_count": 1,
        "registered_writer_test_count": 6,
        "registered_test_failures": [],
    }
    actual = deepcopy(expected)
    actual["registered_portable_test_count"] = 207

    assert runner.compare_test_evidence(actual, expected) == [
        "candidate registered-test drift: registered_portable_test_count"
    ]


def test_candidate_audit_rejects_unportable_public_interface() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())
    tampered = deepcopy(audit)
    tampered["public_interface_status"] = "FAIL"
    tampered["public_interface_failures"] = ["public_interface:private_import"]

    tampered["public_interface_failures"] = []
    assert (
        "candidate public engine interface record is inconsistent"
        in checker.verify_candidate_audit(manifest, tampered)
    )


def test_candidate_audit_rejects_writer_provenance_drift() -> None:
    checker = load_checker()
    manifest = json.loads(checker.MANIFEST_PATH.read_text())
    audit = json.loads(checker.CANDIDATE_AUDIT_PATH.read_text())
    tampered = deepcopy(audit)
    tampered["writer_generic_model_aliases"] = ["claude"]

    assert (
        "candidate Writer v2 provenance contract is not portable"
        in checker.verify_candidate_audit(manifest, tampered)
    )


def test_portable_auditor_rejects_absolute_path_even_when_file_exists() -> None:
    auditor = load_isolated_auditor()
    existing_absolute_path = str(Path(__file__).resolve())
    registry = {
        "gates": [
            {
                "gate_id": "TEST-GATE",
                "stage": "TEST",
                "implementation_type": "CODED",
                "code_paths": ["runner.py"],
                "test_paths": [existing_absolute_path],
                "stage_runner_paths": ["runner.py"],
                "parameters": {},
                "authorization_ref": "none",
                "last_backtest_date": "2026-09-01",
            }
        ]
    }
    report = auditor.validate_registry(registry, Path("/tmp/does-not-matter"))
    assert any(item.startswith("nonportable_absolute_path:TEST-GATE:") for item in report["failures"])


def test_public_interface_audit_rejects_private_import(tmp_path: Path) -> None:
    auditor = load_isolated_auditor()
    (tmp_path / "qingshan_engine").mkdir()
    (tmp_path / "configs").mkdir()
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "qingshan_engine" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "qingshan_engine" / "cli.py").write_text("import backlot_os\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "qingshan-short-drama-engine"
            version = "0.3.0"
            license = {file = "LICENSE"}
            dependencies = []
            [project.scripts]
            qingshan = "qingshan_engine.cli:main"
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "configs" / "PORTABLE_CORE_MANIFEST.json").write_text(
        json.dumps(
            {
                "schema": "qingshan.portable_core_manifest.v1",
                "version": "0.3.0",
                "required_files": ["LICENSE", "qingshan_engine/cli.py"],
            }
        ),
        encoding="utf-8",
    )

    report = auditor.validate_public_interface(tmp_path)

    assert report["public_interface_status"] == "FAIL"
    assert "public_interface:private_import:qingshan_engine/cli.py:backlot_os" in report[
        "public_interface_failures"
    ]


def test_writer_v2_audit_rejects_unbound_dispatcher(tmp_path: Path) -> None:
    auditor = load_isolated_auditor()
    for relative in auditor.WRITER_REQUIRED_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (tmp_path / auditor.WRITER_PROVENANCE_PATH).write_text(
        textwrap.dedent(
            """
            PROVENANCE_SCHEMA = "qingshan.canonical_writer_provenance.v1"
            RECEIPT_SCHEMA = "qingshan.canonical_writer_run_receipt.v1"
            ALLOWED_AGENT_IDS = {"writer"}
            GENERIC_MODEL_ALIASES = {"auto", "default"}
            """
        ),
        encoding="utf-8",
    )

    report = auditor.validate_writer_v2_contract(tmp_path)

    assert report["writer_v2_status"] == "FAIL"
    assert report["writer_v2_failures"] == [
        "writer_v2:dispatcher_provenance_binding_missing"
    ]
