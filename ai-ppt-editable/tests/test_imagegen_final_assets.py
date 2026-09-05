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


def retry_evidence() -> dict:
    return {
        "status": "user-choice-required",
        "attempts_exhausted": 3,
        "max_native_attempts": 3,
        "choices": ["continue-native-generation", "crop-matting-fallback"],
        "attempts": [
            {"attempt": 1, "status": "failed_qa", "backend": "native-imagegen", "prompt_ref": "prompts/a1.txt", "issue_codes": ["silhouette_mismatch"]},
            {"attempt": 2, "status": "failed_qa", "backend": "native-imagegen", "prompt_ref": "prompts/a2.txt", "issue_codes": ["style_mismatch"]},
            {"attempt": 3, "status": "generation_failed", "backend": "native-imagegen", "prompt_ref": "prompts/a3.txt", "error_code": "provider_generation_failed"},
        ],
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
            "assets": [
                {"asset_id": "i1", "asset_class": "icon", "provenance_mode": "imagegen", "generated_source": "gen/i1.png", "copied_to": "editable/i1.png", "prompt_file": "prompts/i1.txt", "backend": "native-imagegen", "sha256": sha(copied)},
                {"asset_id": "logo", "asset_class": "logo", "provenance_mode": "official"},
            ],
        }), encoding="utf-8")
        report = validate(good, strict=True)
        assert report["valid"], report
        assert report["schema"].endswith("/v3")
        assert report["minimum_native_attempts_before_fallback"] == 3

        bad = root / "bad.json"
        bad.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "g1", "asset_class": "gradient_visual", "provenance_mode": "source_reuse", "source_reuse": True}]}), encoding="utf-8")
        report = validate(bad, strict=True)
        assert not report["valid"]
        codes = {item["code"] for item in report["errors"]}
        assert "final_asset_not_imagegen" in codes
        assert "native_retry_evidence_missing" in codes

        fake = root / "fake.json"
        fake.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "i2", "asset_class": "icon", "provenance_mode": "imagegen", "generated_source": "missing.png", "copied_to": "missing2.png", "prompt_file": "missing.txt", "backend": "generic-renderer", "sha256": "0" * 64}]}), encoding="utf-8")
        report = validate(fake, strict=True)
        assert not report["valid"]
        codes = {item["code"] for item in report["errors"]}
        assert "non_native_imagegen_backend" in codes
        assert "imagegen_evidence_file_missing" in codes

        source = root / "source.png"
        source.write_bytes(b"authoritative-source")
        fallback_asset = {
            "asset_id": "g1",
            "asset_class": "icon",
            "provenance_mode": "source_reuse",
            "fallback_decision": "user_approved",
            "selected_choice": "crop-matting-fallback",
            "decision_id": "decision-1",
            "decision_reason": "native imagegen retry budget exhausted; user selected crop fallback",
            "decision_timestamp": "2026-09-01T00:00:00Z",
            "native_retry_evidence": retry_evidence(),
            "source_ref": "source.png",
            "source_bbox": [1, 2, 3, 4],
            "source_sha256": sha(source),
            "copied_to": "editable/g1.png",
            "prompt_file": "not-used",
            "backend": "source-crop",
        }
        incomplete = root / "fallback-incomplete.json"
        incomplete_asset = dict(fallback_asset)
        incomplete_asset.pop("native_retry_evidence")
        incomplete.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [incomplete_asset]}), encoding="utf-8")
        report = validate(incomplete, strict=True)
        assert not report["valid"]
        assert any(item["code"] == "native_retry_evidence_missing" for item in report["errors"])

        fallback = root / "fallback.json"
        fallback.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [fallback_asset]}), encoding="utf-8")
        assert validate(fallback, strict=True)["valid"]
    print("imagegen final-asset policy: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
