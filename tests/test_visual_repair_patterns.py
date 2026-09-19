import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_key_crops_include_composed_footer_and_header_regions(tmp_path):
    mod = load_module("scripts/strict_reference_release.py", "strict_reference_release_test")
    layout = tmp_path / "layout.json"
    output = tmp_path / "regions.json"
    layout.write_text(json.dumps({
        "units": "fraction",
        "slides": [{
            "texts": [
                {"object_id": "title", "bbox": [0.2, 0.03, 0.6, 0.08], "text": "标题"},
                {"object_id": "footer-copy", "bbox": [0.05, 0.90, 0.30, 0.04], "text": "底栏"},
            ],
            "images": [{"object_id": "footer-wave", "bbox": [0.0, 0.84, 1.0, 0.16], "semantic_role": "footer"}],
        }],
    }), encoding="utf-8")
    result = mod.key_region_manifest(layout, output)
    ids = {row["region_id"] for row in result["regions"]}
    assert "s1:semantic-region:__footer_band__" in ids
    assert "s1:semantic-region:__header_band__" in ids
    assert 5 <= len(result["regions"]) <= 10


def test_repair_trace_is_threshold_free_and_pattern_aware():
    mod = load_module("scripts/build_render_repair_trace.py", "repair_trace_test")
    layout = {
        "slides": [{
            "texts": [{"object_id": "body", "bbox": [0.1, 0.2, 0.4, 0.2]}],
            "images": [{"object_id": "icon", "bbox": [0.05, 0.2, 0.04, 0.06]}],
        }]
    }
    regional = {
        "regions": [
            {"region_id": "s1:texts:body", "score": 0.97, "bbox": [0.1, 0.2, 0.4, 0.2], "metrics": {"pixel_fidelity": 0.96, "layout_ssim": 0.98}},
            {"region_id": "s1:images:icon", "score": 0.95, "bbox": [0.05, 0.2, 0.04, 0.06], "metrics": {"pixel_fidelity": 0.90, "layout_ssim": 0.98}},
            {"region_id": "s1:semantic-region:__footer_band__", "score": 0.96, "bbox": [0.0, 0.82, 1.0, 0.18], "metrics": {"pixel_fidelity": 0.93, "layout_ssim": 0.97}},
        ]
    }
    result = mod.build_trace(layout, regional, max_actions=12, min_actions=3)
    assert result["valid"] is True
    assert "0.90" not in result["selection_policy"]
    assert len(result["pending_actions"]) == 3
    responsibilities = {row["responsibility"] for row in result["pending_actions"]}
    assert "typography-density" in responsibilities
    assert "asset-identity" in responsibilities
    assert "anchored-visual-system" in responsibilities


def test_text_fit_contract_preserves_exact_line_topology_and_runtime_font():
    text = (ROOT / "ai-ppt-editable/scripts/ppt_text_fit.py").read_text(encoding="utf-8")
    assert "from runtime_fonts import resolve_font_file" in text
    assert 'parser.add_argument("--target-lines"' in text
    assert 'row["line_count"] == args.target_lines' in text
    assert '"line_topology_preserved"' in text
    assert "NotoSansSC-Regular.ttf" not in text


def test_visual_repair_reference_forbids_generic_icon_substitution():
    text = (ROOT / "ai-ppt-editable/references/visual-repair-patterns.md").read_text(encoding="utf-8")
    assert "Pictogram identity drift" in text
    assert "at most two ordinary native primitives" in text
    assert "Never replace a reference pictogram with a generic native icon" in text
    assert "Anchored visual-system drift" in text
    assert "5Gⁿ" in text
