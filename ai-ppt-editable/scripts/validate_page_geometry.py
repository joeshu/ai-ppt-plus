#!/usr/bin/env python3
"""Fail-closed PageGraph -> authoring geometry calibration for fixed references."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

AUTHOR_TYPES={"text","shape","table","chart","icon","illustration","image","connector","decoration"}

def _load(path:Path)->dict:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"{path.name} must contain an object")
    return value

def _route_required(root:Path)->bool:
    p=root/"route-decision.json"
    if not p.is_file(): return False
    try:return _load(p).get("route")=="reference-reconstruction"
    except Exception:return False

def _bbox(spec:dict,deck:dict):
    raw=spec.get("bbox")
    if isinstance(raw,list) and len(raw)>=4:
        try:x,y,w,h=map(float,raw[:4])
        except (TypeError,ValueError):return None
    else:
        try:
            x=float(spec.get("x",spec.get("left")));y=float(spec.get("y",spec.get("top")))
            w=float(spec.get("w",spec.get("width")));h=float(spec.get("h",spec.get("height")))
        except (TypeError,ValueError):return None
    if deck.get("units","fraction")=="px":
        rw=float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 0)
        rh=float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 0)
        if rw<=0 or rh<=0:return None
        x,y,w,h=x/rw,y/rh,w/rw,h/rh
    if w<=0 or h<=0:return None
    return [x,y,w,h]

def _iou(a,b):
    ax1,ay1,aw,ah=a;bx1,by1,bw,bh=b
    ax2,ay2=ax1+aw,ay1+ah;bx2,by2=bx1+bw,by1+bh
    iw=max(0,min(ax2,bx2)-max(ax1,bx1));ih=max(0,min(ay2,by2)-max(ay1,by1))
    inter=iw*ih;union=aw*ah+bw*bh-inter
    return inter/union if union>0 else 0.0

def _layout_objects(deck):
    out={}
    for slide_no,slide in enumerate(deck.get("slides") or [],1):
        if not isinstance(slide,dict):continue
        for kind in ("texts","shapes","tables","charts","images","connectors"):
            for index,spec in enumerate(slide.get(kind) or [],1):
                if not isinstance(spec,dict):continue
                oid=str(spec.get("object_id") or spec.get("text_id") or spec.get("name") or "").strip()
                if not oid:continue
                out[oid]={"slide":slide_no,"kind":kind,"bbox":_bbox(spec,deck)}
    return out

def audit_page_geometry(layout_path:Path,deck:dict|None=None)->dict:
    layout_path=layout_path.resolve();root=layout_path.parent
    deck=deck or _load(layout_path)
    required=_route_required(root)
    graph_path=root/"page-graph.json"
    report={"schema":"ai-ppt-plus/page-geometry-calibration/v1","valid":True,"required":required,
            "page_graph":str(graph_path),"checked":0,"issues":[],"objects":[]}
    if not graph_path.is_file():
        if required:
            report["valid"]=False;report["issues"].append({"severity":"blocker","code":"page_graph_missing"})
        return report
    graph=_load(graph_path); authored=_layout_objects(deck)
    meta=graph.get("metadata") if isinstance(graph.get("metadata"),dict) else {}
    tol=meta.get("geometry_tolerance") if isinstance(meta.get("geometry_tolerance"),dict) else {}
    min_iou=float(tol.get("min_iou",0.80));max_center=float(tol.get("max_center_error",0.02));max_size=float(tol.get("max_size_error",0.04))
    for node in graph.get("nodes") or []:
        if not isinstance(node,dict) or str(node.get("type","")).lower() not in AUTHOR_TYPES:continue
        oid=str(node.get("id","")).strip();ref=node.get("bbox")
        if not oid or not isinstance(ref,list) or len(ref)!=4:continue
        try:ref=list(map(float,ref))
        except (TypeError,ValueError):continue
        confidence=float(node.get("confidence",1.0) or 0)
        if confidence<0.5:continue
        actual=authored.get(oid)
        if not actual or actual.get("bbox") is None:
            report["issues"].append({"severity":"blocker","code":"page_graph_object_missing","object_id":oid,"node_type":node.get("type")});continue
        box=actual["bbox"];iou=_iou(ref,box)
        rcx,rcy=ref[0]+ref[2]/2,ref[1]+ref[3]/2;acx,acy=box[0]+box[2]/2,box[1]+box[3]/2
        center=math.hypot(acx-rcx,acy-rcy);size=max(abs(box[2]-ref[2]),abs(box[3]-ref[3]))
        valid=iou>=min_iou and center<=max_center and size<=max_size
        row={"object_id":oid,"slide":actual["slide"],"kind":actual["kind"],"reference_bbox":ref,"authored_bbox":box,
             "bbox_iou":round(iou,6),"center_error":round(center,6),"size_error":round(size,6),"valid":valid}
        report["objects"].append(row);report["checked"]+=1
        if not valid:report["issues"].append({"severity":"blocker","code":"page_graph_geometry_drift",**row,
            "thresholds":{"min_iou":min_iou,"max_center_error":max_center,"max_size_error":max_size}})
    report["valid"]=not report["issues"]
    report["thresholds"]={"min_iou":min_iou,"max_center_error":max_center,"max_size_error":max_size}
    report["repair_policy"]="repair_pagegraph_geometry_before_typography_or_asset_tuning"
    return report

def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("layout",type=Path);p.add_argument("--report",type=Path,required=True);a=p.parse_args()
    r=audit_page_geometry(a.layout);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":r["schema"],"valid":r["valid"],"checked":r["checked"],"issue_count":len(r["issues"])},ensure_ascii=False));return 0 if r["valid"] else 2
if __name__=="__main__":raise SystemExit(main())
