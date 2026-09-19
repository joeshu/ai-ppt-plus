#!/usr/bin/env python3
"""Build executable, deterministic per-asset ImageGen jobs."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
NATIVE={"formal_text","text","data","chart_data","native_shape","line","simple_shape","table"}
ICON_CLASSES={"icon","icon_asset","glyph","pictogram","badge"}
def stable_hash(obj): return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def route(item):
    explicit=str(item.get("route","")).lower()
    if explicit in {"native_editable","imagegen_asset"}: return explicit
    cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
    return "native_editable" if cls in NATIVE else "imagegen_asset"
def _crop(box,pad=.25):
    if not isinstance(box,(list,tuple)) or len(box)!=4: return None
    x,y,w,h=map(float,box); px,py=w*pad,h*pad
    return [max(0,x-px),max(0,y-py),min(1,x+w+px),min(1,y+h+py)]
def _contract_prompt(contract):
    if not isinstance(contract,dict): return ""
    identity=contract.get("semantic_identity") or {}; subject=str(identity.get("subject") or "").strip()
    preserve=[str(x).strip() for x in identity.get("must_preserve") or [] if str(x).strip()]
    forbidden=[str(x).strip() for x in identity.get("forbidden_substitutions") or [] if str(x).strip()]
    contours=[str(x).strip() for x in contract.get("contour_traits") or [] if str(x).strip()]
    colors=[]
    for row in contract.get("color_roles") or []:
        if isinstance(row,dict) and row.get("role") and row.get("hex"): colors.append(f"{row['role']}={row['hex']}")
    parts=[]
    if subject: parts.append(f"semantic subject: {subject}")
    if preserve: parts.append("must preserve: "+", ".join(preserve))
    if contours: parts.append("contour traits: "+", ".join(contours))
    if colors: parts.append("color roles: "+", ".join(colors))
    if forbidden: parts.append("forbidden substitutions: "+", ".join(forbidden))
    if contract.get("alpha",{}).get("required") is True: parts.append("true transparent RGBA background with clean transparent edges")
    return "; ".join(parts)
def _generation_prompt(item,contract):
    base=str(item.get("prompt") or "").strip(); suffix=_contract_prompt(contract)
    if base and suffix: return base+"\nAsset identity/color contract: "+suffix
    return base or suffix
def plan(data):
    source=data.get("source",{}); jobs=[]; native=[]
    for i,item in enumerate(data.get("assets",[]),1):
        aid=item.get("asset_id") or item.get("id") or f"asset-{i}"; r=route(item)
        if r=="native_editable": native.append(aid); continue
        bbox=item.get("source_bbox") or item.get("placement_bbox")
        cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
        ref_visible=item.get("reference_visible_bbox_norm"); contract=item.get("asset_contract")
        alpha_contract=contract.get("alpha",{}) if isinstance(contract,dict) else {}
        alpha_required=bool(alpha_contract.get("required",item.get("alpha_required",True)))
        prompt=_generation_prompt(item,contract)
        ref={"source_sha256":source.get("sha256"),"asset_id":aid,"asset_class":item.get("asset_class"),"source_bbox":bbox,"aspect_ratio":item.get("aspect_ratio"),"prompt":prompt,"alpha_required":alpha_required,"asset_contract":contract}
        if ref_visible is not None: ref["reference_visible_bbox_norm"]=list(ref_visible)
        key=stable_hash(ref)
        placement_mode="adaptive-alpha-fit" if alpha_required and cls in ICON_CLASSES else ("alpha-centroid-fit" if alpha_required else "slot-bbox")
        request={"object_id":aid,"generation_prompt":prompt,"asset_contract":contract,"background_mode":"transparent" if alpha_required else "opaque","preserve_geometry":{"x":bbox[0],"y":bbox[1],"w":bbox[2],"h":bbox[3]} if isinstance(bbox,(list,tuple)) and len(bbox)==4 else {},"align_visible_alpha":alpha_required,"placement_mode":placement_mode,"cache_key":key,"retry_scope":"asset_only"}
        if ref_visible is not None: request["reference_visible_bbox_norm"]=list(ref_visible)
        qa={"independent_asset":True,"contact_sheet_forbidden":True,"transparent_rgba":alpha_required,"visible_alpha_bbox":True,"alpha_centroid":True,"placement_bbox":True,"local_crop_compare":True,"local_crop_bbox":_crop(bbox),"identity_contract_required":True,"semantic_identity_compare":True,"contour_identity_compare":True,"color_role_compare":True,"failure_classes":["placement_only","identity_or_color","alpha_or_clipping"]}
        if ref_visible is not None: qa["placement_geometry_compare"]=True
        jobs.append({"job_id":f"imagegen-{aid}-{key[:12]}","asset_id":aid,"route":"imagegen_asset","cache_key":key,"asset_contract":contract,"contract_complete":isinstance(contract,dict) and contract.get("schema")=="ai-ppt-plus/asset-identity-contract/v1","reference":ref,"output":f"assets/imagegen/{aid}.png","prompt_file":f"assets/prompts/{aid}.txt","request":request,"cache":{"evidence":f"assets/cache/{aid}-{key}.json","reuse_requires":["cache_key_match","asset_sha256_match","asset_identity_color_pass","alpha_geometry_pass","local_crop_qa_pass"]},"handoff":{"validator":"reconstruction.asset_orchestrator.validate_generated_asset","binder":"reconstruction.asset_orchestrator.bind_generated_asset","placement":"scripts.asset_placement.adaptive_alpha_fit" if placement_mode=="adaptive-alpha-fit" else ("scripts.asset_placement.alpha_centroid_fit" if alpha_required else "slot-bbox")},"qa":qa,"retry_scope":"asset_only","retry":{"policy":"reconstruction.asset_retry_policy.next_retry_request","max_native_attempts":3,"scope":"asset_only","transparent_edit_before_chroma":True,"automatic_source_reuse":False,"placement_only_consumes_generation_attempt":False,"identity_or_color_requires_regeneration":True},"state_order":["cache_lookup","native_imagegen","validate_bytes","measure_alpha_geometry","validate_identity_color","bind_alpha_centroid","render_local_crop","asset_visual_qa","cache_commit_or_asset_retry"],"source_reuse":"forbidden_without_user_approved_fallback"})
    return {"schema":"ai-ppt-plus/imagegen-asset-jobs/v3","source":source,"native_editable_assets":native,"jobs":jobs,"job_count":len(jobs),"cache_policy":"reuse only when cache key, delivered hash, identity/color contract, alpha geometry and local-crop QA evidence all pass","failure_policy":"placement-only repair does not consume regeneration; identity/color or alpha failure retries only failing asset; never silently source-reuse"}
def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); r=plan(json.loads(a.input.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"job_count":r["job_count"],"output":str(a.output)}))
if __name__=="__main__": main()
