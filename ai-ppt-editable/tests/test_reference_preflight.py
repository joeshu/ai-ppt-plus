#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reference_preflight import validate_reference_preflight


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def page_graph(nodes: list[dict]) -> dict:
    return {
        "version": "1.0",
        "page": {"slide_width_in": 13.333333, "slide_height_in": 7.5, "reference_width": 1672, "reference_height": 941},
        "metadata": {"units": "fraction"},
        "nodes": nodes,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reference-preflight-") as temp:
        root = Path(temp)
        layout = root / "layout.json"
        write(layout, {"slides": [], "texts": [{"content": "下一步工作"}]})
        write(root / "route-decision.json", {"route": "reference-reconstruction"})
        write(root / "page-graph.json", page_graph([
            {"id": "icon-1", "type": "icon", "role": "icon", "bbox": [0.1, 0.1, 0.05, 0.05]},
            {"id": "logo-1", "type": "image", "role": "logo", "bbox": [0.8, 0.02, 0.15, 0.08]},
            {"id": "text-1", "type": "text", "bbox": [0.1, 0.2, 0.5, 0.1]},
        ]))
        write(root / "slide-object-manifest.json", {
            "slides": [{"objects": [
                {"object_id": "icon-1", "object_type": "extracted_icon", "role": "icon"},
                {"object_id": "logo-1", "object_type": "independent_image", "role": "logo"},
            ]}]
        })

        missing = validate_reference_preflight(layout, json.loads(layout.read_text()), embed_fonts=False)
        codes = {item["code"] for item in missing["issues"]}
        assert "imagegen_final_asset_manifest_missing" in codes
        assert "reference_cjk_requires_embedded_fonts" in codes
        assert "reference_cjk_font_evidence_missing" in codes
        assert missing["visual_asset_ids"] == ["icon-1"]
        assert missing["imagegen_required"] is True

        # A downstream manifest cannot hide a visual asset identified by PageGraph.
        write(root / "slide-object-manifest.json", {
            "slides": [{"objects": [{"object_id": "logo-1", "object_type": "independent_image", "role": "logo"}]}]
        })
        mismatch = validate_reference_preflight(layout, json.loads(layout.read_text()), embed_fonts=False)
        assert any(item["code"] == "visual_asset_inventory_mismatch" for item in mismatch["issues"])
        write(root / "slide-object-manifest.json", {
            "slides": [{"objects": [
                {"object_id": "icon-1", "object_type": "extracted_icon", "role": "icon"},
                {"object_id": "logo-1", "object_type": "independent_image", "role": "logo"},
            ]}]
        })

        write(root / "imagegen-assets-manifest.json", {
            "provenance_policy": "imagegen_final_assets",
            "assets": [{"asset_id": "icon-1", "asset_class": "icon", "provenance_mode": "source_reuse", "source_reuse": True}],
        })
        bad_route = validate_reference_preflight(layout, json.loads(layout.read_text()), embed_fonts=True, font_manifest="font-manifest.json")
        bad_codes = {item["code"] for item in bad_route["issues"]}
        assert "imagegen_final_asset_gate_failed" in bad_codes
        assert "reference_cjk_font_evidence_missing" in bad_codes

        (root / "generated").mkdir(exist_ok=True)
        (root / "assets").mkdir(exist_ok=True)
        (root / "prompts").mkdir(exist_ok=True)
        generated = root / "generated" / "icon-1.png"
        copied = root / "assets" / "icon-1.png"
        prompt = root / "prompts" / "icon-1.txt"
        generated.write_bytes(b"generated-icon")
        copied.write_bytes(generated.read_bytes())
        prompt.write_text("generate icon", encoding="utf-8")
        digest = hashlib.sha256(copied.read_bytes()).hexdigest()
        write(root / "imagegen-assets-manifest.json", {
            "provenance_policy": "imagegen_final_assets",
            "assets": [{
                "asset_id": "icon-1", "asset_class": "icon", "provenance_mode": "imagegen",
                "generated_source": "generated/icon-1.png", "copied_to": "assets/icon-1.png",
                "prompt_file": "prompts/icon-1.txt", "backend": "native-imagegen", "sha256": digest,
            }],
        })
        write(root / "font-manifest.json", {"schema": "ai-ppt-plus/font-manifest-test/v1", "fonts": [{"family": "Test CJK Sans", "path": "fonts/test.ttf"}]})
        good = validate_reference_preflight(layout, json.loads(layout.read_text()), embed_fonts=True, font_manifest="font-manifest.json")
        assert good["valid"], good
        assert good["imagegen_required"] is True
        assert good["cjk_required"] is True
        assert good["font_evidence"]["manifest_readable"] is True

        # Missing generated coverage is blocked even if the manifest itself is otherwise valid.
        write(root / "page-graph.json", page_graph([
            {"id": "icon-1", "type": "icon", "role": "icon", "bbox": [0.1, 0.1, 0.05, 0.05]},
            {"id": "icon-2", "type": "icon", "role": "icon", "bbox": [0.2, 0.1, 0.05, 0.05]},
        ]))
        write(root / "slide-object-manifest.json", {"slides": [{"objects": [{"object_id": "icon-1"}, {"object_id": "icon-2"}]}]})
        coverage = validate_reference_preflight(layout, {"text": "English only"}, embed_fonts=False)
        assert any(item["code"] == "imagegen_asset_coverage_missing" for item in coverage["issues"])

        # A page with no icon/illustration/complex-visual nodes does not require imagegen.
        write(root / "page-graph.json", page_graph([
            {"id": "text-only", "type": "text", "bbox": [0.1, 0.1, 0.6, 0.1]},
        ]))
        write(root / "slide-object-manifest.json", {"slides": [{"objects": [{"object_id": "text-only", "object_type": "editable_text"}]}]})
        (root / "imagegen-assets-manifest.json").unlink()
        no_visual_assets = validate_reference_preflight(layout, {"text": "English only"}, embed_fonts=False)
        assert no_visual_assets["valid"], no_visual_assets
        assert no_visual_assets["imagegen_required"] is False

        # Brand-only PageGraph uses the authorized-source exception and does not force imagegen.
        write(root / "page-graph.json", page_graph([
            {"id": "logo-1", "type": "image", "role": "logo", "bbox": [0.8, 0.02, 0.15, 0.08]},
        ]))
        write(root / "slide-object-manifest.json", {"slides": [{"objects": [{"object_id": "logo-1", "object_type": "independent_image", "role": "logo"}]}]})
        brand_only = validate_reference_preflight(layout, {"text": "English only"}, embed_fonts=False)
        assert brand_only["valid"], brand_only
        assert brand_only["imagegen_required"] is False

        # Missing PageGraph itself is fail-closed: visual decomposition is the authority.
        (root / "page-graph.json").unlink()
        missing_graph = validate_reference_preflight(layout, {"text": "English only"}, embed_fonts=False)
        assert any(item["code"] == "reference_page_graph_missing" for item in missing_graph["issues"])

    print("reference reconstruction preflight: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
