#!/usr/bin/env python3
"""Enforce native ImageGen as the final route for non-native visual assets."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

# Deterministic two-route contract: formal text/data + simple PPT primitives stay
# native; all visual classes, including brand visuals, require native ImageGen
# for the final asset. Supplied brand files remain references, not bypasses.
REQUIRED = {
    "icon","icons","badge","gradient","gradient_visual","complex_art",
    "illustration","artistic_typography","decorative_art","logo","brand",
    "brand_lockup","wordmark","calligraphic_slogan","signature","seal",
    "brand_band","skyline","ribbon","5g_mark","locked_brand_art"
}
BRAND_CLASSES = {
    "logo", "brand", "brand_logo", "brand_lockup", "wordmark", "calligraphic_slogan",
    "signature", "seal", "brand_band", "5g_mark", "locked_brand_art",
}
IMAGEGEN_WORD=re.compile(r"(^|[-_.:/ ])imagegen($|[-_.:/ ])",re.I)
NATIVE_IMAGEGEN_TOOL="image_gen.imagegen"
SHEET_WORD=re.compile(r"(^|[-_. /])(contact[-_ ]?sheet|sprite[-_ ]?sheet|icon[-_ ]?sheet|sheet)([-_. /]|$)",re.I)
SHA256_RE=re.compile(r"^[0-9a-f]{64}$")

def _class(item):
    return str(item.get("asset_class",item.get("category",item.get("role","")))).strip().lower().replace("-","_")
def _sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()
def _resolve(manifest,value):
    if not isinstance(value,str) or not value.strip(): return None
    p=Path(value); return (p if p.is_absolute() else manifest.parent/p).resolve()
def _validated_sheet_derivative(item):
    """Allow only explicitly documented, independent slices of a generated sheet."""
    transform = item.get("derived_transform")
    bbox = transform.get("bbox_px") if isinstance(transform, dict) else None
    return (
        item.get("derived_from_sheet") is True
        and item.get("independent_asset") is True
        and isinstance(transform, dict)
        and bool(transform.get("mode"))
        and isinstance(bbox, (list, tuple))
        and len(bbox) == 4
        and all(isinstance(value, (int, float)) and value >= 0 for value in bbox)
    )

def _sheet_ancestry(item):
    if item.get("sprite_sheet") is True or item.get("contact_sheet") is True: return True
    allow_source_sheet = _validated_sheet_derivative(item)
    for field in ("generated_source","copied_to","source_ref","parent_asset","generation_parent"):
        value=item.get(field)
        if isinstance(value,str) and SHEET_WORD.search(value.replace("\\","/")):
            # Source/generation-parent sheet references are valid only for an
            # explicitly recorded independent slice; copied_to remains strict.
            if allow_source_sheet and field in {"generated_source", "source_ref", "parent_asset", "generation_parent"}:
                continue
            return True
    return False

def _native_receipt_issues(manifest: Path, item: dict, asset_id: str, receipt_required: bool) -> list[dict]:
    if not receipt_required:
        return []
    receipt = item.get("native_imagegen_receipt")
    if not isinstance(receipt, dict):
        return [{"code":"native_imagegen_receipt_missing","asset_id":asset_id}]
    issues=[]
    if receipt.get("tool") != NATIVE_IMAGEGEN_TOOL:
        issues.append({"code":"native_imagegen_receipt_tool_invalid","asset_id":asset_id,"observed":receipt.get("tool")})
    if receipt.get("mode") not in {"new","edit"}:
        issues.append({"code":"native_imagegen_receipt_mode_invalid","asset_id":asset_id,"observed":receipt.get("mode")})
    if not isinstance(receipt.get("source_reference"), str) or not receipt["source_reference"].strip():
        issues.append({"code":"native_imagegen_receipt_source_missing","asset_id":asset_id})
    prompt_path=_resolve(manifest, item.get("prompt_file"))
    prompt_hash=receipt.get("prompt_sha256")
    if not isinstance(prompt_hash,str) or not SHA256_RE.fullmatch(prompt_hash):
        issues.append({"code":"native_imagegen_receipt_prompt_hash_invalid","asset_id":asset_id,"observed":prompt_hash})
    elif prompt_path is not None and prompt_path.is_file() and _sha256(prompt_path) != prompt_hash:
        issues.append({"code":"native_imagegen_receipt_prompt_hash_mismatch","asset_id":asset_id})
    output_path=_resolve(manifest, receipt.get("output_path"))
    generated_path=_resolve(manifest, item.get("generated_source"))
    if output_path is None or generated_path is None or output_path != generated_path:
        issues.append({"code":"native_imagegen_receipt_output_mismatch","asset_id":asset_id,"output_path":str(output_path) if output_path else None,"generated_source":str(generated_path) if generated_path else None})
    if not isinstance(receipt.get("generation_request_id"),str) or not receipt["generation_request_id"].strip():
        issues.append({"code":"native_imagegen_receipt_request_id_missing","asset_id":asset_id})
    if not isinstance(receipt.get("recorded_at"),str) or not receipt["recorded_at"].strip():
        issues.append({"code":"native_imagegen_receipt_timestamp_missing","asset_id":asset_id})
    return issues

def validate(path:Path,*,strict=False):
    data=json.loads(path.read_text(encoding="utf-8")); errors=[]
    if strict and data.get("provenance_policy")!="imagegen_final_assets": errors.append({"code":"wrong_provenance_policy","observed":data.get("provenance_policy")})
    receipt_required=bool(data.get("native_tool_receipt_required"))
    if strict and receipt_required and data.get("native_tool")!=NATIVE_IMAGEGEN_TOOL:
        errors.append({"code":"native_imagegen_tool_declaration_invalid","observed":data.get("native_tool")})
    assets=data.get("assets");
    if not isinstance(assets,list): errors.append({"code":"assets_not_list"}); assets=[]
    records=[]
    for index,item in enumerate(assets,1):
        if not isinstance(item,dict): errors.append({"code":"asset_not_object","index":index}); continue
        asset_id=item.get("asset_id") or item.get("id") or f"asset-{index}"; cls=_class(item); route=str(item.get("provenance_mode","")).lower()
        if cls not in REQUIRED:
            records.append({"asset_id":asset_id,"asset_class":cls,"route":route or "unspecified"}); continue
        required=("generated_source","copied_to","prompt_file","backend"); missing=[k for k in required if not item.get(k)]
        fallback=route=="source_reuse" and item.get("fallback_decision")=="user_approved" and item.get("decision_id") and item.get("decision_reason") and item.get("decision_timestamp")
        if cls in BRAND_CLASSES and route != "imagegen": errors.append({"code":"brand_asset_requires_native_imagegen","asset_id":asset_id,"asset_class":cls,"observed":route})
        if route!="imagegen" and not fallback: errors.append({"code":"final_asset_not_imagegen","asset_id":asset_id,"asset_class":cls,"observed":route})
        if missing and not fallback: errors.append({"code":"imagegen_evidence_missing","asset_id":asset_id,"missing":missing})
        if (item.get("source_reuse") is True or item.get("extraction_method") in {"source_reuse","exact_crop","crop"}) and not fallback: errors.append({"code":"source_reuse_final_asset_forbidden","asset_id":asset_id})
        if fallback and not (item.get("source_ref") and item.get("source_bbox") and item.get("source_sha256")): errors.append({"code":"approved_fallback_missing_source_evidence","asset_id":asset_id})
        if _sheet_ancestry(item): errors.append({"code":"sheet_not_independent_asset","asset_id":asset_id})
        # Deterministic geometry evidence is mandatory for final generated visuals.
        if route=="imagegen":
            for key in ("visible_alpha_bbox","alpha_centroid","placement_bbox"):
                if key not in item: errors.append({"code":"alpha_geometry_evidence_missing","asset_id":asset_id,"field":key})
            if item.get("independent_asset") is not True: errors.append({"code":"asset_not_independent","asset_id":asset_id})
            backend=str(item.get("backend",""))
            if strict and not IMAGEGEN_WORD.search(backend): errors.append({"code":"non_native_imagegen_backend","asset_id":asset_id,"backend":backend})
            if strict and receipt_required:
                errors.extend(_native_receipt_issues(path, item, asset_id, True))
            for field in ("generated_source","copied_to","prompt_file"):
                p=_resolve(path,item.get(field))
                if strict and (p is None or not p.is_file()): errors.append({"code":"imagegen_evidence_file_missing","asset_id":asset_id,"field":field,"path":str(p) if p else None})
            copied=_resolve(path,item.get("copied_to")); declared=item.get("sha256") or item.get("asset_sha256") or item.get("copied_to_sha256")
            if strict and (not isinstance(declared,str) or not SHA256_RE.fullmatch(declared)): errors.append({"code":"delivered_hash_missing_or_invalid","asset_id":asset_id,"declared":declared})
            elif copied and copied.is_file() and declared and _sha256(copied)!=declared: errors.append({"code":"delivered_hash_mismatch","asset_id":asset_id})
        if fallback:
            source=_resolve(path,item.get("source_ref")); declared=item.get("source_sha256")
            if strict and (source is None or not source.is_file()): errors.append({"code":"approved_fallback_source_missing","asset_id":asset_id,"path":str(source) if source else None})
            if strict and (not isinstance(declared,str) or not SHA256_RE.fullmatch(declared)): errors.append({"code":"approved_fallback_source_hash_invalid","asset_id":asset_id,"declared":declared})
            elif source and source.is_file() and declared and _sha256(source)!=declared: errors.append({"code":"approved_fallback_source_hash_mismatch","asset_id":asset_id})
        records.append({"asset_id":asset_id,"asset_class":cls,"route":route,"generated_source":item.get("generated_source"),"copied_to":item.get("copied_to")})
    return {"schema":"ai-ppt-plus/imagegen-final-assets/v4" if receipt_required else "ai-ppt-plus/imagegen-final-assets/v3","valid":not errors,"strict":strict,"native_tool_receipt_required":receipt_required,"required_classes":sorted(REQUIRED),"asset_count":len(assets),"records":records,"errors":errors,"human_visual_review_required":True}

def main():
    p=argparse.ArgumentParser(); p.add_argument("manifest",type=Path); p.add_argument("--strict",action="store_true"); p.add_argument("--report",type=Path); a=p.parse_args()
    r=validate(a.manifest.resolve(),strict=a.strict)
    if a.report: a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(r,ensure_ascii=False)); return 0 if r["valid"] else 1
if __name__=="__main__": raise SystemExit(main())
