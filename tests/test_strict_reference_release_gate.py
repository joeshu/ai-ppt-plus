#!/usr/bin/env python3
"""Contract test: fixed-reference release always renders/reviews without a universal visual threshold."""
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
    assert "render_authoritative.py" in worker
    assert "compare_visual.py" in worker
    assert '"--raw-slide","--report"' in compact
    assert '"--raw-slide","--strict"' not in compact
    assert "compare_visual_regions.py" in worker
    assert "build_render_repair_trace.py" in worker
    assert "--require-golden" not in worker
    assert "visual_metrics_diagnostic_only" in worker
    assert 'status="repair-ready"' in compact
    assert "full-page comparison failed structural validation" in worker
    print("strict reference release render-review contract: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
