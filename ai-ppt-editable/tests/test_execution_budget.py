import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from execution_budget import imagegen_usage,validate_usage

def main():
    fast=validate_usage("fast",candidate_build_count=2,full_render_count=2,imagegen_call_count=3,imagegen_retry_counts={"a":1})
    assert fast["valid"],fast
    blocked=validate_usage("fast",candidate_build_count=3,full_render_count=2,imagegen_call_count=4,imagegen_retry_counts={"a":2})
    codes={x["code"] for x in blocked["issues"]}
    assert {"candidate_build_budget_exceeded","imagegen_retry_budget_exceeded"} <= codes
    assert not validate_usage("ci",candidate_build_count=0,full_render_count=0,imagegen_call_count=0,imagegen_retry_counts={})["valid"]
    with tempfile.TemporaryDirectory() as folder:
        assert imagegen_usage(Path(folder)) == (0,{})
        project=Path(folder)
        (project/"imagegen-assets-manifest.json").write_text(json.dumps({"assets":[
            {"asset_id":"a","provenance_mode":"imagegen","generation_batch_id":"batch-1","generation_attempts":1},
            {"asset_id":"b","provenance_mode":"imagegen","generation_batch_id":"batch-1","generation_attempts":1},
            {"asset_id":"c","provenance_mode":"imagegen","generation_request_id":"request-c","generation_attempts":2,"retry_count":1},
        ]}),encoding="utf-8")
        calls,retries=imagegen_usage(project)
        assert calls==3,(calls,retries)
        assert retries=={"a":0,"b":0,"c":1}
    print("execution budget contracts: ok")
if __name__=="__main__": main()
