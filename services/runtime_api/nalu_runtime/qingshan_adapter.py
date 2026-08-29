from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar


class QingshanAdapterError(RuntimeError):
    pass


class QingshanAdapter:
    """Stable boundary around the pinned, history-oriented Qingshan source tree."""

    upstream_release = "v2026.08.29"
    upstream_commit = "e2b5ff48bde2f0ce41d5f6f7f08cb182c80c7c43"

    required_capabilities: ClassVar[dict[str, str]] = {
        "regression_ci": "tools/run_regression_ci.py",
        "episode_generation_guard": "tools/episode_video_generation_guard.py",
        "continuity_audit": "tools/continuity_auditor.py",
        "character_anchor_audit": "tools/character_anchor_auditor.py",
        "dialogue_safety": "tools/dialogue_cut_safety.py",
        "media_boundary_acceptance": "tools/media_boundary_acceptance.py",
        "release_signoff": "tools/release_signoff_integrity_gate.py",
    }

    def __init__(self, repository_root: Path):
        self.repository_root = repository_root
        self.vendor_root = repository_root / "vendor" / "qingshan"

    def preflight(self, package_path: Path) -> Path:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        missing = [
            name
            for name, relative_path in self.required_capabilities.items()
            if not (self.vendor_root / relative_path).is_file()
        ]
        failures: list[str] = []
        if package.get("schema_version") != "nalu.production-package/v1":
            failures.append("unsupported production package schema")
        if not package.get("package_sha256"):
            failures.append("package digest is absent")
        if missing:
            failures.append("missing imported capabilities: " + ", ".join(missing))

        report = {
            "schema_version": "nalu.qingshan-preflight/v1",
            "upstream_release": self.upstream_release,
            "upstream_commit": self.upstream_commit,
            "production_package": str(package_path),
            "package_sha256": package.get("package_sha256"),
            "capabilities": self.required_capabilities,
            "missing_capabilities": missing,
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "paid_execution_enabled": False,
        }
        report_path = package_path.with_name("qingshan-preflight-report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if failures:
            raise QingshanAdapterError("; ".join(failures))
        return report_path
