#!/usr/bin/env python3
"""Plan deterministic per-asset ImageGen jobs from a PageGraph/asset manifest.

The planner never calls a generator itself. It emits one isolated job per
imagegen_asset, stable cache keys, QA requirements and retry responsibility so
an orchestrator can invoke native ImageGen without rebuilding the whole slide.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

NATIVE={"formal_text","text","data","chart_data","native_shape","line","simple_shape","table"}

def stable_hash(obj):
    raw=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def route(item):
    explicit=str(item.get("route","")).lower()
    if explicit in {"native_editable","imagegen_asset"}: return explicit
    cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
    return "native_editable" if cls in NATIVE else "imagegen_asset"

def plan(data):
    source=data.get("source",{}); jobs=[]; native=[]
    for i,item in enumerate(data.get("assets",[]),1):
        aid=item.get("asset_id") or item.get("id") or f"asset-{i}"
        r=route(item)
        if r=="native_editable": native.append(aid); continue
        ref={"source_sha256":source.get("sha256"),"asset_id":aid,"asset_class":item.get("asset_class"),"source_bbox":item.get("source_bbox"),"aspect_ratio":item.get("aspect_ratio"),"prompt":item.get("prompt"),"alpha_required":item.get("alpha_required",True)}
        key=stable_hash(ref)
        jobs.append({
          "job_id":f"imagegen-{aid}-{key[:12]}","asset_id":aid,"route":"imagegen_asset","cache_key":key,
          "reference":ref,"output":f"assets/imagegen/{aid}.png","prompt_file":f"assets/prompts/{aid}.txt",
          "qa":{"independent_asset":True,"contact_sheet_forbidden":True,"transparent_rgba":bool(ref["alpha_required"]),"visible_alpha_bbox":True,"alpha_centroid":True,"placement_bbox":True,"local_crop_compare":True},
          "retry_scope":"asset_only","source_reuse":"forbidden_without_user_approved_fallback"
        })
    return {"schema":"ai-ppt-plus/imagegen-asset-jobs/v1","source":source,"native_editable_assets":native,"jobs":jobs,"job_count":len(jobs),"cache_policy":"reuse only when cache_key and QA-pass evidence both match","failure_policy":"retry only failing asset; never silently source-reuse"}

def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    result=plan(json.loads(a.input.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"job_count":result["job_count"],"output":str(a.output)}))
if __name__=="__main__": main()
