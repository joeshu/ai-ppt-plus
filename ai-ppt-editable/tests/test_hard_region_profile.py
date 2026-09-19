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
    def _run(self, profile):
        module = _module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = Image.new("RGB", (120, 80), "white")
            candidate = Image.new("RGB", (120, 80), "black")
            spec = {"regions": [{"id": "r", "bbox": [0, 0, 1, 1], "min_layout_ssim": 0.90, "min_pixel_fidelity": 0.90}]}
            return module.evaluate(source, candidate, spec, root, profile=profile)

    def test_standard_threshold_is_repair_diagnostic_not_hard_gate(self):
        report = self._run("standard")
        self.assertTrue(report["valid"])
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual(report["diagnostic_absolute_failure_count"], 1)
        self.assertTrue(report["repair_loop_required"])
        self.assertEqual(report["gate_mode"], "repair_diagnostic")
        self.assertFalse(report["regions"][0]["absolute_threshold_applied"])

    def test_competitive_ab_uses_same_nonblocking_repair_semantics(self):
        report = self._run("competitive_ab")
        self.assertTrue(report["valid"])
        self.assertEqual(report["failure_count"], 0)
        self.assertEqual(report["diagnostic_absolute_failure_count"], 1)
        self.assertTrue(report["repair_loop_required"])
        self.assertEqual(report["gate_mode"], "repair_diagnostic")
        self.assertFalse(report["regions"][0]["absolute_threshold_applied"])


if __name__ == "__main__":
    unittest.main()
