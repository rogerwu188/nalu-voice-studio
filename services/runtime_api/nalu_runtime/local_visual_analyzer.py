from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import urllib.parse
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

import av

from .models import LocalVisualAnalysisResult, PostproductionMaterializationResult
from .repository import utc_now
from .secure_files import publish_exclusive_text, secure_directory, secure_file
from .visual_continuity_qa import MINIMUM_CONFIDENCE, canonical_sha256


class LocalVisualAnalyzerError(RuntimeError):
    pass


class VisualAnalyzerRunner(Protocol):
    @property
    def model_sha256(self) -> str: ...

    @property
    def version(self) -> str: ...

    def analyze(self, request: dict[str, Any], working_directory: Path) -> dict[str, Any]: ...


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(root: Path, relative_path: str, expected_sha256: str) -> Path:
    relative = Path(relative_path)
    candidate = root / relative
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise LocalVisualAnalyzerError(
            f"visual analyzer input is missing: {relative_path}"
        ) from exc
    if (
        relative.is_absolute()
        or not relative.parts
        or candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(resolved_root)
    ):
        raise LocalVisualAnalyzerError(f"visual analyzer input is unsafe: {relative_path}")
    if file_sha256(resolved) != expected_sha256:
        raise LocalVisualAnalyzerError(f"visual analyzer input digest changed: {relative_path}")
    return resolved


def _managed_reference(data_root: Path, reference: dict[str, Any]) -> Path:
    parsed = urllib.parse.urlparse(str(reference.get("local_file_uri") or ""))
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise LocalVisualAnalyzerError("visual analyzer reference is not a managed local file URI")
    candidate = Path(urllib.parse.unquote(parsed.path))
    try:
        resolved_root = data_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise LocalVisualAnalyzerError("visual analyzer reference file is missing") from exc
    if (
        candidate.is_symlink()
        or not resolved.is_file()
        or not resolved.is_relative_to(resolved_root)
    ):
        raise LocalVisualAnalyzerError("visual analyzer reference escaped the local data root")
    if file_sha256(resolved) != reference.get("sha256"):
        raise LocalVisualAnalyzerError("visual analyzer reference digest changed")
    return resolved


def _timed_frames(path: Path) -> Iterator[tuple[float, av.VideoFrame]]:
    try:
        with av.open(str(path), mode="r") as container:
            if not container.streams.video:
                raise LocalVisualAnalyzerError("final master has no video stream")
            for frame in container.decode(container.streams.video[0]):
                if frame.time is not None:
                    yield float(frame.time), frame
                elif frame.pts is not None and frame.time_base is not None:
                    yield float(frame.pts * frame.time_base), frame
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise LocalVisualAnalyzerError(
            "final master could not be decoded for visual analysis"
        ) from exc


def _frame_sha256(frame: av.VideoFrame) -> str:
    gray = frame.reformat(format="gray8")
    plane = gray.planes[0]
    raw = bytes(plane)
    pixels = b"".join(
        raw[row * plane.line_size : row * plane.line_size + gray.width]
        for row in range(gray.height)
    )
    return hashlib.sha256(pixels).hexdigest()


def _write_png(frame: av.VideoFrame, path: Path) -> None:
    rgb = frame.reformat(format="rgb24")
    with av.open(str(path), mode="w", format="image2") as output:
        stream = output.add_stream("png", rate=1)
        stream.width = rgb.width
        stream.height = rgb.height
        stream.pix_fmt = "rgb24"
        rgb.pts = 0
        for packet in stream.encode(rgb):
            output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    secure_file(path)


