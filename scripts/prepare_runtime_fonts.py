#!/usr/bin/env python3
"""Root delegate for ai-ppt-editable runtime font materialization."""
from __future__ import annotations
import runpy
from pathlib import Path

_TARGET = Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "prepare_runtime_fonts.py"
runpy.run_path(str(_TARGET), run_name="__main__")
