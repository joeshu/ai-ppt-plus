#!/usr/bin/env python3
"""Importable root delegate for ai-ppt-editable/scripts/ppt_text_fit.py."""
from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

_TARGET = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "ppt_text_fit.py"


def _load_target():
    worker_dir = str(_TARGET.parent)
    if worker_dir not in sys.path:
        sys.path.insert(0, worker_dir)
    spec = importlib.util.spec_from_file_location("ai_ppt_editable_ppt_text_fit", _TARGET)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_TARGET}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    worker_dir = str(_TARGET.parent)
    if worker_dir not in sys.path:
        sys.path.insert(0, worker_dir)
    runpy.run_path(str(_TARGET), run_name="__main__")
else:
    _module = _load_target()
    best_fit = _module.best_fit
    find_font = _module.find_font
    measure = _module.measure
    wrap = _module.wrap
