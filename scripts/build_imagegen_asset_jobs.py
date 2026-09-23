#!/usr/bin/env python3
"""Build executable, deterministic per-asset ImageGen jobs."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
NATIVE={"formal_text","text","data","chart_data","native_shape","line","simple_shape","table"}
ICON_CLASSES={"icon","icon_asset","glyph","pictogram","badge"}
NEVER_BATCH_CLASSES={"brand","brand_asset","brand_lockup","logo","calligraphic_slogan","brand_band","gradient_visual","illustration"}
BRAND_CLASSES={"brand","brand_asset","brand_lockup","brand_logo","brand_mark","logo","wordmark","calligraphic_slogan","signature","seal","brand_band","5g_mark","locked_brand_art"}
def stable_hash(obj): return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def route(item):
    explicit=str(item.get("route","")).lower()
    cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
    if cls in BRAND_CLASSES: return "imagegen_asset"
    if explicit in {"native_editable","imagegen_asset"}: return explicit
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
    cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
    if cls in BRAND_CLASSES:
        brand_instruction=("Faithfully reconstruct the complete brand visual using the supplied reference. Preserve emblem contours, "
                           "wordmark lettering and spelling, proportions, arrangement, and brand colors. Do not invent, simplify, "
                           "or omit mark elements. Produce one independently movable transparent RGBA asset when it overlays the slide.")
        base=(base+"\n"+brand_instruction).strip() if base else brand_instruction
    if base and suffix: return base+"\nAsset identity/color contract: "+suffix
    return base or suffix
def _batch_limit(profile): return {"fast":4,"strict":3,"ci":0}.get(profile,4)
def _batch_style_key(item,contract,source_sha):
    cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
    if cls not in ICON_CLASSES or cls in NEVER_BATCH_CLASSES or item.get("batch_generation") is False: return None
    if not isinstance(contract,dict) or contract.get("schema")!="ai-ppt-plus/asset-identity-contract/v1": return None
    alpha=contract.get("alpha") if isinstance(contract.get("alpha"),dict) else {}
    if alpha.get("required",item.get("alpha_required",True)) is not True: return None
    ratio=item.get("aspect_ratio")
    try: ratio=float(ratio)
    except (TypeError,ValueError): ratio=1.0
    if ratio < .5 or ratio > 2.0: return None
    style=str(item.get("batch_style_id") or item.get("style_family") or "reference-simple-icon").strip()
    return stable_hash({"source_sha256":source_sha,"style":style,"alpha":True})[:16]
def _attach_batches(jobs,items,source,profile,policy):
    limit=_batch_limit(profile)
    if limit < 2 or policy.get("independent_generation_per_asset") is True: return [],len(jobs)
    item_by_id={str((item.get("asset_id") or item.get("id") or f"asset-{index}")):item for index,item in enumerate(items,1)}
    groups={}
    for job in jobs:
        item=item_by_id.get(str(job["asset_id"]),{})
        key=_batch_style_key(item,job.get("asset_contract"),source.get("sha256"))
        if key: groups.setdefault(key,[]).append(job)
    batches=[]
    for style_key,group in sorted(groups.items()):
        for offset in range(0,len(group),limit):
            chunk=group[offset:offset+limit]
            if len(chunk)<2: continue
            batch_id="imagegen-batch-"+stable_hash({"style":style_key,"jobs":[job["cache_key"] for job in chunk]})[:12]
            cells=[]
            for cell_index,job in enumerate(chunk):
                job["generation_batch_id"]=batch_id
                job["batch_cell_index"]=cell_index
                job["batch_delivery"]="independent_alpha_slice_required"
                cells.append({"cell_index":cell_index,"asset_id":job["asset_id"],"generation_prompt":job["request"]["generation_prompt"],"output":job["output"],"qa":job["qa"]})
            batches.append({"batch_id":batch_id,"style_key":style_key,"max_assets":limit,"layout":{"columns":2,"rows":(len(chunk)+1)//2,"uniform_cells":True},"background_mode":"transparent","intermediate_output":f"assets/imagegen/batches/{batch_id}.png","deliver_intermediate":False,"slice_required":True,"independent_asset_validation_required":True,"cells":cells})
    batched={job["asset_id"] for batch in batches for job in jobs if job.get("generation_batch_id")==batch["batch_id"]}
    return batches,len(batches)+sum(1 for job in jobs if job["asset_id"] not in batched)
def plan(data):
    source=data.get("source",{}); items=data.get("assets",[]); policy=data.get("policy") if isinstance(data.get("policy"),dict) else {}; jobs=[]; native=[]; profile=str(data.get("execution_profile") or "fast").lower(); retry_limit={"fast":1,"strict":2,"ci":0}.get(profile,1)
    for i,item in enumerate(items,1):
        aid=item.get("asset_id") or item.get("id") or f"asset-{i}"; r=route(item)
        if r=="native_editable": native.append(aid); continue
        bbox=item.get("source_bbox") or item.get("placement_bbox")
        cls=str(item.get("asset_class",item.get("type",""))).lower().replace("-","_")
        ref_visible=item.get("reference_visible_bbox_norm"); contract=item.get("asset_contract")
        alpha_contract=contract.get("alpha",{}) if isinstance(contract,dict) else {}
        alpha_required=bool(alpha_contract.get("required",item.get("alpha_required",True)))
        prompt=_generation_prompt(item,contract)
        ref={"source_sha256":source.get("sha256"),"source_reference":item.get("source_ref") or source.get("path"),"asset_id":aid,"asset_class":item.get("asset_class"),"source_bbox":bbox,"aspect_ratio":item.get("aspect_ratio"),"prompt":prompt,"alpha_required":alpha_required,"asset_contract":contract}
        if ref_visible is not None: ref["reference_visible_bbox_norm"]=list(ref_visible)
        key=stable_hash(ref)
        placement_mode="adaptive-alpha-fit" if alpha_required and cls in ICON_CLASSES else ("alpha-centroid-fit" if alpha_required else "slot-bbox")
        request={"object_id":aid,"generation_prompt":prompt,"asset_contract":contract,"source_reference":ref["source_reference"],"reference_crop_bbox":bbox,"background_mode":"transparent" if alpha_required else "opaque","preserve_geometry":{"x":bbox[0],"y":bbox[1],"w":bbox[2],"h":bbox[3]} if isinstance(bbox,(list,tuple)) and len(bbox)==4 else {},"align_visible_alpha":alpha_required,"placement_mode":placement_mode,"cache_key":key,"retry_scope":"asset_only","native_tool":"image_gen.imagegen","native_tool_receipt_required":True}
        if ref_visible is not None: request["reference_visible_bbox_norm"]=list(ref_visible)
        qa={"independent_asset":True,"contact_sheet_forbidden":True,"transparent_rgba":alpha_required,"visible_alpha_bbox":True,"alpha_centroid":True,"placement_bbox":True,"local_crop_compare":True,"local_crop_bbox":_crop(bbox),"identity_contract_required":True,"semantic_identity_compare":True,"contour_identity_compare":True,"color_role_compare":True,"failure_classes":["placement_only","identity_or_color","alpha_or_clipping"]}
        if ref_visible is not None: qa["placement_geometry_compare"]=True
        jobs.append({"job_id":f"imagegen-{aid}-{key[:12]}","asset_id":aid,"route":"imagegen_asset","cache_key":key,"asset_contract":contract,"contract_complete":isinstance(contract,dict) and contract.get("schema")=="ai-ppt-plus/asset-identity-contract/v1","reference":ref,"output":f"assets/imagegen/{aid}.png","prompt_file":f"assets/prompts/{aid}.txt","request":request,"cache":{"evidence":f"assets/cache/{aid}-{key}.json","reuse_requires":["cache_key_match","asset_sha256_match","asset_identity_color_pass","alpha_geometry_pass","local_crop_qa_pass"]},"handoff":{"validator":"reconstruction.asset_orchestrator.validate_generated_asset","binder":"reconstruction.asset_orchestrator.bind_generated_asset","placement":"scripts.asset_placement.adaptive_alpha_fit" if placement_mode=="adaptive-alpha-fit" else ("scripts.asset_placement.alpha_centroid_fit" if alpha_required else "slot-bbox")},"qa":qa,"retry_scope":"asset_only","retry":{"policy":"reconstruction.asset_retry_policy.next_retry_request","max_native_attempts":1+retry_limit,"max_retries":retry_limit,"scope":"asset_only","transparent_edit_before_chroma":True,"automatic_source_reuse":False,"placement_only_consumes_generation_attempt":False,"identity_or_color_requires_regeneration":True},"state_order":["cache_lookup","native_imagegen","validate_bytes","measure_alpha_geometry","validate_identity_color","bind_alpha_centroid","render_local_crop","asset_visual_qa","cache_commit_or_asset_retry"],"source_reuse":"forbidden_without_user_approved_fallback"})
    batches,estimated_calls=_attach_batches(jobs,items,source,profile,policy)
    return {"schema":"ai-ppt-plus/imagegen-asset-jobs/v6","execution_profile":profile,"source":source,"native_tool":"image_gen.imagegen","native_tool_receipt_required":True,"native_editable_assets":native,"jobs":jobs,"job_count":len(jobs),"generation_batches":batches,"batch_count":len(batches),"estimated_uncached_imagegen_calls":estimated_calls,"cache_policy":"batch only compatible simple alpha icons; always deliver and validate independent slices; retry only failed asset ids; reuse only when cache key, delivered hash, identity/color contract, alpha geometry and local-crop QA evidence all pass","failure_policy":"brand, calligraphy, wide bands and complex art never batch; placement-only repair does not consume regeneration; identity/color or alpha failure retries only failing asset; never silently source-reuse"}
def main():
    p=argparse.ArgumentParser(); p.add_argument("input",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); r=plan(json.loads(a.input.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"job_count":r["job_count"],"output":str(a.output)}))
if __name__=="__main__": main()
