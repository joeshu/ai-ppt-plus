import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "text_fit_case_replay.py"
spec = importlib.util.spec_from_file_location("text_fit_case_replay", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


class TextFitCaseReplayTests(unittest.TestCase):
    def _manifest(self, evidence=None):
        return {
            "batch": "knight-textfit-b5",
            "acceptance": {
                "overflow_allowed": 0,
                "font_shrink_last": True,
                "fresh_render_required_after_repair": True,
            },
            "cases": [{
                "id": "real-case",
                "name": "real case",
                "status": "source_resolved",
                "focus": ["dense_chinese"],
                "evidence": evidence or {},
            }],
        }

    def test_missing_real_evidence_is_not_run_not_fake_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = mod.evaluate(self._manifest(), root=Path(tmp))
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["summary"], {
            "case_count": 1, "pass_count": 0, "fail_count": 0, "not_run_count": 1,
        })
        self.assertEqual(report["cases"][0]["status"], "NOT_RUN")

    def test_current_b1_b4_evidence_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fit.json").write_text(json.dumps({
                "valid": True,
                "slots": [{"object_id": "title", "fits": True, "repair": {"font_shrink_last": True}}],
            }), encoding="utf-8")
            (root / "feedback.json").write_text(json.dumps({
                "valid": True,
                "records": [{
                    "object_id": "title", "repair_required": True,
                    "repair": {"requires_fresh_render": True},
                }],
            }), encoding="utf-8")
            report = mod.evaluate(self._manifest({
                "text_fit_report": "fit.json",
                "text_render_feedback": "feedback.json",
            }), root=root)
        self.assertTrue(report["release_ready"])
        self.assertEqual(report["cases"][0]["status"], "PASS")

    def test_overflow_or_wrong_repair_order_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fit.json").write_text(json.dumps({
                "valid": True,
                "slots": [{"object_id": "body", "fits": False, "repair": {"font_shrink_last": False}}],
            }), encoding="utf-8")
            (root / "feedback.json").write_text(json.dumps({"valid": True, "records": []}), encoding="utf-8")
            report = mod.evaluate(self._manifest({
                "text_fit_report": "fit.json",
                "text_render_feedback": "feedback.json",
            }), root=root)
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["cases"][0]["status"], "FAIL")
        failed = {row["name"] for row in report["cases"][0]["checks"] if not row["passed"]}
        self.assertEqual(failed, {"no_text_overflow", "font_shrink_last"})

    def test_root_and_editable_replay_scripts_are_identical(self):
        mirror = ROOT / "ai-ppt-editable" / "scripts" / "text_fit_case_replay.py"
        self.assertEqual(SCRIPT.read_bytes(), mirror.read_bytes())

    def test_frozen_batch5_manifest_keeps_four_real_case_slots(self):
        manifest = json.loads((ROOT / "evals" / "text-fit-batch5" / "cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["cases"]), 4)
        self.assertEqual({row["id"] for row in manifest["cases"]}, {
            "china-unicom-downgrade-control",
            "social-channel-commission-table",
            "mixed-cjk-latin-flow",
            "kpi-metric-card",
        })
        self.assertTrue(manifest["acceptance"]["native_text_required"])
        self.assertEqual(manifest["acceptance"]["whole_slide_raster_allowed"], 0)


if __name__ == "__main__":
    unittest.main()
