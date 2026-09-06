import os
import sys
import threading
from typing import BinaryIO

import uvicorn


def runtime_port() -> int:
    raw = os.environ.get("NALU_RUNTIME_PORT", "8765")
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError("Invalid Runtime port")
    port = int(raw)
    if str(port) != raw or not 1024 <= port <= 65535:
        raise ValueError("Invalid Runtime port")
    return port


def watch_owner_pipe(server: uvicorn.Server, owner_pipe: BinaryIO) -> None:
    """EOF means the owning app exited; never signal a PID or another Runtime."""
    try:
        while owner_pipe.read(1):
            pass
    finally:
        server.should_exit = True


def main() -> None:
    options = {"host": "127.0.0.1", "port": runtime_port(), "reload": False}
    if os.environ.get("NALU_RUNTIME_OWNER_PIPE") != "1":
        uvicorn.run("nalu_runtime.app:app", **options)
        return
    server = uvicorn.Server(uvicorn.Config("nalu_runtime.app:app", **options))
    threading.Thread(
        target=watch_owner_pipe, args=(server, sys.stdin.buffer), daemon=True,
        name="nalu-owner-lifetime",
    ).start()
    server.run()


if __name__ == "__main__":
    main()
