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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="reference-preflight-") as temp:
        root = Path(temp)
        layout = root / "layout.json"
        write(layout, {"slides": [], "texts": [{"content": "下一步工作"}]})
        write(root / "route-decision.json", {"route": "reference-reconstruction"})
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

        write(root / "imagegen-assets-manifest.json", {
            "provenance_policy": "imagegen_final_assets",
            "assets": [{
                "asset_id": "icon-1",
                "asset_class": "icon",
                "provenance_mode": "source_reuse",
                "source_reuse": True,
            }],
        })
        bad_route = validate_reference_preflight(
            layout,
            json.loads(layout.read_text()),
            embed_fonts=True,
            font_manifest="font-manifest.json",
        )
        assert any(item["code"] == "imagegen_final_asset_gate_failed" for item in bad_route["issues"])

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
                "asset_id": "icon-1",
                "asset_class": "icon",
                "provenance_mode": "imagegen",
                "generated_source": "generated/icon-1.png",
                "copied_to": "assets/icon-1.png",
                "prompt_file": "prompts/icon-1.txt",
                "backend": "native-imagegen",
                "sha256": digest,
            }],
        })
        good = validate_reference_preflight(
            layout,
            json.loads(layout.read_text()),
            embed_fonts=True,
            font_manifest="font-manifest.json",
        )
        assert good["valid"], good
        assert good["imagegen_required"] is True
        assert good["cjk_required"] is True

        # Brand-only pages use the authorized-source exception and do not force imagegen.
        write(root / "slide-object-manifest.json", {
            "slides": [{"objects": [{"object_id": "logo-1", "object_type": "independent_image", "role": "logo"}]}]
        })
        (root / "imagegen-assets-manifest.json").unlink()
        brand_only = validate_reference_preflight(
            layout,
            {"slides": [], "text": "English only"},
            embed_fonts=False,
        )
        assert brand_only["valid"], brand_only
        assert brand_only["imagegen_required"] is False
        assert brand_only["cjk_required"] is False

    print("reference reconstruction preflight: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
