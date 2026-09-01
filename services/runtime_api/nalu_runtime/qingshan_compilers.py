from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ModelCompilationError(RuntimeError):
    pass


def _canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class QingshanModelCompiler(ABC):
    """Compile an immutable Nalu package into one provider-specific planning contract."""

    adapter_id: str
    adapter_version = "1.2.0"
    profile_id: str
    model: str
    native_resolution: str
    minimum_duration_seconds: int
    maximum_duration_seconds = 15

    @abstractmethod
    def provider_contract(self) -> dict[str, Any]:
        """Return constraints that are unique to the selected provider adapter."""

    def paid_boundary_contract(self) -> dict[str, Any]:
        """Return the fields that must survive every future paid task boundary."""
        return {
            "schema_version": "nalu.qingshan-paid-boundary-contract/v1",
            "adapter_id_required": self.adapter_id,
            "profile_id_required": self.profile_id,
            "model_required": self.model,
            "provider_model_id_required": self.model,
            "duration_seconds_required": True,
            "minimum_duration_seconds": self.minimum_duration_seconds,
            "maximum_duration_seconds": self.maximum_duration_seconds,
            "explicit_combat_classification_required": True,
            "combat_choreography_contract_true_overrides": True,
            "explicit_noncombat_overrides_negative_prompt_cues": True,
            "native_resolution_contract": self.native_resolution,
            "delivery_resolution_contract": self.native_resolution,
            "native_resolution_must_remain_honestly_labeled": True,
            "silent_upscale_forbidden": True,
        }

    def compile(self, package: dict[str, Any], workspace: Path) -> Path:
        policy = package.get("production_policy") or {}
        requested_model = str(policy.get("requested_model") or "")
        if requested_model != self.model:
            raise ModelCompilationError(
                f"compiler {self.adapter_id} cannot compile model {requested_model!r}"
            )

        episode = package.get("episode") or {}
        episode_number = int(episode["episode_number"])
        episode_code = f"E{episode_number:02d}"
        script = package.get("approved_script") or {}
        script_content = str(script.get("content") or "")
        if not script_content.strip():
            raise ModelCompilationError("approved script content is empty")

        inherited_assets = package.get("inherited_assets") or []
        asset_bindings = [
            {
                "asset_id": str(asset["id"]),
                "kind": str(asset["kind"]),
                "sha256": str((asset.get("metadata") or {}).get("sha256") or ""),
                "transport_state": (
                    "LOCAL_MANAGED_SOURCE"
                    if (asset.get("metadata") or {}).get("sha256")
                    else "LOCAL_SOURCE_DIGEST_MISSING"
                ),
            }
            for asset in inherited_assets
        ]
        prompt_source = {
            "approved_script_revision": int(script["revision"]),
            "approved_script_sha256": hashlib.sha256(
                script_content.encode("utf-8")
            ).hexdigest(),
            "continuity_snapshot_id": (package.get("continuity") or {}).get("id"),
            "resolved_library_count": len(package.get("resolved_library") or []),
        }
        provider_contract = self.provider_contract()
        compilation = {
            "schema_version": "nalu.qingshan-model-compilation/v1",
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "profile_id": self.profile_id,
            "model": self.model,
            "episode": episode_code,
            "episode_id": str(episode["id"]),
            "production_package_sha256": str(package["package_sha256"]),
            "prompt_source": prompt_source,
            "asset_bindings": asset_bindings,
            "provider_contract": provider_contract,
            "paid_boundary_contract": self.paid_boundary_contract(),
            "planning_defaults": {
                "aspect_ratio": "9:16",
                "native_resolution": self.native_resolution,
                "minimum_duration_seconds": self.minimum_duration_seconds,
                "maximum_duration_seconds": self.maximum_duration_seconds,
            },
            # Compilation is local and deterministic. It intentionally cannot become a
            # paid task until shot planning and provider asset transport add their own
            # sealed evidence through the durable submitter.
            "execution_state": "LOCAL_COMPILED_AWAITING_SHOT_PLAN",
            "paid_submission_enabled": False,
        }
        compilation["compilation_sha256"] = _canonical_sha256(compilation)
        target = (
            workspace
            / "workflow"
            / "compiled"
            / f"{episode_code}_{self.profile_id}_COMPILATION.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(compilation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target


class Seedance2ProCompiler(QingshanModelCompiler):
    adapter_id = "nalu.qingshan.seedance2-pro"
    profile_id = "SEEDANCE_2_STANDARD_GIGGLE"
    model = "seedance-2.0-pro"
    native_resolution = "720p"
    minimum_duration_seconds = 4

    def provider_contract(self) -> dict[str, Any]:
        return {
            "schema_version": "nalu.seedance2-pro-contract/v1",
            "generation_mode": "MULTI_REFERENCE_IMAGE_TO_VIDEO",
            "exact_first_frame": True,
            "exact_end_frame": False,
            "image_reference_transport": "PROVIDER_ASSET_ID_OR_PUBLIC_HTTPS",
            "audio_reference_transport": "PROVIDER_ASSET_ID_OR_PUBLIC_HTTPS",
            "dialogue_modes": [
                "MODEL_NATIVE_TEXT_DIALOGUE",
                "EXACT_LINE_AUDIO_REFERENCE",
            ],
            "release_upscale_required_above_native": True,
        }


class MiniMaxH3Compiler(QingshanModelCompiler):
    adapter_id = "nalu.qingshan.minimax-h3"
    profile_id = "MINIMAX_H3_GIGGLE"
    model = "MiniMax-H3"
    native_resolution = "768p"
    minimum_duration_seconds = 3

    def provider_contract(self) -> dict[str, Any]:
        return {
            "schema_version": "nalu.minimax-h3-contract/v1",
            "generation_mode": "OMNI_MULTIMODAL",
            "exact_first_frame": True,
            "exact_end_frame": True,
            "maximum_image_references": 9,
            "image_reference_transport": "PROVIDER_UPLOAD_OR_PUBLIC_HTTPS",
            "audio_video_reference_transport": "PUBLIC_HTTPS_ONLY",
            "dialogue_modes": ["PUBLIC_HTTPS_AUDIO_REFERENCE"],
            "fictional_identity_reference_policy": (
                "SYNTHETIC_FICTIONAL_CHARACTERS_ONLY"
            ),
            "release_upscale_required_above_native": True,
        }


class ModelCompilerRegistry:
    def __init__(self) -> None:
        compilers = (Seedance2ProCompiler(), MiniMaxH3Compiler())
        self._by_model = {compiler.model: compiler for compiler in compilers}

    @property
    def supported_models(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_model))

    def compiler_for(self, model: str) -> QingshanModelCompiler:
        try:
            return self._by_model[model]
        except KeyError as exc:
            raise ModelCompilationError(
                f"no registered Qingshan compiler for model {model!r}"
            ) from exc

    def compile(self, package: dict[str, Any], workspace: Path) -> Path:
        model = str((package.get("production_policy") or {}).get("requested_model") or "")
        return self.compiler_for(model).compile(package, workspace)

    def validate_paid_boundary_request(
        self, model: str, request: dict[str, Any]
    ) -> list[str]:
        """Validate immutable semantics immediately before a provider write."""
        try:
            compiler = self.compiler_for(model)
        except ModelCompilationError as exc:
            return [str(exc)]
        failures: list[str] = []
        if request.get("adapter_id") != compiler.adapter_id:
            failures.append("paid request adapter identity is missing or changed")
        if request.get("profile_id") != compiler.profile_id:
            failures.append("paid request profile identity is missing or changed")
        if request.get("model") != compiler.model:
            failures.append("paid request model identity is missing or changed")
        if request.get("provider_model_id") != compiler.model:
            failures.append("paid request provider model identity is missing or changed")
        duration = request.get("duration_seconds")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
        ):
            failures.append("paid request requires numeric duration_seconds")
        elif not compiler.minimum_duration_seconds <= duration <= compiler.maximum_duration_seconds:
            failures.append("paid request duration_seconds is outside provider limits")

        declarations = [
            request[name]
            for name in ("fight_or_chase", "combat_or_chase")
            if isinstance(request.get(name), bool)
        ]
        choreography = bool(request.get("combat_choreography_contract"))
        if not declarations and not choreography:
            failures.append("paid request requires explicit combat classification")
        elif declarations and any(value != declarations[0] for value in declarations):
            failures.append("paid request combat classifications disagree")
        elif choreography and declarations and declarations[0] is False:
            failures.append("combat choreography conflicts with noncombat classification")

        if request.get("native_resolution_contract") != compiler.native_resolution:
            failures.append("paid request native resolution contract is missing or changed")
        if request.get("delivery_resolution_contract") != compiler.native_resolution:
            failures.append("paid request delivery resolution contract is missing or changed")
        if request.get("native_resolution_must_remain_honestly_labeled") is not True:
            failures.append("paid request must preserve the honest native resolution label")
        if request.get("silent_upscale_forbidden") is not True:
            failures.append("paid request must explicitly forbid silent upscale")
        return failures

    def validate_upstream_registry(self, registry_path: Path) -> list[str]:
        """Prove Nalu's compiler contracts still match the pinned Qingshan registry."""
        try:
            upstream = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ["Qingshan video model capability registry is missing or invalid"]

        profiles = {
            str(profile.get("profile_id")): profile
            for profile in upstream.get("profiles") or []
        }
        allowed_profiles = set(
            (upstream.get("active_execution_policy") or {}).get(
                "allowed_paid_profile_ids"
            )
            or []
        )
        failures: list[str] = []
        for compiler in self._by_model.values():
            profile = profiles.get(compiler.profile_id)
            prefix = f"{compiler.profile_id}: "
            if profile is None:
                failures.append(prefix + "profile missing from pinned Qingshan registry")
                continue
            aliases = {str(value).casefold() for value in profile.get("aliases") or []}
            if compiler.model.casefold() not in aliases:
                failures.append(prefix + "requested model alias is no longer registered")
            if profile.get("adapter_status") != "DEPLOYED":
                failures.append(prefix + "adapter is not deployed")
            if profile.get("provider_model_id") != compiler.model:
                failures.append(prefix + "provider model ID changed")
            if compiler.profile_id not in allowed_profiles:
                failures.append(prefix + "profile is not allowed by active execution policy")
            limits = profile.get("provider_limits") or {}
            if compiler.native_resolution not in set(limits.get("resolution_values") or []):
                failures.append(prefix + "native resolution is outside provider limits")
            if limits.get("duration_seconds_min") != compiler.minimum_duration_seconds:
                failures.append(prefix + "minimum duration changed")
            if limits.get("duration_seconds_max") != compiler.maximum_duration_seconds:
                failures.append(prefix + "maximum duration changed")
            if isinstance(compiler, MiniMaxH3Compiler):
                maximum = compiler.provider_contract()["maximum_image_references"]
                if limits.get("omni_image_reference_max") != maximum:
                    failures.append(prefix + "maximum image reference count changed")
        return failures


