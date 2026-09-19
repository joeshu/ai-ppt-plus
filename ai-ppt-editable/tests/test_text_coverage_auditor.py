import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_text_coverage.py"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def plan():
    return {
        "schema": "ai-ppt-plus/authoring-plan/v1",
        "source": {"sha256": "0"*64, "width_px": 1536, "height_px": 864},
        "canvas": {"width": 1, "height": 1, "units": "normalized"},
        "objects": [
            {
                "object_id": "title", "page": 1, "semantic_role": "title",
                "implementation_type": "native_text", "bbox": [0.1,0.1,0.4,0.1],
                "z_role": "content", "typography_contract": {}
            },
            {
                "object_id": "panel", "page": 1, "semantic_role": "panel",
                "implementation_type": "native_shape", "bbox": [0.1,0.3,0.5,0.4],
                "z_role": "background", "geometry_contract": {}
            }
        ]
    }

def coverage(plan_sha):
    return {
        "schema": "ai-ppt-plus/text-coverage/v1",
        "source": {"authoring_plan_sha256": plan_sha},
        "entries": [{
            "target_id": "title", "owner_object_id": "title",
            "producer_kind": "rich_text_runs", "expected_text": "标题",
            "authoring_path": "artifact_tool:textbox", "text_fit_evidence_id": "text:title",
            "text_fit_evidence": {"measured": True, "fit_decision": "slot-preserved"},
            "output_binding": {"kind": "shape", "binding_id": "title"}
        }]
    }

def run(tmp_path, mutate=None):
    p = tmp_path / "authoring-plan.json"
    p.write_text(json.dumps(plan(), ensure_ascii=False), encoding="utf-8")
    c = coverage(digest(p))
    if mutate:
        mutate(c)
    cp = tmp_path / "text-coverage.json"
    cp.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    out = subprocess.run([sys.executable, str(SCRIPT), str(p), str(cp), "--json"], capture_output=True, text=True)
    return out, json.loads(out.stdout)

def test_valid_coverage_passes(tmp_path):
    out, report = run(tmp_path)
    assert out.returncode == 0
    assert report["valid"] is True
    assert report["uncovered_native_text"] == []

def test_missing_native_text_is_blocked(tmp_path):
    out, report = run(tmp_path, lambda c: c["entries"].clear())
    assert out.returncode == 1
    assert any(x["code"] == "text_coverage_native_text_uncovered" for x in report["issues"])

def test_missing_measurement_is_blocked(tmp_path):
    def mutate(c):
        c["entries"][0]["text_fit_evidence"]["measured"] = False
    out, report = run(tmp_path, mutate)
    assert out.returncode == 1
    assert any(x["code"] == "text_coverage_measurement_missing" for x in report["issues"])

def test_plan_sha_mismatch_is_blocked(tmp_path):
    def mutate(c):
        c["source"]["authoring_plan_sha256"] = "f"*64
    out, report = run(tmp_path, mutate)
    assert out.returncode == 1
    assert any(x["code"] == "text_coverage_plan_sha_mismatch" for x in report["issues"])

def test_duplicate_output_binding_is_blocked(tmp_path):
    def mutate(c):
        second = dict(c["entries"][0])
        second["target_id"] = "title-2"
        second["text_fit_evidence"] = dict(second["text_fit_evidence"])
        second["output_binding"] = dict(second["output_binding"])
        c["entries"].append(second)
    out, report = run(tmp_path, mutate)
    assert out.returncode == 1
    assert any(x["code"] == "text_coverage_output_binding_duplicate" for x in report["issues"])


def test_unmeasured_evidence_id_is_blocked(tmp_path):
    p = tmp_path / "authoring-plan.json"
    p.write_text(json.dumps(plan(), ensure_ascii=False), encoding="utf-8")
    c = coverage(digest(p))
    cp = tmp_path / "text-coverage.json"
    cp.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    fit = tmp_path / "text-fit.json"
    fit.write_text(json.dumps({
        "schema": "ai-ppt-plus/text-fit-deck/v3",
        "all_slots_measured": True,
        "measured_object_ids": ["text:other"]
    }), encoding="utf-8")
    out = subprocess.run([sys.executable, str(SCRIPT), str(p), str(cp), "--text-fit-report", str(fit), "--json"], capture_output=True, text=True)
    report = json.loads(out.stdout)
    assert out.returncode == 1
    assert any(x["code"] == "text_coverage_evidence_id_unmeasured" for x in report["issues"])
