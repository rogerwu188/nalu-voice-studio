from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from .models import Asset, AssetCreate, AssetKind, AudienceMode, ConsentScope
from .repository import ConflictError, Repository, new_id
from .secure_files import secure_directory, secure_file

MAX_ASSET_BYTES = 100 * 1024 * 1024


class AssetService:
    def __init__(self, repository: Repository, data_root: Path):
        self.repository = repository
        self.root = (data_root / "assets").resolve()
        secure_directory(data_root.resolve())
        secure_directory(self.root)

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
        directory = (self.root / project_id / asset_id).resolve()
        self._require_within(directory, self.root / project_id)
        directory.mkdir(parents=True, exist_ok=False)
        secure_directory(directory)
        destination = (directory / safe_filename).resolve()
        self._require_within(destination, directory)
        destination.write_bytes(content)
        secure_file(destination)
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
            shutil.rmtree(directory)
            raise ConflictError("asset consent metadata is incomplete") from exc
        try:
            return self.repository.create_asset(project_id, request, asset_id=asset_id)
        except Exception:
            shutil.rmtree(directory)
            raise

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
        self.repository.delete_asset_record(asset_id)
        if directory.is_dir():
            shutil.rmtree(directory)

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
            AssetKind.SCENE_REFERENCE: ("image/", "video/"),
            AssetKind.PROP_REFERENCE: ("image/", "video/"),
            AssetKind.STYLE_REFERENCE: ("image/", "video/"),
            AssetKind.SOURCE_DOCUMENT: (
                "text/", "image/", "application/pdf", "application/json",
            ),
        }
        if not any(content_type.lower().startswith(prefix) for prefix in allowed_prefixes[kind]):
            raise ConflictError(f"content type {content_type!r} is not allowed for {kind}")