def verify_compilation(path: Path, package: dict[str, Any]) -> list[str]:
    """Return fail-closed validation errors for a compiled model contract."""
    failures: list[str] = []
    try:
        compilation = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ["model compilation is missing or invalid JSON"]

    expected_digest = str(compilation.pop("compilation_sha256", ""))
    if not expected_digest or _canonical_sha256(compilation) != expected_digest:
        failures.append("model compilation digest mismatch")
    if compilation.get("production_package_sha256") != package.get("package_sha256"):
        failures.append("model compilation is bound to a different production package")
    requested_model = (package.get("production_policy") or {}).get("requested_model")
    if compilation.get("model") != requested_model:
        failures.append("model compilation does not match requested model")
    try:
        compiler = ModelCompilerRegistry().compiler_for(str(requested_model or ""))
    except ModelCompilationError:
        failures.append("model compilation has no registered compiler")
    else:
        expected_planning_defaults = {
            "aspect_ratio": "9:16",
            "native_resolution": compiler.native_resolution,
            "minimum_duration_seconds": compiler.minimum_duration_seconds,
            "maximum_duration_seconds": compiler.maximum_duration_seconds,
        }
        if compilation.get("adapter_id") != compiler.adapter_id:
            failures.append("model compilation adapter identity changed")
        if compilation.get("adapter_version") != compiler.adapter_version:
            failures.append("model compilation adapter version changed")
        if compilation.get("profile_id") != compiler.profile_id:
            failures.append("model compilation profile identity changed")
        if compilation.get("provider_contract") != compiler.provider_contract():
            failures.append("model compilation provider contract changed")
        if compilation.get("planning_defaults") != expected_planning_defaults:
            failures.append("model compilation planning defaults changed")
        if compilation.get("paid_boundary_contract") != compiler.paid_boundary_contract():
            failures.append("model compilation paid boundary contract changed")
    if compilation.get("paid_submission_enabled") is not False:
        failures.append("local model compilation must not enable paid submission")
    return failures
