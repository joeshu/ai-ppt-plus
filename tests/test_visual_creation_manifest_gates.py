#!/usr/bin/env python3
"""Regression test for visual-creation versus reference gate inference."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_slide_manifest import _gate_requirements


def main() -> int:
    args = SimpleNamespace(
        reference=None,
        visual_source="visual-intermediate-manifest.json#S01",
        requires_text_style_map=False,
        requires_imagegen_assets=True,
        requires_icon_assets=False,
        requires_panel_assets=False,
        requires_panel_approval=False,
        requires_gradient_visual=False,
    )
    requirements = _gate_requirements(
        {},
        [{"objects": [{"object_type": "editable_text"}, {"object_type": "independent_image"}]}],
        args,
    )
    assert requirements["imagegen_assets"] is True
    assert requirements["text_style_map"] is False
    assert requirements["source_image_validation"] is False
    assert requirements["reference_audit"] is False
    print("visual-creation gate inference: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
