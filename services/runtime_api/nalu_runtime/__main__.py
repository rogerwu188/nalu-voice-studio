import os

import uvicorn


def runtime_port() -> int:
    raw = os.environ.get("NALU_RUNTIME_PORT", "8765")
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError("Invalid Runtime port")
    port = int(raw)
    if str(port) != raw or not 1024 <= port <= 65535:
        raise ValueError("Invalid Runtime port")
    return port


def main() -> None:
    uvicorn.run(
        "nalu_runtime.app:app",
        host="127.0.0.1",
        port=runtime_port(),
        reload=False,
    )


if __name__ == "__main__":
    main()
