import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_imagegen_asset_jobs import plan


class AdaptiveImagegenJobPlanningTest(unittest.TestCase):
    def test_icon_defaults_to_adaptive_alpha_fit(self):
        data = {"source": {"sha256": "x"}, "assets": [{"asset_id": "i", "asset_class": "icon", "route": "imagegen_asset", "source_bbox": [.1, .2, .2, .2], "alpha_required": True, "prompt": "icon"}]}
        job = plan(data)["jobs"][0]
        self.assertEqual(job["request"]["placement_mode"], "adaptive-alpha-fit")
        self.assertEqual(job["handoff"]["placement"], "scripts.asset_placement.adaptive_alpha_fit")

    def test_reference_visible_geometry_is_propagated(self):
        data = {"source": {"sha256": "x"}, "assets": [{"asset_id": "i", "asset_class": "icon", "route": "imagegen_asset", "source_bbox": [.1, .2, .2, .2], "reference_visible_bbox_norm": [.2, .1, .5, .6], "alpha_required": True, "prompt": "icon"}]}
        job = plan(data)["jobs"][0]
        self.assertEqual(job["request"]["reference_visible_bbox_norm"], [.2, .1, .5, .6])
        self.assertTrue(job["qa"]["placement_geometry_compare"])

    def test_brand_art_keeps_alpha_centroid_fit_for_backward_compatibility(self):
        data = {"source": {"sha256": "x"}, "assets": [{"asset_id": "b", "asset_class": "brand_lockup", "route": "imagegen_asset", "source_bbox": [.1, .2, .2, .2], "alpha_required": True, "prompt": "brand"}]}
        job = plan(data)["jobs"][0]
        self.assertEqual(job["request"]["placement_mode"], "alpha-centroid-fit")
        self.assertNotIn("placement_geometry_compare", job["qa"])


if __name__ == "__main__":
    unittest.main()
