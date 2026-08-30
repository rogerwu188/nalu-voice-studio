from __future__ import annotations

import shutil
from pathlib import Path

from .models import StorageDiagnostics

GIB = 1024**3
MINIMUM_PRODUCTION_RESERVE_BYTES = 5 * GIB
RECOMMENDED_FREE_BYTES = 20 * GIB


def inspect_storage(data_root: Path, database_path: Path) -> StorageDiagnostics:
    probe = data_root if data_root.exists() else data_root.parent
    usage = shutil.disk_usage(probe)
    database_bytes = database_path.stat().st_size if database_path.is_file() else 0
    if usage.free < MINIMUM_PRODUCTION_RESERVE_BYTES:
        status = "critical"
        explanation = "本机可用空间不足，开始新的视频制作前请先清理磁盘。Nalu 不会自动删除素材。"
        can_start_new_production = False
    elif usage.free < RECOMMENDED_FREE_BYTES:
        status = "warning"
        explanation = "本机空间偏少，长视频或多集制作前建议先清理磁盘。Nalu 不会自动删除素材。"
        can_start_new_production = True
    else:
        status = "healthy"
        explanation = "本机空间充足，可以继续整理和制作。"
        can_start_new_production = True
    return StorageDiagnostics(
        status=status,
        available_bytes=usage.free,
        total_bytes=usage.total,
        database_bytes=database_bytes,
        minimum_production_reserve_bytes=MINIMUM_PRODUCTION_RESERVE_BYTES,
        recommended_free_bytes=RECOMMENDED_FREE_BYTES,
        can_start_new_production=can_start_new_production,
        explanation=explanation,
    )
