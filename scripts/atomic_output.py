#!/usr/bin/env python3
"""Atomic filesystem primitives used by PPTX authoring and previews."""
from __future__ import annotations

import os
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
        os.replace(temporary, destination)
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


def atomic_rewrite_zip(target: str | Path, entries: dict[str, bytes]) -> Path:
    """Rewrite a ZIP package atomically, preserving the old file on failure."""
    def write(path: Path) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)

    return atomic_replace(target, write, suffix=".tmp.zip")