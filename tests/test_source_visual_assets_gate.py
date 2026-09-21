#!/usr/bin/env python3
"""Regression coverage for source-visual -> ImageGen final coverage."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "ai-ppt-editable" / "scripts" / "validate_source_visual_assets.py"
MIRROR = ROOT / "scripts" / "validate_source_visual_assets.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_source_visual_assets", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def inventory(source_sha: str, visuals: list[dict]) -> dict:
    return {
        "schema": "ai-ppt-plus/source-visual-inventory/v1",
        "source": {"sha256": source_sha, "width_px": 1536, "height_px": 864},
        "visuals": visuals,
    }


def main() -> int:
    assert WORKER.read_text(encoding="utf-8") == MIRROR.read_text(encoding="utf-8")
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="source-visual-assets-") as temp:
        root = Path(temp)
        source = root / "source.png"
        source.write_bytes(b"source")
        final = root / "assets" / "logo.png"
        generated = root / "generated" / "logo.png"
        prompt = root / "prompts" / "logo.txt"
        final.parent.mkdir()
        generated.parent.mkdir()
        prompt.parent.mkdir()
        final.write_bytes(b"final-logo")
        generated.write_bytes(b"generated-logo")
        prompt.write_text("transparent independent lockup", encoding="utf-8")
        source_sha = digest(source)

        visual = {
            "visual_id": "logo-1", "page": 1, "semantic_role": "brand_lockup",
            "bbox_norm": [0.8, 0.02, 0.15, 0.08], "required_route": "imagegen",
            "asset_id": "logo-1",
        }
        manifest = root / "imagegen-assets-manifest.json"
        write(manifest, {
            "source_sha256": source_sha,
            "assets": [{
                "asset_id": "logo-1", "asset_class": "brand_lockup", "provenance_mode": "imagegen",
                "generated_source": "generated/logo.png", "copied_to": "assets/logo.png",
                "prompt_file": "prompts/logo.txt", "backend": "native-imagegen",
                "independent_asset": True, "sha256": digest(final),
            }],
        })
        inv = root / "source-visual-inventory.json"
        write(inv, inventory(source_sha, [visual]))
        graph = root / "page-graph.json"
        write(graph, {"nodes": [{"id": "logo-1", "type": "image", "role": "brand_lockup", "bbox": visual["bbox_norm"]}]})
        layout = root / "layout.json"
        write(layout, {"slides": [{"icons": [{"object_id": "logo-1", "file": "assets/logo.png"}]}]})
        good = module.validate(inv, manifest, graph, layout)
        assert good["valid"], good
        assert good["covered_count"] == 1

        unbound_layout = root / "unbound-layout.json"
        write(unbound_layout, {"slides": [{"icons": []}]})
        unbound_report = module.validate(inv, manifest, graph, unbound_layout)
        assert not unbound_report["valid"]
        assert "source_visual_asset_not_bound_to_layout" in {item["code"] for item in unbound_report["issues"]}

        missing = module.validate(inv, None, graph)
        assert not missing["valid"]
        assert "source_visual_imagegen_manifest_missing" in {item["code"] for item in missing["issues"]}

        omitted = root / "omitted.json"
        write(omitted, inventory(source_sha, []))
        omitted_report = module.validate(omitted, manifest, graph)
        assert not omitted_report["valid"]
        assert "source_visual_inventory_missing_graph_asset" in {item["code"] for item in omitted_report["issues"]}

        empty_without_graph = module.validate(omitted, manifest, None)
        assert not empty_without_graph["valid"]
        assert "source_visual_inventory_empty_without_page_graph" in {
            item["code"] for item in empty_without_graph["issues"]
        }

        crop_manifest = root / "crop-manifest.json"
        crop = json.loads(manifest.read_text(encoding="utf-8"))
        crop["assets"][0]["provenance_mode"] = "source_reuse"
        crop["assets"][0]["source_reuse"] = True
        write(crop_manifest, crop)
        crop_report = module.validate(inv, crop_manifest, graph)
        crop_codes = {item["code"] for item in crop_report["issues"]}
        assert "source_visual_asset_requires_imagegen" in crop_codes
        assert "source_visual_asset_crop_fallback_forbidden" in crop_codes

        incomplete_manifest = root / "incomplete-manifest.json"
        incomplete = json.loads(manifest.read_text(encoding="utf-8"))
        incomplete["assets"][0].pop("sha256")
        incomplete["assets"][0]["prompt_file"] = "prompts/missing.txt"
        write(incomplete_manifest, incomplete)
        incomplete_report = module.validate(inv, incomplete_manifest, graph)
        incomplete_codes = {item["code"] for item in incomplete_report["issues"]}
        assert "source_visual_asset_hash_missing" in incomplete_codes
        assert "source_visual_asset_evidence_file_missing" in incomplete_codes

    print("source visual asset coverage gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
