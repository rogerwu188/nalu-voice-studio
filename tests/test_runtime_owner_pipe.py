import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request


def test_owner_eof_stops_only_owned_runtime_and_preserves_database(tmp_path):
    processes = []

    def start(name):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        root = tmp_path / name
        root.mkdir()
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "NALU_RUNTIME_PORT": str(port),
            "NALU_RUNTIME_OWNER_PIPE": "1",
            "NALU_DATA_ROOT": str(root / "data"),
            "NALU_DATABASE_PATH": str(root / "nalu.sqlite3"),
        }
        process = subprocess.Popen(
            [sys.executable, "-m", "nalu_runtime"], env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        processes.append(process)
        url = f"http://127.0.0.1:{port}/health"
        for _ in range(100):
            assert process.poll() is None, "Managed Runtime exited before owner EOF"
            try:
                with urllib.request.urlopen(url, timeout=0.3) as response:
                    assert response.status == 200
                    return process, url, root
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        raise AssertionError("Managed Runtime never became healthy")

    try:
        first, _, first_root = start("first")
        second, second_url, _ = start("second")
        # Non-EOF bytes must not be mistaken for a shutdown command.
        first.stdin.write(b"still-owned")
        first.stdin.flush()
        assert first.poll() is None
        first.stdin.close()
        assert first.wait(timeout=12) == 0
        assert second.poll() is None
        with urllib.request.urlopen(second_url, timeout=1) as response:
            assert response.status == 200
        with sqlite3.connect(first_root / "nalu.sqlite3") as database:
            assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        second.stdin.close()
        assert second.wait(timeout=12) == 0
    finally:
        for process in processes:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
