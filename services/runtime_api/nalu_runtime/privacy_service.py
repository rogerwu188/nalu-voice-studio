from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from .asset_service import AssetService
from .models import ProjectDeletionRequest, ProjectDeletionResult
from .repository import ConflictError, NotFoundError, Repository, encode, new_id, utc_now
from .secure_files import secure_directory, secure_file


class ProjectPrivacyService:
    def __init__(
        self, repository: Repository, asset_service: AssetService, data_root: Path
    ):
        self.repository = repository
        self.asset_service = asset_service
        self.data_root = data_root.resolve()

    def create_privacy_export(self, project_id: str) -> Path:
        backup = self.repository.export_project(project_id).model_dump(mode="json")
        media_manifest: list[dict[str, object]] = []
        media_files: list[tuple[Path, str]] = []
        for asset in backup["payload"]["assets"]:
            source = self.asset_service.managed_path(project_id, asset["local_uri"])
            if not source.is_file():
                raise ConflictError("privacy export found a missing managed asset file")
            archive_path = f"media/{asset['id']}/{source.name}"
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            media_manifest.append(
                {
                    "asset_id": asset["id"],
                    "archive_path": archive_path,
                    "sha256": digest,
                    "byte_size": source.stat().st_size,
                }
            )
            media_files.append((source, archive_path))
            asset["local_uri"] = f"nalu-bundle://{archive_path}"
        canonical = encode(backup["payload"])
        backup["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()

        export_root = self.data_root / "privacy-exports"
        secure_directory(export_root)
        destination = export_root / f"{project_id}-{new_id('privacy')}.zip"
        manifest = {
            "schema_version": "nalu.privacy-export/v1",
            "project_id": project_id,
            "created_at": utc_now(),
            "database_included": False,
            "secret_material_included": False,
            "media": media_manifest,
        }
        with zipfile.ZipFile(
            destination, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr(
                "project-export.json",
                json.dumps(backup, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            )
            archive.writestr(
                "privacy-manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            )
            for source, archive_path in media_files:
                archive.write(source, archive_path)
        secure_file(destination)
        return destination

    def delete_project(
        self, project_id: str, request: ProjectDeletionRequest
    ) -> ProjectDeletionResult:
        preview = self.repository.project_deletion_preview(project_id)
        run_ids = self.repository.project_run_ids(project_id)
        if request.confirmation_title != preview.project_title:
            raise ConflictError("project title confirmation does not match")
        if run_ids and not request.delete_production_snapshots:
            raise ConflictError("immutable production snapshot deletion was not confirmed")

        targets = [self.data_root / "assets" / project_id]
        targets.extend(self.data_root / "runs" / run_id for run_id in run_ids)
        export_root = self.data_root / "privacy-exports"
        if export_root.is_dir():
            targets.extend(export_root.glob(f"{project_id}-*.zip"))
        staging = self.data_root / "deletion-staging" / new_id("delete")
        staging.mkdir(parents=True, exist_ok=False)
        secure_directory(staging)
        moved: list[tuple[Path, Path]] = []
        try:
            for index, target in enumerate(targets):
                resolved = target.resolve()
                if not resolved.is_relative_to(self.data_root):
                    raise ConflictError("project deletion target escaped local storage")
                if not resolved.exists():
                    continue
                staged = staging / f"{index}-{resolved.name}"
                resolved.rename(staged)
                moved.append((staged, resolved))
            asset_count, run_count = self.repository.delete_project_records(
                project_id, request
            )
        except Exception:
            for staged, original in reversed(moved):
                secure_directory(original.parent)
                staged.rename(original)
            shutil.rmtree(staging)
            raise
        shutil.rmtree(staging)
        try:
            self.repository.get_project(project_id)
        except NotFoundError:
            verified_absent = all(not original.exists() for _, original in moved)
        else:
            verified_absent = False
        return ProjectDeletionResult(
            project_id=project_id,
            deleted=True,
            removed_asset_count=asset_count,
            removed_production_run_count=run_count,
            verified_absent=verified_absent,
        )
