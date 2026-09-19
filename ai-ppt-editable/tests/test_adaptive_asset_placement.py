import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from asset_placement import adaptive_alpha_fit


class AdaptiveAssetPlacementTest(unittest.TestCase):
    @staticmethod
    def _asset(path: Path, *, size=(100, 100), box=(20, 20, 80, 80), alpha=255):
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                im.putpixel((x, y), (220, 0, 20, alpha))
        im.save(path)

    def test_balanced_safe_padding_preserves_canvas_slot_relationship(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "icon.png"
            self._asset(p, box=(18, 18, 82, 82))
            placed, evidence = adaptive_alpha_fit(p, 100, 200, 300, 300, return_evidence=True)
            self.assertEqual(placed, (100, 200, 300, 300))
            self.assertEqual(evidence["placement_mode"], "canvas-slot-fit")

    def test_asymmetric_padding_falls_back_to_alpha_centroid_fit(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "icon.png"
            self._asset(p, box=(5, 20, 65, 80))
            placed, evidence = adaptive_alpha_fit(p, 100, 200, 300, 300, return_evidence=True)
            self.assertNotEqual(placed, (100, 200, 300, 300))
            self.assertEqual(evidence["placement_mode"], "alpha-centroid-fit-contained")
            vx, vy, vw, vh = evidence["placed_visible_bbox"]
            self.assertGreaterEqual(vx, 100 - 1)
            self.assertGreaterEqual(vy, 200 - 1)
            self.assertLessEqual(vx + vw, 400 + 1)
            self.assertLessEqual(vy + vh, 500 + 1)

    def test_reference_visible_bbox_overrides_automatic_policy(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "icon.png"
            self._asset(p, box=(20, 20, 80, 80))
            _, evidence = adaptive_alpha_fit(
                p, 100, 200, 300, 300,
                reference_visible_bbox_norm=[0.20, 0.10, 0.50, 0.60],
                return_evidence=True,
            )
            self.assertEqual(evidence["placement_mode"], "reference-visible-fit")
            fx, fy, fw, fh = evidence["visible_bbox_fraction_of_slot"]
            self.assertAlmostEqual(fx + fw / 2.0, 0.45, delta=0.01)
            self.assertAlmostEqual(fy + fh / 2.0, 0.40, delta=0.01)
            self.assertLessEqual(fw, 0.50 + 0.01)
            self.assertLessEqual(fh, 0.60 + 0.01)


if __name__ == "__main__":
    unittest.main()
