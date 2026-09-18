import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evals" / "beat-knight"


class BeatKnightV6EvidenceTest(unittest.TestCase):
    def test_post_alpha_v6_result_is_fixed_three_win_zero_loss(self):
        result = json.loads((EVAL / "降套管控-1536x864-v6-result.json").read_text(encoding="utf-8"))
        self.assertTrue(result["beat_knight"])
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["source_crop_fallback_count"], 0)
        self.assertEqual(result["contact_sheet_ancestry_count"], 0)
        self.assertEqual(result["text_fit"]["overflow_count"], 0)
        self.assertEqual(result["text_fit"]["geometry_defect_count"], 0)
        self.assertTrue(result["layer_audit_valid"])
        self.assertTrue(result["native_editability_valid"])
        ab = result["five_dimensional_ab"]
        self.assertEqual(ab["strict_win_count"], 3)
        self.assertEqual(ab["loss_dimensions"], [])
        self.assertEqual(ab["decision"], "candidate_win")
        self.assertEqual(ab["dimensions"]["pixel"]["verdict"], "win")
        self.assertEqual(ab["dimensions"]["icon_asset"]["verdict"], "win")
        self.assertEqual(ab["dimensions"]["local_crop"]["verdict"], "win")
        self.assertEqual(ab["dimensions"]["text"]["verdict"], "tie")
        self.assertEqual(ab["dimensions"]["object"]["verdict"], "tie")
        self.assertFalse(result["pixel"]["legacy_standard_090_gate_valid"])
        self.assertTrue(result["pixel"]["competitive_relative_gate_valid"])

    def test_problem_assets_are_independent_native_imagegen_outputs(self):
        provenance = json.loads((EVAL / "降套管控-1536x864-v6-provenance.json").read_text(encoding="utf-8"))
        assets = {item["asset_id"]: item for item in provenance["assets"]}
        self.assertEqual(set(assets), {"brand-logo-lockup", "service-calligraphy-lockup", "bottom-brand-band"})
        for item in assets.values():
            self.assertEqual(item["generation_mode"], "native_image_generation")
            self.assertFalse(item["source_crop_fallback"])
            self.assertFalse(item["contact_sheet_ancestry"])
            self.assertEqual(len(item["final_sha256"]), 64)
            self.assertEqual(len(item["raw_imagegen_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
