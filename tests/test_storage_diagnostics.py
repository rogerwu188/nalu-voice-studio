from pathlib import Path
from types import SimpleNamespace

from nalu_runtime import storage_diagnostics


def test_storage_diagnostics_distinguishes_healthy_warning_and_critical(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    database = data_root / "nalu.sqlite3"
    database.write_bytes(b"sqlite-fixture")

    def report_free(gib: int) -> None:
        monkeypatch.setattr(
            storage_diagnostics.shutil,
            "disk_usage",
            lambda _: SimpleNamespace(total=100 * 1024**3, used=0, free=gib * 1024**3),
        )

    report_free(40)
    healthy = storage_diagnostics.inspect_storage(data_root, database)
    assert healthy.status == "healthy"
    assert healthy.can_start_new_production is True
    assert healthy.database_bytes == len(b"sqlite-fixture")

    report_free(10)
    warning = storage_diagnostics.inspect_storage(data_root, database)
    assert warning.status == "warning"
    assert warning.can_start_new_production is True
    assert "不会自动删除" in warning.explanation

    report_free(4)
    critical = storage_diagnostics.inspect_storage(data_root, database)
    assert critical.status == "critical"
    assert critical.can_start_new_production is False
    assert critical.minimum_production_reserve_bytes == 5 * 1024**3
