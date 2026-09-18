#!/usr/bin/env python3
"""Root runtime mirror for PPTX layer-order audit."""
from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "ai-ppt-editable" / "scripts" / "audit_pptx_layers.py"),
    run_name="__main__",
)
