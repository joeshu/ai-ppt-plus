#!/usr/bin/env python3
"""Audit measured reference line boxes for fixed-reference editable text."""
from __future__ import annotations

import argparse,json
from pathlib import Path

def _load(p:Path)->dict:
    v=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(v,dict):raise ValueError(f"{p.name} must contain an object")
    return v

def _route_required(root:Path)->bool:
    p=root/"route-decision.json"
    if not p.is_file():return False
    try:return _load(p).get("route")=="reference-reconstruction"
    except Exception:return False

def _text(spec):
    if isinstance(spec.get("runs"),list):return "".join(str(x.get("text","")) for x in spec["runs"] if isinstance(x,dict))
    return str(spec.get("text",spec.get("content","")))

def _iter(deck):
    for slide_no,slide in enumerate(deck.get("slides") or [],1):
        if not isinstance(slide,dict):continue
        for kind in ("texts","shapes"):
            for i,spec in enumerate(slide.get(kind) or [],1):
                if not isinstance(spec,dict) or not _text(spec).strip():continue
                oid=str(spec.get("object_id") or spec.get("text_id") or spec.get("name") or f"{kind}-{i}")
                yield slide_no,kind,oid,spec

def _box4(v):
    if not isinstance(v,list) or len(v)!=4:return None
    try:x,y,w,h=map(float,v)
    except (TypeError,ValueError):return None
    return [x,y,w,h] if w>0 and h>0 else None

def audit_measured_line_boxes(layout_path:Path,deck:dict|None=None)->dict:
    layout_path=layout_path.resolve();root=layout_path.parent;deck=deck or _load(layout_path)
    strict=bool(deck.get("require_measured_line_boxes"))
    route=_route_required(root);required=route and strict
    report={"schema":"ai-ppt-plus/measured-text-line-boxes/v1","valid":True,"required":required,"strict_requested":strict,
            "checked":0,"issues":[],"slots":[]}
    for slide,kind,oid,spec in _iter(deck):
        declared=spec.get("reference_line_count")
        boxes=spec.get("reference_line_boxes",spec.get("source_line_boxes"))
        if boxes is None and declared is None:continue
        if boxes is None:
            if required:report["issues"].append({"severity":"blocker","code":"measured_line_boxes_missing","object_id":oid,"slide":slide})
            continue
        if not isinstance(boxes,list) or not boxes:
            report["issues"].append({"severity":"blocker","code":"measured_line_boxes_invalid","object_id":oid,"slide":slide});continue
        parsed=[_box4(x) for x in boxes]
        if any(x is None for x in parsed):
            report["issues"].append({"severity":"blocker","code":"measured_line_box_invalid","object_id":oid,"slide":slide});continue
        expected=int(declared) if declared is not None else len(parsed)
        valid=len(parsed)==expected
        source=_box4(spec.get("source_bbox"))
        # Source line boxes are expected in the same source-coordinate space as source_bbox.
        if source:
            sx,sy,sw,sh=source
            for idx,b in enumerate(parsed):
                x,y,w,h=b
                if x<sx-1 or y<sy-1 or x+w>sx+sw+1 or y+h>sy+sh+1:
                    valid=False;report["issues"].append({"severity":"blocker","code":"line_box_outside_source_bbox","object_id":oid,"line":idx})
        for a,b in zip(parsed,parsed[1:]):
            if b[1] < a[1]:
                valid=False;report["issues"].append({"severity":"blocker","code":"line_boxes_not_top_to_bottom","object_id":oid})
                break
        row={"slide":slide,"kind":kind,"object_id":oid,"reference_line_count":expected,"measured_line_count":len(parsed),"valid":valid}
        report["slots"].append(row);report["checked"]+=1
        if len(parsed)!=expected:report["issues"].append({"severity":"blocker","code":"measured_line_count_mismatch",**row})
    if required:
        declared_ids=[oid for _,_,oid,s in _iter(deck) if s.get("reference_line_count") is not None]
        covered={r["object_id"] for r in report["slots"]}
        for oid in declared_ids:
            if oid not in covered:report["issues"].append({"severity":"blocker","code":"measured_line_boxes_missing","object_id":oid})
    report["valid"]=not report["issues"]
    report["repair_policy"]="reconstruct_reference_line_boxes_then_fit_geometry_before_font_shrink"
    return report

def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("layout",type=Path);p.add_argument("--report",type=Path,required=True);a=p.parse_args()
    r=audit_measured_line_boxes(a.layout);a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":r["schema"],"valid":r["valid"],"required":r["required"],"checked":r["checked"],"issue_count":len(r["issues"])},ensure_ascii=False));return 0 if r["valid"] else 2
if __name__=="__main__":raise SystemExit(main())
