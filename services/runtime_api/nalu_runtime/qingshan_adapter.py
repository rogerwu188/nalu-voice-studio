from __future__ import annotations

import hashlib
import json
import shutil
import unicodedata
from pathlib import Path

from .qingshan_compilers import (
    ModelCompilationError,
    ModelCompilerRegistry,
    verify_compilation,
)
from .qingshan_gate_audit import GateRegistryAuditError, audit_gate_registry


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

    @staticmethod
    def _canonical_sha256(value: dict | list) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _normalized_subject(value: object) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        return "".join(normalized.split())

    def _visual_analyzer_inputs(self, package: dict) -> dict:
        assets = package.get("inherited_assets") or []
        entities = package.get("resolved_library") or []
        characters = [entity for entity in entities if entity.get("kind") == "character"]
        props = [entity for entity in entities if entity.get("kind") == "prop"]
        entity_by_id = {str(entity["entity_id"]): entity for entity in [*characters, *props]}
        names_to_entity_ids: dict[str, set[str]] = {}
        for entity_id, entity in entity_by_id.items():
            revision = entity.get("revision") or {}
            attributes = revision.get("attributes") or {}
            aliases = attributes.get("aliases")
            names = [entity.get("stable_name"), *(aliases if isinstance(aliases, list) else [])]
            for name in names:
                normalized = self._normalized_subject(name)
                if normalized:
                    names_to_entity_ids.setdefault(normalized, set()).add(entity_id)

        references: dict[str, list[dict]] = {entity_id: [] for entity_id in entity_by_id}
        unresolved: list[dict[str, object]] = []
        reference_kinds = {"character_image": "character", "prop_reference": "prop"}
        for asset in assets:
            expected_entity_kind = reference_kinds.get(str(asset.get("kind") or ""))
            if expected_entity_kind is None:
                continue
            asset_id = str(asset.get("id") or "")
            subject_name = str(asset.get("subject_name") or "")
            matches = names_to_entity_ids.get(self._normalized_subject(subject_name), set())
            matches = {
                entity_id
                for entity_id in matches
                if entity_by_id[entity_id].get("kind") == expected_entity_kind
            }
            if len(matches) != 1:
                unresolved.append(
                    {
                        "code": (
                            "REFERENCE_SUBJECT_AMBIGUOUS"
                            if len(matches) > 1
                            else "REFERENCE_SUBJECT_UNRESOLVED"
                        ),
                        "asset_id": asset_id,
                        "asset_kind": asset.get("kind"),
                        "subject_name": subject_name,
                    }
                )
                continue
            metadata = asset.get("metadata") or {}
            digest = str(metadata.get("sha256") or "")
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                unresolved.append(
                    {
                        "code": "REFERENCE_DIGEST_INVALID",
                        "asset_id": asset_id,
                        "asset_kind": asset.get("kind"),
                    }
                )
                continue
            entity_id = next(iter(matches))
            references[entity_id].append(
                {
                    "asset_id": asset_id,
                    "asset_kind": asset.get("kind"),
                    "subject_name": subject_name,
                    "local_file_uri": asset.get("local_uri"),
                    "sha256": digest,
                    "content_type": metadata.get("content_type"),
                    "byte_size": metadata.get("byte_size"),
                    "scope": (
                        "episode"
                        if asset.get("episode_id")
                        else "season"
                        if asset.get("season_id")
                        else "project"
                    ),
                    "consent_scope": asset.get("consent_scope"),
                    "guardian_approved": bool(asset.get("guardian_approved")),
                }
            )

        subjects: list[dict[str, object]] = []
        if not characters:
            unresolved.append({"code": "CONFIRMED_CHARACTER_MISSING"})
        required_prop_ids: set[str] = set()
        for entity in characters:
            entity_id = str(entity["entity_id"])
            revision = entity.get("revision") or {}
            attributes = revision.get("attributes") or {}
            wardrobe = attributes.get("wardrobe")
            space_axis = attributes.get("space_axis") or attributes.get("screen_axis")
            pose = attributes.get("pose")
            held_props = attributes.get("held_props")
            if not references[entity_id]:
                unresolved.append({"code": "CHARACTER_REFERENCE_MISSING", "entity_id": entity_id})
            if (
                not isinstance(wardrobe, list)
                or not wardrobe
                or not all(isinstance(item, str) and item.strip() for item in wardrobe)
            ):
                unresolved.append({"code": "WARDROBE_EXPECTATION_MISSING", "entity_id": entity_id})
                wardrobe = []
            if space_axis not in {"screen-left", "screen-right", "center"}:
                unresolved.append(
                    {"code": "SPACE_AXIS_EXPECTATION_INVALID", "entity_id": entity_id}
                )
                space_axis = None
            if pose not in {"standing", "sitting", "lying", "walking", "kneeling"}:
                unresolved.append({"code": "POSE_EXPECTATION_INVALID", "entity_id": entity_id})
                pose = None
            if not isinstance(held_props, list) or not all(
                isinstance(item, str) and item.strip() for item in held_props
            ):
                unresolved.append({"code": "PROP_EXPECTATION_MISSING", "entity_id": entity_id})
                held_props = []
            for held_prop in held_props:
                matches = names_to_entity_ids.get(self._normalized_subject(held_prop), set())
                prop_matches = {
                    candidate_id
                    for candidate_id in matches
                    if entity_by_id[candidate_id].get("kind") == "prop"
                }
                if len(prop_matches) == 1:
                    required_prop_ids.update(prop_matches)
                else:
                    unresolved.append(
                        {
                            "code": (
                                "HELD_PROP_AUTHORITY_AMBIGUOUS"
                                if len(prop_matches) > 1
                                else "HELD_PROP_AUTHORITY_MISSING"
                            ),
                            "entity_id": entity_id,
                            "held_prop": held_prop,
                        }
                    )
            subjects.append(
                {
                    "entity_id": entity_id,
                    "confirmed_revision": entity.get("confirmed_revision"),
                    "stable_name": entity.get("stable_name"),
                    "references": sorted(references[entity_id], key=lambda item: item["asset_id"]),
                    "expected": {
                        "identity": entity.get("stable_name"),
                        "wardrobe": wardrobe,
                        "space_axis": space_axis,
                        "pose": pose,
                        "props": held_props,
                    },
                }
            )
        for entity in props:
            entity_id = str(entity["entity_id"])
            if entity_id in required_prop_ids and not references[entity_id]:
                unresolved.append({"code": "PROP_REFERENCE_MISSING", "entity_id": entity_id})

        body = {
            "schema_version": "nalu.visual-analyzer-inputs/v1",
            "production_package_sha256": package["package_sha256"],
            "resolved_library_sha256": self._canonical_sha256(entities),
            "required_domains": ["identity", "wardrobe", "space_axis", "pose", "props"],
            "subjects": subjects,
            "prop_references": [
                {
                    "entity_id": str(entity["entity_id"]),
                    "confirmed_revision": entity.get("confirmed_revision"),
                    "stable_name": entity.get("stable_name"),
                    "references": sorted(
                        references[str(entity["entity_id"])], key=lambda item: item["asset_id"]
                    ),
                }
                for entity in props
            ],
            "unresolved": unresolved,
            "readiness": "READY" if not unresolved else "BLOCKED",
            "local_execution_only": True,
            "provider_upload_allowed": False,
            "asset_digest_recheck_required": True,
            "final_master_frame_digest_required": True,
        }
        return {**body, "inputs_sha256": self._canonical_sha256(body)}

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
            "exports/provider-results",
        ):
            (workspace / relative).mkdir(parents=True, exist_ok=True)

        episode_number = int(package["episode"]["episode_number"])
        episode_code = f"E{episode_number:02d}"
        script = package["approved_script"]
        visual_analyzer_inputs = self._visual_analyzer_inputs(package)
        visual_analyzer_inputs_path = f"configs/{episode_code}_VISUAL_ANALYZER_INPUTS.json"
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
                "required_outputs": {
                    "shot_boundary_manifest": {
                        "artifact_kind": "shot_manifest",
                        "relative_path": f"exports/{episode_code}_SHOT_BOUNDARIES.json",
                        "contract_path": (f"configs/{episode_code}_SHOT_BOUNDARY_CONTRACT.json"),
                    },
                    "postproduction_lineage_manifest": {
                        "artifact_kind": "postproduction_manifest",
                        "relative_path": (f"exports/{episode_code}_POSTPRODUCTION_LINEAGE.json"),
                        "contract_path": (
                            f"configs/{episode_code}_POSTPRODUCTION_LINEAGE_CONTRACT.json"
                        ),
                    },
                    "visual_continuity_manifest": {
                        "artifact_kind": "visual_continuity_manifest",
                        "relative_path": (f"exports/{episode_code}_VISUAL_CONTINUITY.json"),
                        "contract_path": (
                            f"configs/{episode_code}_VISUAL_CONTINUITY_CONTRACT.json"
                        ),
                    },
                },
                "local_postproduction": {
                    "executor": "nalu-local-postproduction",
                    "request_schema_version": ("nalu.postproduction-materialization-plan/v1"),
                    "provider_result_root": "exports/provider-results",
                    "contract_path": (
                        f"configs/{episode_code}_POSTPRODUCTION_MATERIALIZATION_CONTRACT.json"
                    ),
                    "network_call_performed_by_executor": False,
                },
                "local_visual_analysis": {
                    "inputs_schema_version": "nalu.visual-analyzer-inputs/v1",
                    "inputs_path": visual_analyzer_inputs_path,
                    "inputs_sha256": visual_analyzer_inputs["inputs_sha256"],
                    "readiness": visual_analyzer_inputs["readiness"],
                    "provider_upload_allowed": False,
                    "manifest_must_be_computed_from_decoded_frames": True,
                },
            },
        )
        self._write_json(
            workspace / "configs" / f"{episode_code}_SHOT_BOUNDARY_CONTRACT.json",
            {
                "schema_version": "nalu.shot-boundary-output-contract/v1",
                "manifest_schema_version": "nalu.shot-boundary-manifest/v1",
                "artifact_kind": "shot_manifest",
                "output_relative_path": f"exports/{episode_code}_SHOT_BOUNDARIES.json",
                "production_package_sha256": package["package_sha256"],
                "digest_algorithm": ("sha256-canonical-json-excluding-manifest_sha256"),
                "required_unit_fields": ["unit_id", "start_seconds", "end_seconds"],
                "required_incoming_transition_fields": [
                    "transition_type",
                    "visual_change_required",
                    "audio_bridge",
                ],
                "fail_closed": True,
            },
        )
        self._write_json(
            workspace / "configs" / f"{episode_code}_POSTPRODUCTION_LINEAGE_CONTRACT.json",
            {
                "schema_version": "nalu.postproduction-lineage-output-contract/v1",
                "manifest_schema_version": "nalu.postproduction-lineage-manifest/v1",
                "artifact_kind": "postproduction_manifest",
                "output_relative_path": (f"exports/{episode_code}_POSTPRODUCTION_LINEAGE.json"),
                "production_package_sha256": package["package_sha256"],
                "required_picture_evidence": [
                    "selected source SHA and provider task/receipt",
                    "ADMITTED_FOR_ASSEMBLY status",
                    "decoded normalized segment SHA and zero-based timeline",
                ],
                "normalized_media": {
                    "audio_sample_rate_hz": 48000,
                    "audio_channels": 2,
                    "pixel_format": "yuv420p",
                    "timestamps_zero_based": True,
                },
                "required_audio_layers": [
                    "dialogue",
                    "ambience",
                    "foley",
                    "music",
                    "sfx",
                ],
                "published_mix_must_bind_final_master_audio": True,
                "release_loudness": {
                    "measurement_standard": "EBU_R128_LIBAVFILTER",
                    "measured_from_decoded_media": True,
                    "integrated_loudness_range_lufs": [-17.0, -15.0],
                    "max_loudness_range_lu": 12.0,
                    "true_peak_max_dbtp": -1.0,
                },
                "subtitles_must_bind_sealed_captions": True,
                "fail_closed": True,
            },
        )
        self._write_json(
            workspace / "configs" / f"{episode_code}_POSTPRODUCTION_MATERIALIZATION_CONTRACT.json",
            {
                "schema_version": "nalu.postproduction-materialization-contract/v1",
                "request_schema_version": "nalu.postproduction-materialization-plan/v1",
                "result_schema_version": "nalu.postproduction-materialization/v1",
                "provider_result_root": "exports/provider-results",
                "production_package_sha256": package["package_sha256"],
                "required_shot_authority": [
                    "source task ID",
                    "provider receipt SHA-256",
                    "source file SHA-256",
                    "explicit admitted source interval",
                    "locally measured provider-media duration",
                    "explicit editorial selection excluding whole-media passthrough",
                ],
                "whole_provider_media_passthrough_forbidden": True,
                "required_audio_layers": [
                    "dialogue",
                    "ambience",
                    "foley",
                    "music",
                    "sfx",
                ],
                "normalization": {
                    "pixel_format": "yuv420p",
                    "audio_sample_rate_hz": 48000,
                    "audio_channels": 2,
                    "timestamps_zero_based": True,
                    "release_target_lufs": -16.0,
                    "release_true_peak_headroom_dbtp": -1.5,
                    "maximum_gain_db": 12.0,
                    "maximum_attenuation_db": 8.0,
                },
                "release_loudness_measured_locally": True,
                "atomic_output_directory": True,
                "source_digest_rechecked_before_commit": True,
                "network_call_performed": False,
                "fail_closed": True,
            },
        )
        self._write_json(workspace / visual_analyzer_inputs_path, visual_analyzer_inputs)
        self._write_json(
            workspace / "configs" / f"{episode_code}_VISUAL_CONTINUITY_CONTRACT.json",
            {
                "schema_version": "nalu.visual-continuity-output-contract/v1",
                "manifest_schema_version": "nalu.visual-continuity-manifest/v1",
                "artifact_kind": "visual_continuity_manifest",
                "output_relative_path": (f"exports/{episode_code}_VISUAL_CONTINUITY.json"),
                "production_package_sha256": package["package_sha256"],
                "resolved_library_sha256": self._canonical_sha256(
                    package.get("resolved_library") or []
                ),
                "analyzer_inputs_path": visual_analyzer_inputs_path,
                "analyzer_inputs_sha256": visual_analyzer_inputs["inputs_sha256"],
                "analyzer_inputs_readiness": visual_analyzer_inputs["readiness"],
                "required_domains": [
                    "identity",
                    "wardrobe",
                    "space_axis",
                    "pose",
                    "props",
                ],
                "evidence_frame_must_decode_from_final_master": True,
                "local_analyzer_required": True,
                "asset_digest_recheck_required": True,
                "authored_observations_are_not_perceptual_evidence": True,
                "human_original_resolution_review_still_required": True,
                "fail_closed": True,
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
        try:
            gate_registry_audit = audit_gate_registry(
                self.repository_root,
                self.vendor_root,
                upstream_release=self.upstream_release,
                upstream_commit=self.upstream_commit,
            )
        except GateRegistryAuditError as exc:
            raise QingshanAdapterError(str(exc)) from exc
        gate_registry_audit_path = workspace / "workflow" / "qingshan-gate-registry-audit.json"
        self._write_json(gate_registry_audit_path, gate_registry_audit)

        tracked_files = sorted(path for path in workspace.rglob("*") if path.is_file())
        manifest = {
            "schema_version": "nalu.qingshan-workspace-manifest/v1",
            "upstream_release": self.upstream_release,
            "upstream_commit": self.upstream_commit,
            "episode": episode_code,
            "production_package_sha256": package["package_sha256"],
            "model_compilation": str(model_compilation.relative_to(workspace)),
            "model_compilation_sha256": self._sha256(model_compilation),
            "gate_registry_audit": str(gate_registry_audit_path.relative_to(workspace)),
            "gate_registry_audit_sha256": self._sha256(gate_registry_audit_path),
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

        gate_audit_relative = manifest.get("gate_registry_audit")
        gate_audit_path = workspace / "workflow" / "qingshan-gate-registry-audit.json"
        gate_audit: dict = {}
        if gate_audit_relative != "workflow/qingshan-gate-registry-audit.json":
            failures.append("Qingshan gate registry audit path is invalid")
        elif not gate_audit_path.is_file() or gate_audit_path.is_symlink():
            failures.append("Qingshan gate registry audit is absent or unsafe")
        else:
            try:
                gate_audit = json.loads(gate_audit_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                failures.append("Qingshan gate registry audit is invalid JSON")
            if self._sha256(gate_audit_path) != manifest.get("gate_registry_audit_sha256"):
                failures.append("Qingshan gate registry audit SHA mismatch")
            if gate_audit.get("upstream_commit") != self.upstream_commit:
                failures.append("Qingshan gate registry audit is bound to another upstream commit")
            if gate_audit.get("status") not in {
                "PASS_INTEGRITY",
                "QUARANTINED_KNOWN_UPSTREAM_DEFECT",
            }:
                failures.append("Qingshan gate registry has unreviewed integrity failures")
            if (
                not package.get("production_policy", {}).get("dry_run", True)
                and gate_audit.get("paid_execution_allowed") is not True
            ):
                failures.append("paid execution is blocked by Qingshan gate registry quarantine")

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
            "gate_registry_audit": gate_audit_relative,
            "gate_registry_audit_sha256": manifest.get("gate_registry_audit_sha256"),
            "gate_registry_status": gate_audit.get("status"),
            "registered_gate_count": gate_audit.get("gate_count"),
            "registered_tests_executed": gate_audit.get("registered_tests_executed", False),
            "capabilities": self.required_capabilities,
            "capability_contracts": self.capability_contracts,
            "missing_capabilities": missing,
            "changed_capabilities": changed,
            "status": "PASS" if not failures else "FAIL",
            "failures": failures,
            "paid_execution_enabled": False,
        }
        report_path = package_path.with_name("qingshan-preflight-report.json")
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if failures:
            raise QingshanAdapterError("; ".join(failures))
        return report_path
