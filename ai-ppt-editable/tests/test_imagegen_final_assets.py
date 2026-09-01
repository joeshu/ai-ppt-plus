#!/usr/bin/env python3
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_imagegen_final_assets import validate


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="imagegen-final-") as folder:
        root = Path(folder)
        good = root / "good.json"
        good.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "i1", "asset_class": "icon", "provenance_mode": "imagegen", "generated_source": "gen/i1.png", "copied_to": "editable/i1.png", "prompt_file": "prompts/i1.txt", "backend": "codex-imagegen"}, {"asset_id": "logo", "asset_class": "logo", "provenance_mode": "official"}]}), encoding="utf-8")
        assert validate(good, strict=True)["valid"]
        bad = root / "bad.json"
        bad.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "g1", "asset_class": "gradient_visual", "provenance_mode": "source_reuse", "source_reuse": True}]}), encoding="utf-8")
        report = validate(bad, strict=True)
        assert not report["valid"]
        assert any(item["code"] == "final_asset_not_imagegen" for item in report["errors"])
        fallback = root / "fallback.json"
        fallback.write_text(json.dumps({"provenance_policy": "imagegen_final_assets", "assets": [{"asset_id": "g1", "asset_class": "icon", "provenance_mode": "source_reuse", "fallback_decision": "user_approved", "decision_id": "decision-1", "decision_reason": "user selected crop", "decision_timestamp": "2026-09-01T00:00:00Z", "source_ref": "source.png", "source_bbox": [1, 2, 3, 4], "source_sha256": "abc", "copied_to": "editable/g1.png", "prompt_file": "not-used", "backend": "source-crop"}]}), encoding="utf-8")
        assert validate(fallback, strict=True)["valid"]
    print("imagegen final-asset policy: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
