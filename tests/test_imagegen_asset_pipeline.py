import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
planner=load("ai-ppt-editable/scripts/build_imagegen_asset_jobs.py","planner")
validator=load("ai-ppt-editable/scripts/validate_imagegen_final_assets.py","validator")

def test_brand_routes_directly_to_imagegen():
    data={"source":{"sha256":"a"*64},"assets":[{"asset_id":"logo","asset_class":"brand_lockup","source_bbox":[0,0,1,1]},{"asset_id":"body","asset_class":"formal_text"},{"asset_id":"footer","asset_class":"brand_band","source_bbox":[0,0,10,1]}]}
    r=planner.plan(data)
    assert [j["asset_id"] for j in r["jobs"]]==["logo","footer"]
    assert r["native_editable_assets"]==["body"]
    assert all(j["retry_scope"]=="asset_only" for j in r["jobs"])
    assert all(j["qa"]["contact_sheet_forbidden"] for j in r["jobs"])

def test_cache_key_is_deterministic_and_bbox_sensitive():
    base={"source":{"sha256":"b"*64},"assets":[{"asset_id":"x","asset_class":"logo","source_bbox":[1,2,3,4]}]}
    a=planner.plan(base)["jobs"][0]["cache_key"]; b=planner.plan(base)["jobs"][0]["cache_key"]
    base["assets"][0]["source_bbox"]=[1,2,3,5]; c=planner.plan(base)["jobs"][0]["cache_key"]
    assert a==b and a!=c

def test_validator_has_no_brand_exception(tmp_path):
    manifest=tmp_path/"m.json"; manifest.write_text('{"provenance_policy":"imagegen_final_assets","assets":[{"asset_id":"logo","asset_class":"brand_lockup","provenance_mode":"source_reuse"}]}',encoding="utf-8")
    r=validator.validate(manifest)
    codes={e["code"] for e in r["errors"]}
    assert "final_asset_not_imagegen" in codes

def test_validator_requires_alpha_geometry(tmp_path):
    manifest=tmp_path/"m.json"; manifest.write_text('{"provenance_policy":"imagegen_final_assets","assets":[{"asset_id":"logo","asset_class":"logo","provenance_mode":"imagegen","generated_source":"g.png","copied_to":"c.png","prompt_file":"p.txt","backend":"native-imagegen","independent_asset":true}]}',encoding="utf-8")
    r=validator.validate(manifest)
    missing=[e for e in r["errors"] if e["code"]=="alpha_geometry_evidence_missing"]
    assert {e["field"] for e in missing}=={"visible_alpha_bbox","alpha_centroid","placement_bbox"}