def _sample_frames(
    master_path: Path, shots: list[dict[str, Any]], stage: Path
) -> list[dict[str, Any]]:
    targets: list[tuple[float, dict[str, Any]]] = []
    previous_end = 0.0
    for shot in shots:
        start = shot.get("timeline_start_seconds")
        duration = shot.get("duration_seconds")
        if (
            not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(duration, (int, float))
            or isinstance(duration, bool)
            or float(start) < previous_end - 0.05
            or float(duration) <= 0
        ):
            raise LocalVisualAnalyzerError("postproduction shot timeline is invalid")
        start_value = float(start)
        end_value = start_value + float(duration)
        previous_end = end_value
        targets.append((start_value + float(duration) / 2, shot))

    iterator = iter(_timed_frames(master_path))
    previous: tuple[float, av.VideoFrame] | None = None
    try:
        current: tuple[float, av.VideoFrame] | None = next(iterator)
    except StopIteration as exc:
        raise LocalVisualAnalyzerError("final master has no timed video frames") from exc
    samples: list[dict[str, Any]] = []
    for target, shot in targets:
        while current is not None and current[0] < target:
            previous = current
            try:
                current = next(iterator)
            except StopIteration:
                current = None
        candidates = [candidate for candidate in (previous, current) if candidate is not None]
        if not candidates:
            raise LocalVisualAnalyzerError("final master does not cover the authored shot timeline")
        selected_time, selected_frame = min(
            candidates, key=lambda candidate: abs(candidate[0] - target)
        )
        if abs(selected_time - target) > 0.25:
            raise LocalVisualAnalyzerError("final master has no frame near the shot midpoint")
        shot_id = str(shot.get("shot_id") or "")
        if not shot_id:
            raise LocalVisualAnalyzerError("postproduction shot ID is missing")
        frame_path = stage / f"{len(samples) + 1:04d}-{shot_id}.png"
        _write_png(selected_frame, frame_path)
        samples.append(
            {
                "shot_id": shot_id,
                "start_seconds": round(float(shot["timeline_start_seconds"]), 6),
                "end_seconds": round(
                    float(shot["timeline_start_seconds"]) + float(shot["duration_seconds"]),
                    6,
                ),
                "time_seconds": round(selected_time, 6),
                "frame_sha256": _frame_sha256(selected_frame),
                "image_path": str(frame_path),
            }
        )
    return samples


class AppleVisionAnalyzer:
    def __init__(self, binary_path: Path | None, timeout_seconds: int = 180):
        self.binary_path = binary_path.resolve() if binary_path else None
        self.timeout_seconds = timeout_seconds

    @property
    def model_sha256(self) -> str:
        if self.binary_path is None or not self.binary_path.is_file():
            raise LocalVisualAnalyzerError("packaged Apple Vision analyzer is unavailable")
        return file_sha256(self.binary_path)

    @property
    def version(self) -> str:
        return "nalu.apple-vision-perceptual-baseline/v1"

    def analyze(self, request: dict[str, Any], working_directory: Path) -> dict[str, Any]:
        if (
            self.binary_path is None
            or not self.binary_path.is_file()
            or not os.access(self.binary_path, os.X_OK)
        ):
            raise LocalVisualAnalyzerError("packaged Apple Vision analyzer is unavailable")
        encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        environment = {
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(working_directory),
            "LANG": "en_US.UTF-8",
        }
        try:
            completed = subprocess.run(
                [str(self.binary_path)],
                input=encoded,
                capture_output=True,
                cwd=working_directory,
                env=environment,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LocalVisualAnalyzerError("Apple Vision analyzer could not complete") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace")[:1000]
            raise LocalVisualAnalyzerError(f"Apple Vision analyzer failed: {detail}")
        if len(completed.stdout) > 4 * 1024 * 1024:
            raise LocalVisualAnalyzerError("Apple Vision analyzer output exceeded the safety limit")
        try:
            response = json.loads(completed.stdout)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise LocalVisualAnalyzerError("Apple Vision analyzer returned invalid JSON") from exc
        if response.get("schema_version") != "nalu.apple-vision-measurements/v1":
            raise LocalVisualAnalyzerError("Apple Vision analyzer returned an unsupported schema")
        if response.get("local_analysis") is not True:
            raise LocalVisualAnalyzerError("Apple Vision analyzer did not attest local execution")
        return response


def _distance_confidence(value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - float(value) / 20.0)), 6)


