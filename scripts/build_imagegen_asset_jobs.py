#!/usr/bin/env python3
"""Build executable, deterministic per-asset ImageGen jobs.

Each visual asset owns its cache key, native-generation request, alpha-geometry
handoff, local-crop QA and bounded retry state.  A failing icon never forces a
full-slide regeneration and source reuse is never selected silently.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

NATIVE={"formal_text","text","data","chart_data","native_shape","line","simple_shape","table"}

def stable_hash(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def route(item):
    explicit=str(item.get("route","")).lower()
    if explicit in {"native_editable","imagegen_asset"}: return explicit
    cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
    return "native_editable" if cls in NATIVE else "imagegen_asset"

def _crop(box,pad=.25):
    if not isinstance(box,(list,tuple)) or len(box)!=4: return None
    x,y,w,h=map(float,box); px,py=w*pad,h*pad
    return [max(0,x-px),max(0,y-py),min(1,x+w+px),min(1,y+h+py)]

def plan(data):
    source=data.get("source",{}); jobs=[]; native=[]
    for i,item in enumerate(data.get("assets",[]),1):
        aid=item.get("asset_id") or item.get("id") or f"asset-{i}"; r=route(item)
        if r=="native_editable": native.append(aid); continue
        bbox=item.get("source_bbox") or item.get("placement_bbox")
        ref={"source_sha256":source.get("sha256"),"asset_id":aid,"asset_class":item.get("asset_class"),"source_bbox":bbox,"aspect_ratio":item.get("aspect_ratio"),"prompt":item.get("prompt"),"alpha_required":item.get("alpha_required",True)}
        key=stable_hash(ref); output=f"assets/imagegen/{aid}.png"; prompt_file=f"assets/prompts/{aid}.txt"
        request={"object_id":aid,"generation_prompt":item.get("prompt"),"background_mode":"transparent" if ref["alpha_required"] else "opaque","preserve_geometry":{"x":bbox[0],"y":bbox[1],"w":bbox[2],"h":bbox[3]} if isinstance(bbox,(list,tuple)) and len(bbox)==4 else {},"align_visible_alpha":bool(ref["alpha_required"]),"placement_mode":"alpha-centroid-fit" if ref["alpha_required"] else "slot-bbox","cache_key":key,"retry_scope":"asset_only"}
        jobs.append({
            "job_id":f"imagegen-{aid}-{key[:12]}","asset_id":aid,"route":"imagegen_asset","cache_key":key,"reference":ref,
            "output":output,"prompt_file":prompt_file,"request":request,
            "cache":{"evidence":f"assets/cache/{aid}-{key}.json","reuse_requires":["cache_key_match","asset_sha256_match","alpha_geometry_pass","local_crop_qa_pass"]},
            "handoff":{"validator":"reconstruction.asset_orchestrator.validate_generated_asset","binder":"reconstruction.asset_orchestrator.bind_generated_asset","placement":"scripts.asset_placement.alpha_centroid_fit" if ref["alpha_required"] else "slot-bbox"},
            "qa":{"independent_asset":True,"contact_sheet_forbidden":True,"transparent_rgba":bool(ref["alpha_required"]),"visible_alpha_bbox":True,"alpha_centroid":True,"placement_bbox":True,"local_crop_compare":True,"local_crop_bbox":_crop(bbox)},
            "retry":{"policy":"reconstruction.asset_retry_policy.next_retry_request","max_native_attempts":3,"scope":"asset_only","transparent_edit_before_chroma":True,"automatic_source_reuse":False},
            "state_order":["cache_lookup","native_imagegen","validate_bytes","measure_alpha_geometry","bind_alpha_centroid","render_local_crop","asset_visual_qa","cache_commit_or_asset_retry"],
            "source_reuse":"forbidden_without_user_approved_fallback"
        })
    return {"schema":"ai-ppt-plus/imagegen-asset-jobs/v2","source":source,"native_editable_assets":native,"jobs":jobs,"job_count":len(jobs),"cache_policy":"reuse only when cache key, delivered hash, alpha geometry and local-crop QA evidence all pass","failure_policy":"retry only failing asset; never silently source-reuse"}

def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    result=plan(json.loads(a.input.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"job_count":result["job_count"],"output":str(a.output)}))
if __name__=="__main__": main()
