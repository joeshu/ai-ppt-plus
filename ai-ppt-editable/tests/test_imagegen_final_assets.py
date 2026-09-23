#!/usr/bin/env python3
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_imagegen_final_assets import validate


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry():
    return {
        "visible_alpha_bbox": [0.08, 0.08, 0.92, 0.92],
        "alpha_centroid": [0.5, 0.5],
        "placement_bbox": [0.1, 0.1, 0.05, 0.05],
        "independent_asset": True,
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="imagegen-final-") as folder:
        root = Path(folder)
        (root / "gen").mkdir()
        (root / "editable").mkdir()
        (root / "prompts").mkdir()
        generated = root / "gen" / "i1.png"
        copied = root / "editable" / "i1.png"
        prompt = root / "prompts" / "i1.txt"
        generated.write_bytes(b"generated-icon")
        copied.write_bytes(generated.read_bytes())
        prompt.write_text("generate icon", encoding="utf-8")

        good = root / "good.json"
        good.write_text(json.dumps({
            "provenance_policy": "imagegen_final_assets",
            "assets": [{
                "asset_id": "i1", "asset_class": "icon", "provenance_mode": "imagegen",
                "generated_source": "gen/i1.png", "copied_to": "editable/i1.png",
                "prompt_file": "prompts/i1.txt", "backend": "native-imagegen", "sha256": sha(copied),
                **geometry(),
            }],
        }), encoding="utf-8")
        report = validate(good, strict=True)
        assert report["valid"], report
        assert report["schema"].endswith("/v3")

        receipt_good = json.loads(good.read_text(encoding="utf-8"))
        receipt_good.update({"native_tool": "image_gen.imagegen", "native_tool_receipt_required": True})
        receipt_good["assets"][0]["native_imagegen_receipt"] = {
            "tool": "image_gen.imagegen", "mode": "new", "source_reference": "source.png",
            "prompt_sha256": sha(prompt), "output_path": "gen/i1.png",
            "generation_request_id": "request-i1", "recorded_at": "2026-09-21T00:00:00Z",
        }
        receipt_manifest = root / "receipt-good.json"
        receipt_manifest.write_text(json.dumps(receipt_good), encoding="utf-8")
        report = validate(receipt_manifest, strict=True)
        assert report["valid"], report
        assert report["schema"].endswith("/v4")

        missing_receipt = json.loads(receipt_manifest.read_text(encoding="utf-8"))
        missing_receipt["assets"][0].pop("native_imagegen_receipt")
        missing_receipt_manifest = root / "receipt-missing.json"
        missing_receipt_manifest.write_text(json.dumps(missing_receipt), encoding="utf-8")
        report = validate(missing_receipt_manifest, strict=True)
        assert not report["valid"]
        assert any(item["code"] == "native_imagegen_receipt_missing" for item in report["errors"])

        # An unspecified "official" route is not enough evidence.
        official = root / "official.json"
        official.write_text(json.dumps({
            "provenance_policy": "imagegen_final_assets",
            "assets": [{"asset_id": "logo", "asset_class": "logo", "provenance_mode": "official"}],
        }), encoding="utf-8")
        report = validate(official, strict=True)
        assert not report["valid"]
        assert any(item["code"] == "final_asset_not_imagegen" for item in report["errors"])

        brand_fallback = root / "brand-fallback.json"
        brand_fallback.write_text(json.dumps({
            "provenance_policy": "imagegen_final_assets",
            "assets": [{"asset_id": "logo", "asset_class": "brand_lockup", "provenance_mode": "source_reuse", "fallback_decision": "user_approved", "decision_id": "decision-1", "decision_reason": "temporary test fallback", "decision_timestamp": "2026-09-01T00:00:00Z", "source_ref": "source.png", "source_bbox": [1, 2, 3, 4], "source_sha256": "0" * 64, "copied_to": "editable/i1.png", "prompt_file": "not-used", "backend": "source-crop"}],
        }), encoding="utf-8")
        report = validate(brand_fallback, strict=True)
        assert not report["valid"]
        assert any(item["code"] == "brand_asset_requires_native_imagegen" for item in report["errors"])

        exact_source = root / "official-logo.png"
        exact_source.write_bytes(b"official-logo")
        exact_copy = root / "editable" / "official-logo.png"
        exact_copy.write_bytes(exact_source.read_bytes())
        exact = root / "exact-brand.json"
        exact.write_text(json.dumps({
            "provenance_policy": "imagegen_final_assets",
            "assets": [{"asset_id": "logo", "asset_class": "logo",
                "provenance_mode": "provided_exact_brand_asset",
                "extraction_method": "approved-source-asset", "exact_brand_asset": True,
                "user_supplied": True, "source_kind": "official_asset", "independent_asset": True,
                "source_ref": "official-logo.png", "source_sha256": sha(exact_source),
                "copied_to": "editable/official-logo.png"}],
        }), encoding="utf-8")
        exact_report = validate(exact, strict=True)
        assert not exact_report["valid"]
        assert any(item["code"] == "brand_asset_requires_native_imagegen" for item in exact_report["errors"])

        bad = root / "bad.json"
        bad.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "g1", "asset_class": "gradient_visual", "provenance_mode": "source_reuse", "source_reuse": True}]}), encoding="utf-8")
        report = validate(bad, strict=True)
        assert not report["valid"]
        assert any(item["code"] == "final_asset_not_imagegen" for item in report["errors"])

        fake = root / "fake.json"
        fake.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "i2", "asset_class": "icon", "provenance_mode": "imagegen", "generated_source": "missing.png", "copied_to": "missing2.png", "prompt_file": "missing.txt", "backend": "generic-renderer", "sha256": "0" * 64, **geometry()}]}), encoding="utf-8")
        report = validate(fake, strict=True)
        assert not report["valid"]
        codes = {item["code"] for item in report["errors"]}
        assert "non_native_imagegen_backend" in codes
        assert "imagegen_evidence_file_missing" in codes

        # Slicing a generated contact/sprite sheet is not an independent final
        # asset.  The ancestry must fail even if copied_to has an innocent name.
        contact_dir = root / "gen" / "contact-sheet"
        contact_dir.mkdir()
        sheet_source = contact_dir / "icons.png"
        sheet_source.write_bytes(b"sheet")
        sheet_copy = root / "editable" / "single-icon.png"
        sheet_copy.write_bytes(b"sheet")
        sheet_prompt = root / "prompts" / "sheet.txt"
        sheet_prompt.write_text("icon sheet", encoding="utf-8")
        sheet = root / "sheet.json"
        sheet.write_text(json.dumps({
            "provenance_policy": "imagegen_final_assets",
            "assets": [{
                "asset_id": "sheet-child", "asset_class": "icon", "provenance_mode": "imagegen",
                "generated_source": "gen/contact-sheet/icons.png", "copied_to": "editable/single-icon.png",
                "prompt_file": "prompts/sheet.txt", "backend": "native-imagegen", "sha256": sha(sheet_copy),
                **geometry(),
            }],
        }), encoding="utf-8")
        report = validate(sheet, strict=True)
        assert not report["valid"]
        assert "sheet_not_independent_asset" in {item["code"] for item in report["errors"]}

        # A documented alpha-trimmed cell may inherit its source from a sheet,
        # while the delivered PPT asset remains an independent slice.
        sliced_copy = root / "editable" / "sliced-icon.png"
        sliced_copy.write_bytes(b"independent-slice")
        sliced = root / "sliced.json"
        sliced.write_text(json.dumps({
            "provenance_policy": "imagegen_final_assets",
            "assets": [{
                "asset_id": "sheet-child-valid", "asset_class": "icon", "provenance_mode": "imagegen",
                "generated_source": "gen/contact-sheet/icons.png", "copied_to": "editable/sliced-icon.png",
                "prompt_file": "prompts/sheet.txt", "backend": "native-imagegen", "sha256": sha(sliced_copy),
                "derived_from_sheet": True, "generation_parent": "gen/contact-sheet/icons.png",
                "derived_transform": {"mode": "alpha-trimmed-grid-slice", "bbox_px": [0, 0, 32, 32]},
                **geometry(),
            }],
        }), encoding="utf-8")
        report = validate(sliced, strict=True)
        assert report["valid"], report

        source = root / "source.png"
        source.write_bytes(b"authoritative-source")
        fallback = root / "fallback.json"
        fallback.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "g1", "asset_class": "icon", "provenance_mode": "source_reuse", "fallback_decision": "user_approved", "decision_id": "decision-1", "decision_reason": "user selected crop", "decision_timestamp": "2026-09-01T00:00:00Z", "source_ref": "source.png", "source_bbox": [1, 2, 3, 4], "source_sha256": sha(source), "copied_to": "editable/g1.png", "prompt_file": "not-used", "backend": "source-crop"}]}), encoding="utf-8")
        assert validate(fallback, strict=True)["valid"]
    print("imagegen final-asset policy v3: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
