#!/usr/bin/env python3
"""Regression tests for the unified manifest registry."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "manifest_registry.py"
sys.path.insert(0, str(ROOT / "scripts"))
from schema_contract import validate as validate_schema  # noqa: E402


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=ROOT, capture_output=True, text=True, check=False)


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        deck = root / "deck.pptx"; deck.write_bytes(b"fake-pptx")
        slide = root / "slide-manifest.json"; write(slide, {"slides": [{"slide_no": 1, "slide_id": "S01", "asset_ids": ["panel-01"]}]})
        objects = root / "slide-object-manifest.json"; write(objects, {"slides": [{"slide_no": 1, "objects": [{"object_id": "panel-01", "role": "semantic-panel", "object_type": "traceable_static_graphic", "editability_level": "L3", "independent": True}, {"object_id": "title", "object_type": "editable_text", "editability_level": "L1", "runs": [{"text": "标题"}]}]}]})
        layout = root / "layout.json"; write(layout, {"slides": [{"slide_no": 1, "regions": [{"region_id": "panel-01", "object_ids": ["panel-01"], "bbox": [0, 0, 1, 1], "independent": True}]}]})
        text_manifest = root / "text-layout-manifest.json"; write(text_manifest, {"schema": "ai-ppt-plus/text-layout-manifest/v1", "units": "fraction", "reference_size": {"width": 1, "height": 1}, "slides": [{"slide_no": 1, "text_specs": [{"text_id": "title", "content": "标题", "style": {"font_family": "Noto Sans CJK SC", "size_pt": 24}, "runs": []}]}]})
        panel_file = root / "panel.png"; panel_file.write_bytes(b"panel")
        assets = root / "panel-asset-manifest.json"; write(assets, {"source": str(panel_file), "panels": [{"panel_id": "panel-01", "role": "semantic-panel", "path": "panel.png"}]})
        report = root / "report-index.json"; write(report, {"reports": [{"report_type": "qa", "path": "qa.json", "required": True}]}); write(root / "qa.json", {"valid": True})
        registry = root / "manifest-registry.json"
        built = run("build", "--output", registry, "--project-id", "demo", "--deck", deck, "--slide-manifest", slide, "--object-manifest", objects, "--layout", layout, "--text-manifest", text_manifest, "--asset-manifest", assets, "--report-index", report)
        assert built.returncode == 0, built.stderr
        data = json.loads(registry.read_text(encoding="utf-8"))
        assert data["schema"] == "ai-ppt-plus/manifest-registry/v2"
        assert data["model"] == {
            "name": "SlideSpec/RegionSpec/ObjectSpec/AssetSpec",
            "version": "2.0",
            "legacy_inputs": ["ai-ppt-plus/manifest-registry/v1"],
        }
        assert data["slides"][0]["regions"][0]["region_id"] == "panel-01"
        assert data["slides"][0]["regions"][0]["bbox"] == {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
        assert data["slides"][0]["regions"][0]["object_ids"] == ["panel-01"]
        assert data["slides"][0]["text_specs"][0]["text_id"] == "title"
        assert len(data["assets"][0]["path_sha256"]) == 64
        assert data["assets"][0]["source_ref"] == "panel.png"
        schema = json.loads((ROOT / "assets/schemas/manifest-registry.schema.json").read_text(encoding="utf-8"))
        assert not validate_schema(data, schema)
        validation = root / "validation.json"
        checked = run("validate", registry, "--deck", deck, "--report", validation, "--require-gates")
        assert checked.returncode == 0, checked.stdout + checked.stderr
        panel_file.write_bytes(b"mutated")
        stale_asset = run("validate", registry, "--deck", deck)
        assert stale_asset.returncode != 0 and "asset_path_hash_mismatch" in stale_asset.stdout
        panel_file.write_bytes(b"panel")
        (root / "qa.json").unlink()
        missing_gate = run("validate", registry, "--deck", deck, "--report", validation, "--require-gates")
        assert missing_gate.returncode != 0 and "gate_report_missing" in missing_gate.stdout
        write(root / "qa.json", {"valid": True})
        deck.write_bytes(b"changed")
        broken = run("validate", registry, "--deck", deck)
        assert broken.returncode != 0 and "deck_hash_mismatch" in broken.stdout

        conflict = json.loads(registry.read_text(encoding="utf-8"))
        conflict["slides"][0]["regions"][0]["object_ids"] = ["missing-object"]
        write(registry, conflict)
        broken_reference = run("validate", registry, "--deck", deck)
        assert broken_reference.returncode != 0
        assert "unresolved_region_object_reference" in broken_reference.stdout

        # Pixel-space layouts are valid and must not be reinterpreted as
        # fractional geometry by the registry validator.  Also accept the
        # common x/y/w/h region form used by layout.json.
        layout_px = root / "layout-px.json"; write(layout_px, {
            "units": "px",
            "ref_width": 100,
            "ref_height": 80,
            "slides": [{"slide_no": 1, "regions": [{"region_id": "panel-01", "object_ids": ["panel-01"], "x": 2, "y": 3, "w": 90, "h": 70, "independent": True}]}],
        })
        text_px = root / "text-layout-px.json"; write(text_px, {
            "schema": "ai-ppt-plus/text-layout-manifest/v1",
            "units": "px",
            "reference_size": {"width": 100, "height": 80},
            "slides": [{"slide_no": 1, "text_specs": [{"text_id": "title", "content": "标题", "bbox": {"x": 5, "y": 5, "w": 40, "h": 12}, "style": {"font_family": "Noto Sans CJK SC", "size_px": 12}, "runs": []}]}],
        })
        registry_px = root / "manifest-registry-px.json"
        built_px = run("build", "--output", registry_px, "--project-id", "demo", "--deck", deck, "--slide-manifest", slide, "--object-manifest", objects, "--layout", layout_px, "--text-manifest", text_px, "--asset-manifest", assets)
        assert built_px.returncode == 0, built_px.stderr
        px_data = json.loads(registry_px.read_text(encoding="utf-8"))
        assert px_data["slides"][0]["regions"][0]["bbox"] == {"x": 2.0, "y": 3.0, "w": 90.0, "h": 70.0}
        px_check = run("validate", registry_px, "--deck", deck)
        assert px_check.returncode == 0, px_check.stdout + px_check.stderr
        px_result = json.loads(px_check.stdout)
        warning_codes = {item.get("code") for item in px_result.get("warnings", [])}
        assert "region_geometry_missing" not in warning_codes
        assert "text_model_text_bbox_fraction_outside_unit" not in warning_codes

        legacy = root / "legacy-registry.json"
        write(legacy, {
            "schema": "ai-ppt-plus/manifest-registry/v1",
            "project_id": "demo",
            "revision": "working",
            "state": "validated",
            "deck": {"path": "deck.pptx", "sha256": "a" * 64},
            "authority": {"formal_content": "slide-manifest.json", "visual": "reference.png"},
            "sources": [],
            "slides": [{
                "slide_id": "S01",
                "slide_no": 1,
                "regions": [{"region_id": "panel-01", "bbox": [0, 0, 1, 1], "object_id": "panel-01", "asset_id": "panel-01"}],
                "objects": [
                    {"object_id": "panel-01", "object_type": "traceable_static_graphic", "editability_level": "L3"},
                    {"object_id": "title", "object_type": "editable_text", "editability_level": "L1"},
                ],
                "text_specs": [{"text_id": "title", "content": "标题", "runs": []}],
                "asset_ids": ["panel-01"],
                "gate_refs": [],
            }],
            "assets": [{"asset_id": "panel-01", "role": "asset", "details": {}}],
            "gates": [],
            "evidence": {},
        })
        legacy_check = run("validate", legacy)
        assert legacy_check.returncode == 0, legacy_check.stdout + legacy_check.stderr
        assert "legacy_registry_schema" in legacy_check.stdout
    print("manifest registry tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
