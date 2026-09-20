import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_text_coverage.py"
AUDIT = ROOT / "scripts" / "audit_text_coverage.py"

def test_builder_materializes_measured_native_text(tmp_path):
    plan = {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {"sha256": "0"*64, "width_px": 1536, "height_px": 864},
        "canvas": {"width": 1, "height": 1, "units": "normalized"},
        "objects": [{
            "object_id": "title", "page": 1, "semantic_role": "title",
            "implementation_type": "native_text", "bbox": [0.1,0.1,0.5,0.1],
            "z_role": "content", "typography_contract": {}
        }]
    }
    fit = {
        "schema": "ai-ppt-plus/text-fit-deck/v3",
        "all_slots_measured": True,
        "measured_object_ids": ["text:title"],
        "slots": [{
            "slide": 1, "kind": "text", "object_id": "text:title",
            "text": "标题", "target_pt": 28, "recommended_pt": 28,
            "target_fits": True, "geometry_defect": False, "line_count": 1,
            "text_spec_id": "title", "content_sha256": "c3405f8c7d9d392aa3e2d073d5793bce795353c5f7ef0d27f3d6c1c8d2832681",
            "content_matches_runs": True, "run_count": 2,
            "run_ids": ["title.r01", "title.r02"],
            "run_trace": [
                {"run_id": "title.r01", "text": "标", "style": {"color": "#FFFFFF"}},
                {"run_id": "title.r02", "text": "题", "style": {"bold": True}}
            ], "run_style_sha256": "c1d801f362b1642579516db3344abd95e4888336bb85973e3d38dff98f9b91c7",
            "measurement_scope": {"kind": "whole_phrase", "scope_id": "text:title"}
        }]
    }
    pp = tmp_path/"authoring-plan.json"
    fp = tmp_path/"text-fit.json"
    cp = tmp_path/"text-coverage.json"
    pp.write_text(json.dumps(plan), encoding="utf-8")
    fp.write_text(json.dumps(fit), encoding="utf-8")
    build = subprocess.run([sys.executable, str(BUILD), str(pp), str(fp), "--output", str(cp)], capture_output=True, text=True)
    assert build.returncode == 0
    data = json.loads(cp.read_text(encoding="utf-8"))
    assert data["entries"][0]["text_fit_evidence_id"] == "text:title"
    assert data["entries"][0]["producer_kind"] == "rich_text_runs"
    assert data["entries"][0]["text_fit_evidence"]["run_ids"] == ["title.r01", "title.r02"]
    audit = subprocess.run([sys.executable, str(AUDIT), str(pp), str(cp), "--text-fit-report", str(fp), "--json"], capture_output=True, text=True)
    assert audit.returncode == 0
    assert json.loads(audit.stdout)["valid"] is True
