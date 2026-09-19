#!/usr/bin/env python3
"""Contract test: fixed-reference release must render/review fresh output and gate Golden promotion."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "ai-ppt-editable" / "scripts" / "strict_reference_release.py"
MIRROR = ROOT / "scripts" / "strict_reference_release.py"


def main() -> int:
    worker = WORKER.read_text(encoding="utf-8")
    mirror = MIRROR.read_text(encoding="utf-8")
    compact = "".join(worker.split())
    assert worker == mirror, "strict release gate must stay runtime-mirrored"
    assert "strict_reference_rerun.py" in worker
    assert "render_pptx.py" in worker
    assert "compare_visual.py" in worker
    assert '"--raw-slide","--strict"' in compact
    assert "compare_visual_regions.py" in worker
    assert "build_render_repair_trace.py" in worker
    assert "--require-golden" in worker
    assert "draft-needs-render-repair" in worker
    assert "golden-ready" in worker
    assert "strict_visual_target_passed" in worker
    # Fresh visual comparison is always recorded; only explicit Golden promotion
    # fails closed on a below-target render.
    assert "visual.returncode==0" in compact
    assert "ifa.require_goldenandnotvisual_passed:" in compact
    print("strict reference release render-driven gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
