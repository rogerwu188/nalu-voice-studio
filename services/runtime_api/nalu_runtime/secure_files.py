from __future__ import annotations

import os
import secrets
from pathlib import Path


def secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def secure_file(path: Path) -> None:
    os.chmod(path, 0o600)


def sync_directory(path: Path) -> None:
    """Persist directory-entry changes before acknowledging a local artifact."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_exclusive_text(path: Path, encoded: str) -> None:
    """Create an immutable text artifact durably without replacing a peer's artifact."""
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            descriptor = -1
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        secure_file(temporary)
        os.link(temporary, path)
        secure_file(path)
        sync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        sync_directory(path.parent)


def replace_text_durably(path: Path, encoded: str) -> None:
    """Atomically replace a mutable text artifact and persist the replacement."""
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            descriptor = -1
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        secure_file(temporary)
        os.replace(temporary, path)
        secure_file(path)
        sync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        sync_directory(path.parent)


def harden_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    os.chmod(root, 0o700)
