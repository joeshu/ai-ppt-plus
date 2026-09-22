from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_reference_performance_ledger import build


def test_reference_ledger_records_editability_and_diagnostic_delta():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        timing, visual = root / "timing.json", root / "visual.json"
        inspection, baseline, output = root / "inspection.json", root / "baseline.json", root / "ledger.json"
        timing.write_text(json.dumps({"profile": "strict", "candidate_build_ms": 4000, "total_ms": 7000}))
        visual.write_text(json.dumps({"metrics": {"global_ssim": .55, "blurred_layout_ssim": .77, "reference_fidelity_score": .84}}))
        inspection.write_text(json.dumps({"slide_count": 1, "slides": [{"shapes": 142, "text_objects": 70, "pictures": 14}]}))
        baseline.write_text(json.dumps({"visual_metrics": {"global_ssim": .56, "blurred_layout_ssim": .76, "reference_fidelity_score": .83}}))
        report = build(timing=timing, visual=visual, inspection=inspection, output=output, baseline=baseline)
        assert report["editability"]["shape_count"] == 142
        assert report["baseline_comparison"]["regression_signal"] is True
        assert report["baseline_comparison"]["policy"].startswith("diagnostic_only")
