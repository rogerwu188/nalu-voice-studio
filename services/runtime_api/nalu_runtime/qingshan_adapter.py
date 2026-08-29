from __future__ import annotations

import hashlib
import json
import shutil
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

    @staticmethod
    def _write_json(path: Path, value: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def materialize_workspace(self, package_path: Path) -> Path:
        """Create a clean, episode-agnostic Qingshan workspace from a Nalu package."""
        package = json.loads(package_path.read_text(encoding="utf-8"))
        workspace = package_path.parent / "qingshan-workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        for relative in (
            "source",
            "workflow/tasks",
            "configs",
            "libraries/characters",
            "libraries/scenes",
            "libraries/props",
            "libraries/audio",
            "libraries/visual_style",
            "libraries/prompts",
            "libraries/qa",
            "libraries/continuity",
            "exports",
        ):
            (workspace / relative).mkdir(parents=True, exist_ok=True)

        episode_number = int(package["episode"]["episode_number"])
        episode_code = f"E{episode_number:02d}"
        script = package["approved_script"]
        (workspace / "source" / f"{episode_code}_APPROVED_SCRIPT.md").write_text(
            script["content"].rstrip() + "\n", encoding="utf-8"
        )

        self._write_json(
            workspace / "workflow" / "NALU_PRODUCTION_PACKAGE.json",
            package,
        )
        self._write_json(
            workspace / "workflow" / "work_queue.json",
            {
                "schema_version": "nalu.qingshan-work-queue/v1",
                "current": {
                    "episode": episode_code,
                    "episode_id": package["episode"]["id"],
                    "stage": "APPROVED_SCRIPT_INTAKE",
                    "production_package_sha256": package["package_sha256"],
                },
                "paid_submission_enabled": False,
            },
        )
        self._write_json(
            workspace / "workflow" / "tasks" / f"{episode_code}_PRODUCTION_TASK.json",
            {
                "schema_version": "nalu.qingshan-episode-task/v1",
                "episode": episode_code,
                "project_id": package["project"]["id"],
                "season_id": package["season"]["id"],
                "episode_id": package["episode"]["id"],
                "status": "READY_FOR_QINGSHAN_PREFLIGHT",
                "approved_script_revision": script["revision"],
                "requested_model": package["production_policy"]["requested_model"],
                "dry_run": package["production_policy"]["dry_run"],
            },
        )

        assets_by_kind: dict[str, list[dict]] = {}
        for asset in package.get("inherited_assets") or []:
            assets_by_kind.setdefault(str(asset["kind"]), []).append(asset)
        library_targets = {
            "character_image": "libraries/characters/index.json",
            "voice_reference": "libraries/audio/index.json",
            "scene_reference": "libraries/scenes/index.json",
            "prop_reference": "libraries/props/index.json",
            "style_reference": "libraries/visual_style/index.json",
        }
        for kind, target in library_targets.items():
            self._write_json(
                workspace / target,
                {
                    "schema_version": "nalu.qingshan-asset-index/v1",
                    "kind": kind,
                    "assets": assets_by_kind.get(kind, []),
                },
            )

        self._write_json(
            workspace / "libraries" / "continuity" / f"{episode_code}_INHERITED_STATE.json",
            package.get("continuity")
            or {
                "schema_version": "nalu.continuity-empty/v1",
                "state": {},
                "unresolved_hooks": [],
            },
        )
        self._write_json(
            workspace / "configs" / f"{episode_code}_PRODUCTION_POLICY.json",
            package["production_policy"],
        )

        tracked_files = sorted(path for path in workspace.rglob("*") if path.is_file())
        manifest = {
            "schema_version": "nalu.qingshan-workspace-manifest/v1",
            "upstream_release": self.upstream_release,
            "upstream_commit": self.upstream_commit,
            "episode": episode_code,
            "production_package_sha256": package["package_sha256"],
            "files": [
                {
                    "path": str(path.relative_to(workspace)),
                    "sha256": self._sha256(path),
                }
                for path in tracked_files
            ],
        }
        self._write_json(workspace / "workspace-manifest.json", manifest)
        return workspace

    def preflight(self, package_path: Path, workspace: Path | None = None) -> Path:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        workspace = workspace or self.materialize_workspace(package_path)
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
        workspace_manifest = workspace / "workspace-manifest.json"
        if not workspace_manifest.is_file():
            failures.append("standard Qingshan workspace manifest is absent")

        report = {
            "schema_version": "nalu.qingshan-preflight/v1",
            "upstream_release": self.upstream_release,
            "upstream_commit": self.upstream_commit,
            "production_package": str(package_path),
            "workspace": str(workspace),
            "workspace_manifest_sha256": (
                self._sha256(workspace_manifest) if workspace_manifest.is_file() else None
            ),
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
