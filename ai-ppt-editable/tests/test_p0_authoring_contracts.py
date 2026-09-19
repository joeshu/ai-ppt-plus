from __future__ import annotations
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_authoring_plan import build_plan
from audit_text_coverage import audit
from build_imagegen_asset_jobs import plan as asset_plan

class P0AuthoringContractsTest(unittest.TestCase):
    def test_authoring_plan_compiles_relationships_and_contracts(self):
        inv={"source":{"sha256":"ref"},"objects":[
            {"object_id":"footer","semantic_role":"footer-band","bbox":[0,.82,1,.18]},
            {"object_id":"mark","semantic_role":"pictogram","route":"imagegen_asset","parent_id":"footer","bbox":[.45,.86,.1,.08],"semantic_identity":"5G mark","contour_traits":["italic 5G","superscript n"],"color_contract":{"foreground":"#D71920","host_background":"transparent"}},
            {"object_id":"copy","semantic_role":"body","text":"正文","parent_id":"footer","bbox":[.1,.86,.2,.05],"font_face":"Noto Sans CJK SC","target_lines":1,"text_producer":"add_run"}]}
        result=build_plan(inv); self.assertTrue(result["valid"]); by={o["object_id"]:o for o in result["objects"]}
        self.assertEqual(by["mark"]["implementation_type"],"imagegen_asset"); self.assertEqual(by["mark"]["asset_contract"]["identity"]["semantic_identity"],"5G mark")
        self.assertEqual(by["copy"]["text_contract"]["producer"],"add_run"); self.assertFalse(result["policy"]["visual_threshold_blocker"])

    def test_text_coverage_catches_bypassed_producer(self):
        plan=build_plan({"objects":[{"object_id":"a","semantic_role":"body","text":"A","bbox":[0,0,.2,.1],"font_face":"Noto Sans CJK SC","text_producer":"badge_label"},{"object_id":"b","semantic_role":"body","text":"B","bbox":[0,.2,.2,.1],"font_face":"Noto Sans CJK SC","text_producer":"table_cell"}]})
        ledger={"entries":[{"object_id":"a","slot_bbox":[0,0,.2,.1],"font_face":"Noto Sans CJK SC","fit_evidence":{"fits":True}}]}
        result=audit(plan,ledger); self.assertFalse(result["valid"]); self.assertEqual(result["coverage"],.5); self.assertEqual(result["issues"][0]["object_id"],"b")

    def test_asset_job_cache_key_and_qa_include_identity_and_color(self):
        base={"source":{"sha256":"x"},"assets":[{"asset_id":"i","asset_class":"icon","route":"imagegen_asset","source_bbox":[.1,.2,.2,.2],"alpha_required":True,"prompt":"calendar megaphone","identity_contract":{"semantic_identity":"calendar plus megaphone","contour_traits":["calendar grid","megaphone horn"],"forbidden_substitutions":["generic calendar"]},"color_contract":{"foreground":"#E60012","internal_detail":"#FFFFFF","host_background":"transparent"}}]}
        job=asset_plan(base)["jobs"][0]; self.assertEqual(job["request"]["identity_contract"]["semantic_identity"],"calendar plus megaphone"); self.assertTrue(job["qa"]["identity_compare"]); self.assertTrue(job["qa"]["color_role_compare"]); self.assertIn("identity_contract_pass",job["cache"]["reuse_requires"])
        changed={**base,"assets":[{**base["assets"][0],"color_contract":{"foreground":"#0066CC"}}]}; self.assertNotEqual(job["cache_key"],asset_plan(changed)["jobs"][0]["cache_key"])

if __name__=="__main__": unittest.main()
