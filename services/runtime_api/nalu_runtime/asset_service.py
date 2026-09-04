from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from .models import Asset, AssetCreate, AssetKind, AudienceMode, ConsentScope
from .repository import ConflictError, NotFoundError, Repository, new_id
from .secure_files import secure_directory

MAX_ASSET_BYTES = 100 * 1024 * 1024


class AssetService:
    IMPORT_MARKER = ".nalu-asset-import.pending.json"

    def __init__(self, repository: Repository, data_root: Path):
        self.repository = repository
        self.root = (data_root / "assets").resolve()
        secure_directory(data_root.resolve())
        secure_directory(self.root)
        self._recover_interrupted_imports()

    @staticmethod
    def _sync_directory(path: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise ConflictError("managed asset directory is unsafe")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _write_synced_file(path: Path, content: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ConflictError("managed asset file is unsafe")
            written = 0
            while written < len(content):
                count = os.write(descriptor, content[written:])
                if count <= 0:
                    raise ConflictError("managed asset write was incomplete")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _after_asset_promotion(_directory: Path) -> None:
        """Crash-test seam after managed bytes become durable but before SQLite commit."""

    @staticmethod
    def _after_asset_database_commit(_asset: Asset) -> None:
        """Crash-test seam after SQLite commit but before import-marker cleanup."""

    @staticmethod
    def _after_asset_retirement(_directory: Path) -> None:
        """Crash-test seam after managed bytes become private but before SQLite deletion."""

    @staticmethod
    def _after_asset_database_deletion(_directory: Path) -> None:
        """Crash-test seam after SQLite deletion but before managed-byte removal."""

    def _recover_interrupted_imports(self) -> None:
        for project_directory in self.root.iterdir():
            if project_directory.is_symlink() or not project_directory.is_dir():
                raise ConflictError("managed asset project directory is unsafe")
            for candidate in list(project_directory.iterdir()):
                if candidate.name.startswith(".ast_") and candidate.name.endswith(".deleting"):
                    if candidate.is_symlink() or not candidate.is_dir():
                        raise ConflictError("managed asset deletion stage is unsafe")
                    asset_id = candidate.name[1 : -len(".deleting")]
                    final_directory = project_directory / asset_id
                    try:
                        asset = self.repository.get_asset(asset_id)
                    except NotFoundError:
                        shutil.rmtree(candidate)
                    else:
                        if (
                            final_directory.exists()
                            or final_directory.is_symlink()
                            or asset.project_id != project_directory.name
                        ):
                            raise ConflictError("managed asset deletion recovery binding changed")
                        os.rename(candidate, final_directory)
                    self._sync_directory(project_directory)
                    continue
                if candidate.name.startswith(".ast_") and candidate.name.endswith(".pending"):
                    if candidate.is_symlink() or not candidate.is_dir():
                        raise ConflictError("managed asset staging directory is unsafe")
                    shutil.rmtree(candidate)
                    self._sync_directory(project_directory)
                    continue
                if candidate.is_symlink() or not candidate.is_dir():
                    continue
                marker = candidate / self.IMPORT_MARKER
                if not marker.exists() and not marker.is_symlink():
                    continue
                if marker.is_symlink() or not marker.is_file():
                    raise ConflictError("managed asset import marker is unsafe")
                try:
                    recovery = json.loads(marker.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise ConflictError("managed asset import marker is invalid") from exc
                if (
                    recovery.get("schema_version") != "nalu.asset-import-recovery/v1"
                    or recovery.get("asset_id") != candidate.name
                    or recovery.get("project_id") != project_directory.name
                ):
                    raise ConflictError("managed asset import marker binding changed")
                filename = recovery.get("filename")
                if not isinstance(filename, str) or Path(filename).name != filename:
                    raise ConflictError("managed asset import filename is unsafe")
                destination = candidate / filename
                try:
                    asset = self.repository.get_asset(candidate.name)
                except NotFoundError:
                    shutil.rmtree(candidate)
                    self._sync_directory(project_directory)
                    continue
                if (
                    destination.is_symlink()
                    or not destination.is_file()
                    or asset.project_id != project_directory.name
                    or asset.local_uri != destination.resolve().as_uri()
                    or hashlib.sha256(destination.read_bytes()).hexdigest()
                    != recovery.get("sha256")
                    or asset.metadata.get("sha256") != recovery.get("sha256")
                    or asset.metadata.get("byte_size") != recovery.get("byte_size")
                ):
                    raise ConflictError("committed managed asset failed recovery verification")
                marker.unlink()
                self._sync_directory(candidate)

    def import_bytes(
        self,
        project_id: str,
        *,
        content: bytes,
        filename: str,
        content_type: str,
        kind: AssetKind,
        name: str,
        subject_name: str,
        season_id: str | None,
        episode_id: str | None,
        consent_granted: bool,
        consent_scope: ConsentScope,
        guardian_approved: bool,
        consent_granted_by: str,
        consent_statement: str,
    ) -> Asset:
        project = self.repository.get_project(project_id)
        if not content or len(content) > MAX_ASSET_BYTES:
            raise ConflictError("asset must contain 1 byte to 100 MB")
        safe_filename = self._safe_filename(filename)
        self._validate_content_type(kind, content_type)
        if (
            project.audience_mode == AudienceMode.CHILD
            and kind in {AssetKind.CHARACTER_IMAGE, AssetKind.VOICE_REFERENCE}
            and not guardian_approved
        ):
            raise ConflictError("child biometric assets require guardian approval")
        asset_id = new_id("ast")
        project_directory = (self.root / project_id).resolve()
        self._require_within(project_directory, self.root)
        secure_directory(project_directory)
        directory = (project_directory / asset_id).resolve()
        staging = (project_directory / f".{asset_id}.pending").resolve()
        self._require_within(directory, project_directory)
        self._require_within(staging, project_directory)
        destination = (directory / safe_filename).resolve()
        self._require_within(destination, directory)
        digest = hashlib.sha256(content).hexdigest()
        try:
            request = AssetCreate(
                kind=kind,
                name=name,
                local_uri=destination.as_uri(),
                subject_name=subject_name,
                season_id=season_id,
                episode_id=episode_id,
                metadata={
                    "sha256": digest,
                    "byte_size": len(content),
                    "content_type": content_type,
                    "original_filename": safe_filename,
                    "storage": "nalu-managed-local-copy/v1",
                },
                consent_granted=consent_granted,
                consent_scope=consent_scope,
                guardian_approved=guardian_approved,
                consent_granted_by=consent_granted_by,
                consent_statement=consent_statement,
            )
        except ValidationError as exc:
            raise ConflictError("asset consent metadata is incomplete") from exc
        staging.mkdir(mode=0o700)
        staged_destination = staging / safe_filename
        marker = staging / self.IMPORT_MARKER
        recovery = {
            "schema_version": "nalu.asset-import-recovery/v1",
            "asset_id": asset_id,
            "project_id": project_id,
            "filename": safe_filename,
            "sha256": digest,
            "byte_size": len(content),
        }
        self._write_synced_file(staged_destination, content)
        self._write_synced_file(
            marker,
            (json.dumps(recovery, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
        )
        self._sync_directory(staging)
        os.rename(staging, directory)
        self._sync_directory(project_directory)
        self._after_asset_promotion(directory)
        try:
            asset = self.repository.create_asset(project_id, request, asset_id=asset_id)
        except Exception:
            try:
                self.repository.get_asset(asset_id)
            except NotFoundError:
                shutil.rmtree(directory)
                self._sync_directory(project_directory)
            raise
        self._after_asset_database_commit(asset)
        (directory / self.IMPORT_MARKER).unlink()
        self._sync_directory(directory)
        return asset

    def register_existing(self, project_id: str, request: AssetCreate) -> Asset:
        project = self.repository.get_project(project_id)
        if (
            project.audience_mode == AudienceMode.CHILD
            and request.kind in {AssetKind.CHARACTER_IMAGE, AssetKind.VOICE_REFERENCE}
            and not request.guardian_approved
        ):
            raise ConflictError("child biometric assets require guardian approval")
        path = self._managed_path(project_id, request.local_uri)
        if not path.is_file():
            raise ConflictError("asset path is not a managed local file")
        return self.repository.create_asset(project_id, request)

    def delete_asset(self, asset_id: str) -> None:
        asset = self.repository.get_asset(asset_id)
        report = self.repository.asset_dependency_report(asset_id)
        if not report.can_delete:
            raise ConflictError(report.explanation)
        path = self._managed_path(asset.project_id, asset.local_uri)
        directory = path.parent
        project_directory = directory.parent
        deleting = project_directory / f".{asset.id}.deleting"
        if (
            directory.is_symlink()
            or not directory.is_dir()
            or path.is_symlink()
            or not path.is_file()
            or deleting.exists()
            or deleting.is_symlink()
        ):
            raise ConflictError("managed asset deletion path is unsafe")
        os.rename(directory, deleting)
        self._sync_directory(project_directory)
        self._after_asset_retirement(deleting)
        try:
            self.repository.delete_asset_record(asset_id)
        except Exception:
            if not directory.exists() and deleting.is_dir():
                os.rename(deleting, directory)
                self._sync_directory(project_directory)
            raise
        self._after_asset_database_deletion(deleting)
        shutil.rmtree(deleting)
        self._sync_directory(project_directory)

    def _managed_path(self, project_id: str, local_uri: str) -> Path:
        parsed = urlparse(local_uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise ConflictError("asset URI must be a managed local file")
        path = Path(unquote(parsed.path)).resolve()
        self._require_within(path, self.root / project_id)
        return path

    def managed_path(self, project_id: str, local_uri: str) -> Path:
        return self._managed_path(project_id, local_uri)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        cleaned = unquote(filename).strip()
        if (
            not cleaned
            or cleaned in {".", ".."}
            or "/" in cleaned
            or "\\" in cleaned
            or "\x00" in cleaned
            or Path(cleaned).name != cleaned
        ):
            raise ConflictError("asset filename contains an unsafe path")
        return cleaned[:180]

    @staticmethod
    def _require_within(path: Path, root: Path) -> None:
        resolved_root = root.resolve()
        if not path.is_relative_to(resolved_root):
            raise ConflictError("asset path escapes Nalu local storage")

    @staticmethod
    def _validate_content_type(kind: AssetKind, content_type: str) -> None:
        allowed_prefixes = {
            AssetKind.CHARACTER_IMAGE: ("image/",),
            AssetKind.VOICE_REFERENCE: ("audio/",),
            AssetKind.ARCHIVE_AUDIO: ("audio/",),
            AssetKind.ARCHIVE_VIDEO: ("video/",),
            AssetKind.SCENE_REFERENCE: ("image/", "video/"),
            AssetKind.PROP_REFERENCE: ("image/", "video/"),
            AssetKind.STYLE_REFERENCE: ("image/", "video/"),
            AssetKind.SOURCE_DOCUMENT: (
                "text/", "image/", "application/pdf", "application/json",
            ),
        }
        if not any(content_type.lower().startswith(prefix) for prefix in allowed_prefixes[kind]):
            raise ConflictError(f"content type {content_type!r} is not allowed for {kind}")
