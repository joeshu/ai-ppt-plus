#!/usr/bin/env python3
"""Apply authoritative PageGraph geometry to strict fixed-reference authoring layouts."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

COLLECTIONS=("texts","shapes","tables","charts","images","connectors")


def _load(path:Path)->dict:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _authoring_index(deck:dict)->dict[str,dict]:
    result={}
    for slide_no,slide in enumerate(deck.get("slides") or [],1):
        if not isinstance(slide,dict):
            continue
        for collection in COLLECTIONS:
            for spec in slide.get(collection) or []:
                if not isinstance(spec,dict):
                    continue
                oid=str(spec.get("object_id") or spec.get("text_id") or spec.get("name") or "").strip()
                if oid and oid not in result:
                    result[oid]={"slide":slide_no,"collection":collection,"spec":spec}
    return result


def _convert_bbox(deck:dict,bbox:list[float])->list[float]:
    x,y,w,h=map(float,bbox[:4])
    if deck.get("units","fraction")=="px":
        rw=float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 0)
        rh=float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 0)
        if rw<=0 or rh<=0:
            raise ValueError("px layout requires positive reference dimensions")
        return [x*rw,y*rh,w*rw,h*rh]
    return [x,y,w,h]


def _write_bbox(spec:dict,box:list[float])->None:
    x,y,w,h=box
    if isinstance(spec.get("bbox"),list):
        spec["bbox"]=[x,y,w,h]
    for key,value in (("x",x),("y",y),("w",w),("h",h),("left",x),("top",y),("width",w),("height",h)):
        if key in spec or key in {"x","y","w","h"}:
            spec[key]=value


def apply_page_graph_geometry(deck:dict,page_graph:dict,*,min_confidence:float=0.5)->tuple[dict,dict]:
    result=copy.deepcopy(deck)
    index=_authoring_index(result)
    applied=[];skipped=[];missing=[]
    for node in page_graph.get("nodes") or []:
        if not isinstance(node,dict):
            continue
        oid=str(node.get("id","")).strip();bbox=node.get("bbox")
        if not oid or not isinstance(bbox,list) or len(bbox)!=4:
            continue
        try:
            confidence=float(node.get("confidence",1.0) or 0);values=list(map(float,bbox))
        except (TypeError,ValueError):
            skipped.append({"object_id":oid,"reason":"invalid_geometry_or_confidence"});continue
        if confidence<min_confidence:
            skipped.append({"object_id":oid,"reason":"low_confidence","confidence":confidence});continue
        target=index.get(oid)
        if not target:
            missing.append({"object_id":oid,"node_type":node.get("type"),"confidence":confidence});continue
        box=_convert_bbox(result,values);before=[target["spec"].get(k) for k in ("x","y","w","h")]
        _write_bbox(target["spec"],box)
        target["spec"]["page_graph_geometry_locked"]=True;target["spec"]["page_graph_confidence"]=confidence
        applied.append({"object_id":oid,"slide":target["slide"],"collection":target["collection"],"before":before,"after":box,"confidence":confidence})
    return result,{"schema":"ai-ppt-plus/page-geometry-calibration/v2","valid":True,"min_confidence":min_confidence,"applied_count":len(applied),"missing_count":len(missing),"skipped_count":len(skipped),"applied":applied,"missing":missing,"skipped":skipped,"policy":"pagegraph_bbox_is_authoritative_before_text_fit"}


def calibrate_reference_deck(deck:dict,layout_path:Path)->tuple[dict,dict|None]:
    """Calibrate only fixed-reference routes; keep compose_pptx orchestration-only."""
    parent=layout_path.resolve().parent;route_path=parent/"route-decision.json"
    if not route_path.is_file():
        return deck,None
    route=_load(route_path)
    if route.get("route")!="reference-reconstruction":
        return deck,None
    page_graph_path=parent/"page-graph.json"
    if not page_graph_path.is_file():
        raise ValueError(f"reference reconstruction requires PageGraph geometry: {page_graph_path}")
    return apply_page_graph_geometry(deck,_load(page_graph_path))


def write_calibration_report(output_path:Path,report:dict|None)->None:
    if report is None:
        return
    path=output_path.with_name(f"{output_path.stem}.page-geometry-calibration.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def calibrate_layout(layout_path:Path,page_graph_path:Path,output_path:Path,report_path:Path|None=None,min_confidence:float=0.5)->dict:
    deck=_load(layout_path);graph=_load(page_graph_path)
    calibrated,report=apply_page_graph_geometry(deck,graph,min_confidence=min_confidence)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(calibrated,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if report_path:
        report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("layout",type=Path);p.add_argument("page_graph",type=Path)
    p.add_argument("--output",type=Path,required=True);p.add_argument("--report",type=Path,required=True);p.add_argument("--min-confidence",type=float,default=0.5)
    a=p.parse_args();r=calibrate_layout(a.layout.resolve(),a.page_graph.resolve(),a.output.resolve(),a.report.resolve(),a.min_confidence)
    print(json.dumps({"schema":r["schema"],"valid":r["valid"],"applied_count":r["applied_count"],"missing_count":r["missing_count"]},ensure_ascii=False));return 0


if __name__=="__main__":
    raise SystemExit(main())
