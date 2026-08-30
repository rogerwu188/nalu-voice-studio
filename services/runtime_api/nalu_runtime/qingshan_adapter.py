from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .qingshan_compilers import (
    ModelCompilationError,
    ModelCompilerRegistry,
    verify_compilation,
)


class QingshanAdapterError(RuntimeError):
    pass


class QingshanAdapter:
    """Stable boundary around the pinned, history-oriented Qingshan source tree."""

    def __init__(self, repository_root: Path):
        self.repository_root = repository_root
        self.vendor_root = repository_root / "vendor" / "qingshan"
        manifest_path = repository_root / "configs" / "qingshan-upstream.json"
        self.upstream_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.upstream_release = self.upstream_manifest["release"]
        self.upstream_commit = self.upstream_manifest["commit"]
        self.capability_contracts = self.upstream_manifest["capabilities"]
        self.required_capabilities = {
            name: contract["path"] for name, contract in self.capability_contracts.items()
        }
        self.model_compilers = ModelCompilerRegistry()

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
        entities_by_kind: dict[str, list[dict]] = {}
        for entity in package.get("resolved_library") or []:
            entities_by_kind.setdefault(str(entity["kind"]), []).append(entity)
        library_targets = {
            "character_image": ("character", "libraries/characters/index.json"),
            "voice_reference": ("voice", "libraries/audio/index.json"),
            "scene_reference": ("scene", "libraries/scenes/index.json"),
            "prop_reference": ("prop", "libraries/props/index.json"),
            "style_reference": ("style", "libraries/visual_style/index.json"),
        }
        for asset_kind, (entity_kind, target) in library_targets.items():
            self._write_json(
                workspace / target,
                {
                    "schema_version": "nalu.qingshan-resolved-library/v1",
                    "asset_kind": asset_kind,
                    "entity_kind": entity_kind,
                    "assets": assets_by_kind.get(asset_kind, []),
                    "confirmed_entities": entities_by_kind.get(entity_kind, []),
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
        try:
            model_compilation = self.model_compilers.compile(package, workspace)
        except ModelCompilationError as exc:
            raise QingshanAdapterError(str(exc)) from exc

        tracked_files = sorted(path for path in workspace.rglob("*") if path.is_file())
        manifest = {
            "schema_version": "nalu.qingshan-workspace-manifest/v1",
            "upstream_release": self.upstream_release,
            "upstream_commit": self.upstream_commit,
            "episode": episode_code,
            "production_package_sha256": package["package_sha256"],
            "model_compilation": str(model_compilation.relative_to(workspace)),
            "model_compilation_sha256": self._sha256(model_compilation),
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
        changed = [
            name
            for name, contract in self.capability_contracts.items()
            if (self.vendor_root / contract["path"]).is_file()
            and self._sha256(self.vendor_root / contract["path"]) != contract["sha256"]
        ]
        failures: list[str] = []
        model_registry_failures = self.model_compilers.validate_upstream_registry(
            self.vendor_root / "configs" / "VIDEO_MODEL_CAPABILITY_REGISTRY_v1.json"
        )
        if package.get("schema_version") != "nalu.production-package/v1":
            failures.append("unsupported production package schema")
        if not package.get("package_sha256"):
            failures.append("package digest is absent")
        else:
            canonical_package = {
                key: value for key, value in package.items() if key != "package_sha256"
            }
            encoded = json.dumps(
                canonical_package,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if hashlib.sha256(encoded).hexdigest() != package["package_sha256"]:
                failures.append("production package digest mismatch")
        if missing:
            failures.append("missing imported capabilities: " + ", ".join(missing))
        if changed:
            failures.append("unreviewed capability changes: " + ", ".join(changed))
        failures.extend(model_registry_failures)
        workspace_manifest = workspace / "workspace-manifest.json"
        if not workspace_manifest.is_file():
            failures.append("standard Qingshan workspace manifest is absent")
            manifest = {}
        else:
            try:
                manifest = json.loads(workspace_manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
                failures.append("standard Qingshan workspace manifest is invalid JSON")

        compilation_relative = manifest.get("model_compilation")
        compilation_path: Path | None = None
        if compilation_relative:
            relative_path = Path(str(compilation_relative))
            candidate = workspace / relative_path
            try:
                resolved_workspace = workspace.resolve(strict=True)
                resolved_candidate = candidate.resolve(strict=True)
                resolved_candidate.relative_to(resolved_workspace)
                if relative_path.is_absolute() or candidate.is_symlink():
                    raise ValueError
                compilation_path = candidate
            except (OSError, ValueError):
                failures.append("registered model compilation path is unsafe")
        if compilation_path is None or not compilation_path.is_file():
            failures.append("registered model compilation is absent")
        else:
            failures.extend(verify_compilation(compilation_path, package))
            if self._sha256(compilation_path) != manifest.get("model_compilation_sha256"):
                failures.append("workspace model compilation SHA mismatch")

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
            "model_compilation": compilation_relative,
            "model_compilation_sha256": manifest.get("model_compilation_sha256"),
            "registered_compilers": self.model_compilers.supported_models,
            "model_registry_failures": model_registry_failures,
            "capabilities": self.required_capabilities,
            "capability_contracts": self.capability_contracts,
            "missing_capabilities": missing,
            "changed_capabilities": changed,
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "paid_execution_enabled": False,
        }
        report_path = package_path.with_name("qingshan-preflight-report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if failures:
            raise QingshanAdapterError("; ".join(failures))
        return report_path
