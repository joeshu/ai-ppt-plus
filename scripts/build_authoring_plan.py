#!/usr/bin/env python3
"""Compile Visual Inventory into an executable pre-authoring contract.

The plan prevents first-pass drift by deciding ownership, implementation, geometry,
text/asset contracts, anchors and z-role before Artifact Tool authoring starts.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

TEXT_ROLES={"title","subtitle","kicker","tag","body","label","caption","legend","chart-label","table-cell","number-unit"}
IMAGEGEN_ROLES={"icon","pictogram","brand-lockup","complex-badge","illustration","decorative-art","footer-art","header-art","ribbon-stream"}
VALID_IMPL={"native_text","native_shape","native_chart","native_table","native_connector","native_freeform","imagegen_asset","semantic_group"}
VALID_Z={"background","container","asset","geometry","text","foreground"}

def _bbox(obj):
    b=obj.get("bbox") or obj.get("source_bbox") or obj.get("placement_bbox")
    if isinstance(b,(list,tuple)) and len(b)==4:
        return [float(v) for v in b]
    if all(k in obj for k in ("x","y","w","h")):
        return [float(obj[k]) for k in ("x","y","w","h")]
    return None

def _implementation(obj):
    explicit=obj.get("implementation_type")
    if explicit in VALID_IMPL: return explicit
    route=str(obj.get("route","")).lower()
    role=str(obj.get("semantic_role",obj.get("type",""))).lower().replace("_","-")
    if role in TEXT_ROLES or obj.get("text") is not None: return "native_text"
    if route=="imagegen_asset" or role in IMAGEGEN_ROLES: return "imagegen_asset"
    if role in {"chart","native-chart"}: return "native_chart"
    if role in {"table","semantic-table"}: return "native_table"
    if role in {"connector","line"}: return "native_connector"
    if role in {"group","semantic-region","title-block","footer-band","header-band"}: return "semantic_group"
    return "native_shape"

def _text_contract(obj):
    return {
        "producer": obj.get("text_producer","text_box"),
        "slot_bbox": _bbox(obj),
        "target_lines": obj.get("target_lines"),
        "line_breaks": obj.get("line_breaks"),
        "first_baseline": obj.get("first_baseline"),
        "baseline_delta": obj.get("baseline_delta",obj.get("target_line_height")),
        "inner_margins": obj.get("inner_margins"),
        "font_face": obj.get("font_face"),
        "font_size": obj.get("font_size"),
        "font_weight": obj.get("font_weight"),
        "runs": obj.get("runs"),
        "fit_evidence_required": True,
    }

def _asset_contract(obj):
    identity=obj.get("identity_contract") or {}
    color=obj.get("color_contract") or {}
    return {
        "identity": {"semantic_identity":identity.get("semantic_identity",obj.get("semantic_identity")),"contour_traits":identity.get("contour_traits",obj.get("contour_traits")),"forbidden_substitutions":identity.get("forbidden_substitutions",[])},
        "color": {"foreground":color.get("foreground"),"internal_detail":color.get("internal_detail"),"host_background":color.get("host_background"),"evidence_status":color.get("evidence_status","specified" if color else "unavailable")},
        "alpha_required": bool(obj.get("alpha_required",True)),
        "safe_padding": obj.get("safe_padding"),
        "reference_visible_bbox_norm": obj.get("reference_visible_bbox_norm"),
        "visual_centroid": obj.get("visual_centroid"),
    }

def build_plan(data):
    issues=[]; out=[]; seen=set()
    for idx,obj in enumerate(data.get("objects",[]),1):
        oid=str(obj.get("object_id") or obj.get("id") or f"object-{idx}")
        if oid in seen: issues.append({"code":"duplicate_object_id","object_id":oid}); continue
        seen.add(oid); impl=_implementation(obj); bbox=_bbox(obj)
        if bbox is None: issues.append({"code":"missing_bbox","object_id":oid})
        parent=obj.get("parent_id") or obj.get("parent")
        z=obj.get("z_role") or ("text" if impl=="native_text" else "asset" if impl=="imagegen_asset" else "geometry")
        if z not in VALID_Z: issues.append({"code":"invalid_z_role","object_id":oid,"observed":z})
        entry={"object_id":oid,"semantic_role":obj.get("semantic_role",obj.get("type")),"implementation_type":impl,"parent_id":parent,"bbox":bbox,"anchors":obj.get("anchors",obj.get("anchor")),"relationships":obj.get("relationships",{}),"z_role":z,"protected_neighbors":list(obj.get("protected_neighbors") or [])}
        if impl=="native_text": entry["text_contract"]=_text_contract(obj)
        if impl=="imagegen_asset": entry["asset_contract"]=_asset_contract(obj)
        out.append(entry)
    ids={o["object_id"] for o in out}
    for o in out:
        if o.get("parent_id") and o["parent_id"] not in ids: issues.append({"code":"unknown_parent","object_id":o["object_id"],"parent_id":o["parent_id"]})
        for n in o.get("protected_neighbors",[]):
            if n not in ids: issues.append({"code":"unknown_protected_neighbor","object_id":o["object_id"],"neighbor":n})
    return {"schema":"ai-ppt-plus/authoring-plan/v1","source":data.get("source",{}),"valid":not issues,"issues":issues,"objects":out,"object_count":len(out),"policy":{"authoring_order":["parent/container geometry","assets and native geometry","native text"],"repair_owner_first":True,"visual_threshold_blocker":False}}

def main():
    p=argparse.ArgumentParser(); p.add_argument("inventory",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    result=build_plan(json.loads(a.inventory.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"valid":result["valid"],"objects":result["object_count"],"output":str(a.output)})); return 0 if result["valid"] else 2
if __name__=="__main__": raise SystemExit(main())
