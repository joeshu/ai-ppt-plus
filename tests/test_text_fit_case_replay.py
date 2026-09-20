import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SCRIPT=ROOT/"scripts"/"text_fit_case_replay.py";spec=importlib.util.spec_from_file_location("text_fit_case_replay",SCRIPT);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod)
class TextFitCaseReplayTests(unittest.TestCase):
    def _manifest(self,evidence=None,status="source_resolved"):
        return {"batch":"knight-textfit-b5","acceptance":{"text_loss_allowed":0,"overflow_allowed":0,"whole_slide_raster_allowed":0,"native_text_required":True,"font_shrink_last":True,"fresh_render_required_after_repair":True},"cases":[{"id":"real-case","name":"real case","status":status,"source":{"kind":"file_library","ref":"real-source.pptx"},"focus":["dense_chinese"],"evidence":evidence or {}}]}
    def _write_complete(self,root:Path,*,overflow=False,fresh=True,native=1):
        (root/"fit.json").write_text(json.dumps({"valid":True,"all_slots_measured":True,"slots":[{"object_id":"title","target_fits":not overflow,"repair":{"font_shrink_last":True}}]}),encoding="utf-8")
        (root/"feedback.json").write_text(json.dumps({"valid":True,"records":[{"object_id":"title","repair_required":True,"repair":{"requires_fresh_render":True},"reference":{"render_sha256":"a"*64},"candidate":{"render_sha256":"b"*64}}]}),encoding="utf-8")
        (root/"coverage.json").write_text(json.dumps({"valid":True,"status":"passed","uncovered_native_text":[]}),encoding="utf-8")
        (root/"editable.json").write_text(json.dumps({"valid":True,"summary":{"whole_slide_raster_count":0,"native_text_count":native}}),encoding="utf-8")
        (root/"provenance.json").write_text(json.dumps({"valid":True,"fresh_candidate_render":fresh,"candidate_artifact_sha256":"c"*64,"rendered_from_candidate_sha256":"c"*64}),encoding="utf-8")
        return {"text_fit_report":"fit.json","text_render_feedback":"feedback.json","text_coverage_audit":"coverage.json","editability_audit":"editable.json","render_provenance":"provenance.json"}
    def test_missing_real_evidence_is_not_run_not_fake_pass(self):
        with tempfile.TemporaryDirectory() as tmp:report=mod.evaluate(self._manifest(),root=Path(tmp))
        self.assertFalse(report["release_ready"]);self.assertEqual(report["cases"][0]["status"],"NOT_RUN");self.assertEqual(set(report["cases"][0]["missing_evidence"]),{"text_fit_report","text_render_feedback","text_coverage_audit","editability_audit","render_provenance"})
    def test_unresolved_real_source_is_not_run_even_with_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self._write_complete(root);report=mod.evaluate(self._manifest(evidence,status="source_reference_missing"),root=root)
        self.assertEqual(report["cases"][0]["status"],"NOT_RUN");self.assertEqual(report["cases"][0]["missing_evidence"],["source_reference"]);self.assertFalse(report["release_ready"])
    def test_complete_b1_b4_evidence_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self._write_complete(root);report=mod.evaluate(self._manifest(evidence),root=root)
        self.assertTrue(report["release_ready"]);self.assertEqual(report["cases"][0]["status"],"PASS")
    def test_stale_render_or_missing_native_text_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self._write_complete(root,fresh=False,native=0);report=mod.evaluate(self._manifest(evidence),root=root)
        failed={x["name"] for x in report["cases"][0]["checks"] if not x["passed"]};self.assertEqual(report["cases"][0]["status"],"FAIL");self.assertIn("fresh_candidate_render",failed);self.assertIn("native_text_present",failed)
    def test_overflow_fails_even_with_other_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self._write_complete(root,overflow=True);report=mod.evaluate(self._manifest(evidence),root=root)
        failed={x["name"] for x in report["cases"][0]["checks"] if not x["passed"]};self.assertIn("no_text_overflow",failed)
    def test_root_and_editable_replay_scripts_are_identical(self):
        self.assertEqual(SCRIPT.read_bytes(),(ROOT/"ai-ppt-editable"/"scripts"/"text_fit_case_replay.py").read_bytes())
    def test_frozen_manifest_has_four_real_cases_and_complete_evidence_contract(self):
        manifest=json.loads((ROOT/"evals"/"text-fit-batch5"/"cases.json").read_text(encoding="utf-8"));self.assertEqual(len(manifest["cases"]),4);required={"text_fit_report","text_render_feedback","text_coverage_audit","editability_audit","render_provenance"}
        for row in manifest["cases"]:self.assertEqual(set(row["evidence"]),required)
        status={row["id"]:row["status"] for row in manifest["cases"]};self.assertEqual(status["china-unicom-downgrade-control"],"source_resolved");self.assertEqual(sum(v=="source_resolved" for v in status.values()),4);unicom=next(row for row in manifest["cases"] if row["id"]=="china-unicom-downgrade-control");self.assertEqual(unicom["source"]["sha256"],"036a0c6877bd9fd25541fcb38313a67d2bfef14c911f673f0e5c1a8d9be8ec99");self.assertEqual(unicom["source"]["pixel_size"],[1536,864]);self.assertEqual(unicom["source"]["aspect_ratio"],"16:9")
if __name__=="__main__":unittest.main()
