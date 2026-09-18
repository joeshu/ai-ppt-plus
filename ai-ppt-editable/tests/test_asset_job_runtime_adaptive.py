import unittest
from types import SimpleNamespace

from reconstruction.asset_job_runtime import _placement_from_result, _placement_geometry_qa


class RuntimeAdaptivePlacementTest(unittest.TestCase):
    @staticmethod
    def _result(*, bbox=(.18, .18, .82, .82), centroid=(.5, .5), size=(100, 100)):
        return SimpleNamespace(visible_alpha_bbox=bbox, alpha_centroid=centroid, width=size[0], height=size[1])

    def test_balanced_icon_uses_canvas_slot_fit(self):
        placement, evidence = _placement_from_result(
            self._result(), (100, 100, 300, 300),
            {"align_visible_alpha": True, "placement_mode": "adaptive-alpha-fit"},
        )
        self.assertEqual(placement, (100, 100, 300, 300))
        self.assertEqual(evidence["mode"], "canvas-slot-fit")

    def test_asymmetric_icon_uses_alpha_centroid(self):
        placement, evidence = _placement_from_result(
            self._result(bbox=(.02, .2, .62, .8), centroid=(.31, .5)), (100, 100, 300, 300),
            {"align_visible_alpha": True, "placement_mode": "adaptive-alpha-fit"},
        )
        self.assertNotEqual(placement, (100, 100, 300, 300))
        self.assertEqual(evidence["mode"], "alpha-centroid-fit-contained")

    def test_reference_visible_bbox_overrides_automatic_policy(self):
        _, evidence = _placement_from_result(
            self._result(), (100, 100, 300, 300),
            {"align_visible_alpha": True, "placement_mode": "adaptive-alpha-fit", "reference_visible_bbox_norm": [.2, .1, .5, .6]},
        )
        self.assertEqual(evidence["mode"], "reference-visible-fit")

    def test_geometry_qa_marks_placement_only_failure(self):
        q = _placement_geometry_qa([.1, .2, .5, .5], [.16, .2, .5, .5])
        self.assertFalse(q["approved"])
        self.assertEqual(q["repair_scope"], "placement_only")
        self.assertIn("local_crop_centroid_drift", q["issue_codes"])


if __name__ == "__main__":
    unittest.main()
