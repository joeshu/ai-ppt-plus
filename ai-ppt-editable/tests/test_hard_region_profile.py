import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hard_region_crop_gate.py"


def _module():
    spec = importlib.util.spec_from_file_location("hard_region_crop_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HardRegionProfileTest(unittest.TestCase):
    def test_standard_keeps_absolute_threshold(self):
        module = _module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = Image.new("RGB", (120, 80), "white")
            candidate = Image.new("RGB", (120, 80), "black")
            spec = {"regions": [{"id": "r", "bbox": [0, 0, 1, 1], "min_layout_ssim": 0.90, "min_pixel_fidelity": 0.90}]}
            report = module.evaluate(source, candidate, spec, root, profile="standard")
            self.assertFalse(report["valid"])
            self.assertEqual(report["failure_count"], 1)
            self.assertEqual(report["gate_mode"], "absolute_regional")

    def test_competitive_ab_is_diagnostic_not_hidden_090_blocker(self):
        module = _module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = Image.new("RGB", (120, 80), "white")
            candidate = Image.new("RGB", (120, 80), "black")
            spec = {"regions": [{"id": "r", "bbox": [0, 0, 1, 1], "min_layout_ssim": 0.90, "min_pixel_fidelity": 0.90}]}
            report = module.evaluate(source, candidate, spec, root, profile="competitive_ab")
            self.assertTrue(report["valid"])
            self.assertEqual(report["failure_count"], 0)
            self.assertEqual(report["diagnostic_absolute_failure_count"], 1)
            self.assertEqual(report["gate_mode"], "competitive_relative_diagnostic")
            self.assertFalse(report["regions"][0]["absolute_threshold_applied"])


if __name__ == "__main__":
    unittest.main()