def _confidence(value: Any) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _check(
    *,
    domain: str,
    expected: str,
    observed: str,
    confidence: float,
    frame_sha256: str,
    subject_id: str | None = None,
    confirmed_revision: int | None = None,
    measurement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    passed = expected == observed and confidence >= MINIMUM_CONFIDENCE[domain]
    result: dict[str, Any] = {
        "domain": domain,
        "expected": expected,
        "observed": observed,
        "confidence": round(confidence, 6),
        "source_frame_sha256": frame_sha256,
        "status": "PASS" if passed else "FAIL",
        "machine_measurement": measurement or {},
    }
    if subject_id:
        result["subject_id"] = subject_id
    if confirmed_revision is not None:
        result["confirmed_revision"] = confirmed_revision
    return result


def _manifest_from_measurements(
    *,
    run_id: str,
    package_sha256: str,
    resolved_library_sha256: str,
    master_sha256: str,
    inputs: dict[str, Any],
    samples: list[dict[str, Any]],
    response: dict[str, Any],
    analyzer: VisualAnalyzerRunner,
    analyzer_model_sha256: str,
) -> tuple[dict[str, Any], str, list[str]]:
    rows = response.get("shots")
    if not isinstance(rows, list) or len(rows) != len(samples):
        raise LocalVisualAnalyzerError(
            "Apple Vision analyzer returned incomplete shot measurements"
        )
    rows_by_id = {str(row.get("shot_id") or ""): row for row in rows if isinstance(row, dict)}
    if len(rows_by_id) != len(samples):
        raise LocalVisualAnalyzerError("Apple Vision analyzer returned duplicate shot measurements")
    subject_inputs = {str(item["entity_id"]): item for item in inputs["subjects"]}
    prop_inputs = {str(item["entity_id"]): item for item in inputs["prop_references"]}
    manifest_shots: list[dict[str, Any]] = []
    failures: list[str] = []
    for sample in samples:
        row = rows_by_id.get(sample["shot_id"])
        if row is None or row.get("frame_sha256") != sample["frame_sha256"]:
            raise LocalVisualAnalyzerError("Apple Vision analyzer frame binding is invalid")
        measurements = row.get("subjects")
        if not isinstance(measurements, list):
            raise LocalVisualAnalyzerError("Apple Vision analyzer subject measurements are invalid")
        measurements_by_id = {
            str(item.get("entity_id") or ""): item
            for item in measurements
            if isinstance(item, dict)
        }
        if set(measurements_by_id) != set(subject_inputs):
            raise LocalVisualAnalyzerError("Apple Vision analyzer subject set is incomplete")
        checks: list[dict[str, Any]] = []
        for entity_id, subject in subject_inputs.items():
            measurement = measurements_by_id[entity_id]
            expected = subject["expected"]
            identity_confidence = _distance_confidence(measurement.get("identity_distance"))
            identity_name = str(expected["identity"])
            checks.append(
                _check(
                    domain="identity",
                    expected=identity_name,
                    observed=(identity_name if identity_confidence >= 0.85 else "unmatched"),
                    confidence=identity_confidence,
                    frame_sha256=sample["frame_sha256"],
                    subject_id=entity_id,
                    confirmed_revision=subject["confirmed_revision"],
                    measurement={"feature_print_distance": measurement.get("identity_distance")},
                )
            )
            detected_color = str(measurement.get("dominant_color") or "unknown")
            color_confidence = _confidence(measurement.get("color_confidence"))
            for wardrobe in expected["wardrobe"]:
                target = str(wardrobe)
                observed = target if detected_color in target else detected_color
                checks.append(
                    _check(
                        domain="wardrobe",
                        expected=target,
                        observed=observed,
                        confidence=color_confidence,
                        frame_sha256=sample["frame_sha256"],
                        subject_id=entity_id,
                        confirmed_revision=subject["confirmed_revision"],
                        measurement={"dominant_color": detected_color},
                    )
                )
            axis = str(measurement.get("space_axis") or "unknown")
            axis_confidence = _confidence(measurement.get("axis_confidence"))
            checks.append(
                _check(
                    domain="space_axis",
                    expected=str(expected["space_axis"]),
                    observed=axis,
                    confidence=axis_confidence,
                    frame_sha256=sample["frame_sha256"],
                    measurement={"subject_center_x": measurement.get("subject_center_x")},
                )
            )
            pose = str(measurement.get("pose") or "unknown")
            pose_confidence = _confidence(measurement.get("pose_confidence"))
            checks.append(
                _check(
                    domain="pose",
                    expected=str(expected["pose"]),
                    observed=pose,
                    confidence=pose_confidence,
                    frame_sha256=sample["frame_sha256"],
                    measurement={"body_joint_count": measurement.get("body_joint_count")},
                )
            )
            expected_props = [str(item) for item in expected["props"]]
            prop_distances = measurement.get("prop_distances") or {}
            if not isinstance(prop_distances, dict):
                raise LocalVisualAnalyzerError("Apple Vision prop measurements are invalid")
            if expected_props:
                props_by_name = {str(item["stable_name"]): item for item in prop_inputs.values()}
                for expected_prop in expected_props:
                    prop = props_by_name.get(expected_prop)
                    if prop is None:
                        raise LocalVisualAnalyzerError(
                            "analyzer input lost a required prop authority"
                        )
                    prop_id = str(prop["entity_id"])
                    distance = prop_distances.get(prop_id)
                    confidence = _distance_confidence(distance)
                    checks.append(
                        _check(
                            domain="props",
                            expected=expected_prop,
                            observed=(expected_prop if confidence >= 0.80 else "unmatched"),
                            confidence=confidence,
                            frame_sha256=sample["frame_sha256"],
                            subject_id=prop_id,
                            confirmed_revision=prop["confirmed_revision"],
                            measurement={"feature_print_distance": distance},
                        )
                    )
            else:
                checks.append(
                    _check(
                        domain="props",
                        expected="none",
                        observed="none",
                        confidence=1.0,
                        frame_sha256=sample["frame_sha256"],
                        measurement={"expected_prop_count": 0},
                    )
                )
        failed_domains = sorted({check["domain"] for check in checks if check["status"] == "FAIL"})
        failures.extend(f"{sample['shot_id']}:{domain}" for domain in failed_domains)
        manifest_shots.append(
            {
                "shot_id": sample["shot_id"],
                "start_seconds": sample["start_seconds"],
                "end_seconds": sample["end_seconds"],
                "evidence_frames": [
                    {
                        "time_seconds": sample["time_seconds"],
                        "frame_sha256": sample["frame_sha256"],
                    }
                ],
                "checks": checks,
            }
        )
    generated_at = utc_now()
    body = {
        "schema_version": "nalu.visual-continuity-manifest/v1",
        "run_id": run_id,
        "production_package_sha256": package_sha256,
        "final_master_sha256": master_sha256,
        "resolved_library_sha256": resolved_library_sha256,
        "analyzer_inputs_sha256": inputs["inputs_sha256"],
        "analyzer": {
            "analyzer_id": "nalu-apple-vision-local",
            "version": analyzer.version,
            "model_sha256": analyzer_model_sha256,
            "local_analysis": True,
            "provider_upload_performed": False,
            "generated_at": generated_at,
        },
        "required_domains": ["identity", "wardrobe", "space_axis", "pose", "props"],
        "shots": manifest_shots,
    }
    return {**body, "manifest_sha256": canonical_sha256(body)}, generated_at, failures


def execute_local_visual_analysis(
    *,
    run_id: str,
    project_id: str,
    episode_id: str,
    data_root: Path,
    run_directory: Path,
    analyzer: VisualAnalyzerRunner,
) -> LocalVisualAnalysisResult:
    workspace = run_directory / "qingshan-workspace"
    exports = workspace / "exports"
    result_paths = list((exports / "materialized").glob("*/materialization-result.json"))
    if len(result_paths) != 1:
        raise LocalVisualAnalyzerError(
            "local visual analysis requires one materialized final master"
        )
    if result_paths[0].is_symlink():
        raise LocalVisualAnalyzerError("postproduction materialization result is unsafe")
    try:
        materialization = PostproductionMaterializationResult.model_validate_json(
            result_paths[0].read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise LocalVisualAnalyzerError("postproduction materialization result is invalid") from exc
    materialization_body = materialization.model_dump(mode="json", exclude={"result_sha256"})
    if canonical_sha256(materialization_body) != materialization.result_sha256:
        raise LocalVisualAnalyzerError("postproduction materialization result digest changed")
    master = _regular_file(
        exports, materialization.master["relative_path"], materialization.master["sha256"]
    )
    postproduction_manifest_path = _regular_file(
        exports,
        materialization.postproduction_manifest["relative_path"],
        materialization.postproduction_manifest["sha256"],
    )
    task_paths = list((workspace / "workflow" / "tasks").glob("*_PRODUCTION_TASK.json"))
    if len(task_paths) != 1:
        raise LocalVisualAnalyzerError("visual analyzer production task is missing or ambiguous")
    if task_paths[0].is_symlink():
        raise LocalVisualAnalyzerError("visual analyzer production task is unsafe")
    try:
        task = json.loads(task_paths[0].read_text(encoding="utf-8"))
        local_visual = task["local_visual_analysis"]
        inputs_relative = Path(str(local_visual["inputs_path"]))
        inputs_candidate = workspace / inputs_relative
        resolved_workspace = workspace.resolve(strict=True)
        inputs_path = inputs_candidate.resolve(strict=True)
        if (
            inputs_relative.is_absolute()
            or not inputs_relative.parts
            or inputs_candidate.is_symlink()
            or not inputs_path.is_file()
            or not inputs_path.is_relative_to(resolved_workspace)
        ):
            raise LocalVisualAnalyzerError("visual analyzer input contract path is unsafe")
        inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LocalVisualAnalyzerError("visual analyzer input contract is unreadable") from exc
    inputs_body = {key: value for key, value in inputs.items() if key != "inputs_sha256"}
    if canonical_sha256(inputs_body) != inputs.get("inputs_sha256") or local_visual.get(
        "inputs_sha256"
    ) != inputs.get("inputs_sha256"):
        raise LocalVisualAnalyzerError("visual analyzer input contract digest changed")
    if inputs.get("readiness") != "READY" or inputs.get("unresolved"):
        raise LocalVisualAnalyzerError("visual analyzer inputs are BLOCKED")
    if (
        inputs.get("provider_upload_allowed") is not False
        or inputs.get("local_execution_only") is not True
    ):
        raise LocalVisualAnalyzerError("visual analyzer input privacy boundary is invalid")
    try:
        postproduction_manifest = json.loads(
            postproduction_manifest_path.read_text(encoding="utf-8")
        )
        shots = postproduction_manifest["timeline"]["selected_shots"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LocalVisualAnalyzerError("postproduction shot timeline is unreadable") from exc
    if not isinstance(shots, list) or not shots:
        raise LocalVisualAnalyzerError("postproduction shot timeline is empty")

    subjects = inputs.get("subjects")
    prop_references = inputs.get("prop_references")
    if not isinstance(subjects, list) or not subjects:
        raise LocalVisualAnalyzerError("visual analyzer character subjects are missing")
    if not isinstance(prop_references, list):
        raise LocalVisualAnalyzerError("visual analyzer prop references are invalid")

    reference_payload: list[dict[str, Any]] = []
    for subject in [*subjects, *prop_references]:
        references = []
        for reference in subject["references"]:
            path = _managed_reference(data_root, reference)
            references.append(
                {
                    "asset_id": reference["asset_id"],
                    "sha256": reference["sha256"],
                    "image_path": str(path),
                }
            )
        reference_payload.append(
            {
                "entity_id": subject["entity_id"],
                "kind": "character" if "expected" in subject else "prop",
                "references": references,
            }
        )

    stage = run_directory / f".local-visual-analysis-{os.getpid()}-{os.urandom(6).hex()}"
    secure_directory(stage)
    try:
        analyzer_model_sha256 = analyzer.model_sha256
        samples = _sample_frames(master, shots, stage)
        request = {
            "schema_version": "nalu.apple-vision-request/v1",
            "frames": [
                {
                    "shot_id": item["shot_id"],
                    "frame_sha256": item["frame_sha256"],
                    "image_path": item["image_path"],
                }
                for item in samples
            ],
            "subjects": reference_payload,
        }
        response = analyzer.analyze(request, stage)
        manifest, created_at, failures = _manifest_from_measurements(
            run_id=run_id,
            package_sha256=materialization.production_package_sha256,
            resolved_library_sha256=inputs["resolved_library_sha256"],
            master_sha256=materialization.master["sha256"],
            inputs=inputs,
            samples=samples,
            response=response,
            analyzer=analyzer,
            analyzer_model_sha256=analyzer_model_sha256,
        )
        if analyzer.model_sha256 != analyzer_model_sha256:
            raise LocalVisualAnalyzerError("Apple Vision analyzer binary changed during execution")
    finally:
        if stage.exists():
            shutil.rmtree(stage)

    output_relative = Path(materialization.output_root_relative_path)
    output_root = exports / output_relative
    try:
        resolved_exports = exports.resolve(strict=True)
        resolved_output_root = output_root.resolve(strict=True)
    except OSError as exc:
        raise LocalVisualAnalyzerError("materialized visual output directory is missing") from exc
    if (
        output_relative.is_absolute()
        or not output_relative.parts
        or output_root.is_symlink()
        or not resolved_output_root.is_dir()
        or not resolved_output_root.is_relative_to(resolved_exports)
    ):
        raise LocalVisualAnalyzerError("materialized visual output directory is unsafe")
    episode_code = task_paths[0].name.split("_", 1)[0]
    manifest_path = output_root / f"{episode_code}_VISUAL_CONTINUITY.json"
    encoded_manifest = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists():
        if (
            manifest_path.is_symlink()
            or manifest_path.read_text(encoding="utf-8") != encoded_manifest
        ):
            raise LocalVisualAnalyzerError(
                "local visual analysis already exists with different evidence"
            )
    else:
        publish_exclusive_text(manifest_path, encoded_manifest)
    artifact = {
        "kind": "visual_continuity_manifest",
        "relative_path": str(manifest_path.relative_to(exports)),
        "media_type": "application/json",
        "sha256": file_sha256(manifest_path),
        "byte_size": manifest_path.stat().st_size,
    }
    body = {
        "schema_version": "nalu.local-visual-analysis/v1",
        "run_id": run_id,
        "project_id": project_id,
        "episode_id": episode_id,
        "production_package_sha256": materialization.production_package_sha256,
        "inputs_sha256": inputs["inputs_sha256"],
        "master_sha256": materialization.master["sha256"],
        "analyzer_model_sha256": analyzer_model_sha256,
        "manifest": artifact,
        "status": "FAIL" if failures else "PASS",
        "failures": failures,
        "analyzed_shot_count": len(samples),
        "provider_upload_performed": False,
        "created_at": created_at,
    }
    return LocalVisualAnalysisResult(**body, result_sha256=canonical_sha256(body))
