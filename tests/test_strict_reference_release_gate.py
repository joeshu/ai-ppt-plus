#!/usr/bin/env python3
"""Contract test: fixed-reference release must fail closed on the fresh render."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "ai-ppt-editable" / "scripts" / "strict_reference_release.py"
MIRROR = ROOT / "scripts" / "strict_reference_release.py"


def main() -> int:
    worker = WORKER.read_text(encoding="utf-8")
    mirror = MIRROR.read_text(encoding="utf-8")
    assert worker == mirror, "strict release gate must stay runtime-mirrored"
    assert "strict_reference_rerun.py" in worker
    assert "render_pptx.py" in worker
    assert "compare_visual.py" in worker
    assert '"--raw-slide", "--strict"' in worker
    assert "compare_visual_regions.py" in worker
    assert "blocked-by-rendered-reference-fidelity" in worker
    assert "rendered-and-visual-gated" in worker
    assert "visual_gate_passed" in worker
    # The gate must update status only from the real compare process return code.
    assert 'visual.returncode == 0' in worker
    print("strict reference release render gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
