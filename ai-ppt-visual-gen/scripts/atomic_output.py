#!/usr/bin/env python3
"""Atomic filesystem primitives used by every PPTX artifact writer.

Reports are part of the delivery contract just like the PPTX itself.  Keep
all JSON/text/byte publication behind these helpers so a cancelled process
cannot leave a truncated report that a later gate mistakes for evidence.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable


def _temporary_path(target: Path, suffix: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=suffix, dir=target.parent)
    os.close(handle)
    return Path(name)


def atomic_replace(target: str | Path, writer: Callable[[Path], None], *, suffix: str = ".tmp") -> Path:
    """Write a sibling temporary file and atomically replace ``target``."""
    destination = Path(target).resolve()
    temporary = _temporary_path(destination, suffix)
    try:
        writer(temporary)
        # The writer may be a library call (python-pptx, Pillow, or ZIP).  By
        # the time it returns the file should be complete; flush it before the
        # rename so a successful command cannot publish an unwritten buffer.
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        # A rename is atomic, but the directory entry itself is not durable
        # until the parent directory is flushed on POSIX filesystems.
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def atomic_save_presentation(presentation, target: str | Path) -> Path:
    """Save a python-pptx Presentation without exposing a partial target."""
    return atomic_replace(target, lambda path: presentation.save(str(path)), suffix=".tmp.pptx")


def atomic_write_bytes(target: str | Path, payload: bytes, *, suffix: str = ".tmp") -> Path:
    def write(path: Path) -> None:
        path.write_bytes(payload)

    return atomic_replace(target, write, suffix=suffix)


def atomic_write_text(target: str | Path, payload: str, *, suffix: str = ".tmp", encoding: str = "utf-8") -> Path:
    """Write a text artifact without exposing a partial target."""
    return atomic_write_bytes(target, payload.encode(encoding), suffix=suffix)


def atomic_write_json(target: str | Path, value, *, suffix: str = ".tmp.json") -> Path:
    """Serialize JSON and publish it through the same atomic policy."""
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return atomic_write_text(target, payload, suffix=suffix)


def atomic_copy(source: str | Path, target: str | Path, *, suffix: str = ".tmp.copy") -> Path:
    """Copy a completed artifact into place without exposing a partial file."""
    source_path = Path(source)

    def write(path: Path) -> None:
        with source_path.open("rb") as stream, path.open("wb") as destination:
            shutil.copyfileobj(stream, destination, length=1024 * 1024)

    return atomic_replace(target, write, suffix=suffix)


def atomic_rewrite_zip(target: str | Path, entries: dict[str, bytes]) -> Path:
    """Rewrite a ZIP package atomically, preserving the old file on failure."""
    def write(path: Path) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)

    return atomic_replace(target, write, suffix=".tmp.zip")
