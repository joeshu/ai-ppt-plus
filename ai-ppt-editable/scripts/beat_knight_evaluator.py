#!/usr/bin/env python3
"""Compare Knight and candidate evidence across the five mandatory dimensions."""
from __future__ import annotations
import argparse, json
from pathlib import Path

DIMENSIONS=("pixel","text","object","icon_asset","local_crop")

def _num(value, default=0.0):
    try: return float(value)
    except (TypeError,ValueError): return default

def _score_dimension(name, evidence):
    # Inputs are normalized so larger is always better and bounded to [0,1].
    if name=="pixel":
        return min(_num(evidence.get("layout_ssim")),_num(evidence.get("pixel_fidelity")))
    if name=="text":
        coverage=_num(evidence.get("coverage",evidence.get("accuracy",0)))
        overflow=_num(evidence.get("overflow_count",0)); missing=_num(evidence.get("missing_count",0)); extra=_num(evidence.get("extra_count",0))
        return max(0.0,min(1.0,coverage-0.05*(overflow+missing+extra)))
    if name=="object":
        coverage=_num(evidence.get("coverage",1.0)); drift=_num(evidence.get("unauthorized_drift_count",0)); blocking=_num(evidence.get("blocking_count",0))
        return max(0.0,min(1.0,coverage-0.05*drift-0.10*blocking))
    if name=="icon_asset":
        iou=_num(evidence.get("mean_visible_bbox_iou",evidence.get("mean_iou",0)))
        centroid=_num(evidence.get("mean_centroid_error_norm",0)); scale=_num(evidence.get("mean_scale_error",0)); failures=_num(evidence.get("failure_count",0))
        return max(0.0,min(1.0,iou-0.20*centroid-0.10*scale-0.05*failures))
    if name=="local_crop":
        return min(_num(evidence.get("worst_layout_ssim")),_num(evidence.get("worst_pixel_fidelity")))
    raise KeyError(name)

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--knight",type=Path,required=True); p.add_argument("--candidate",type=Path,required=True); p.add_argument("--report",type=Path,required=True); p.add_argument("--tolerance",type=float,default=0.002)
    a=p.parse_args(); knight=json.loads(a.knight.read_text(encoding="utf-8")); candidate=json.loads(a.candidate.read_text(encoding="utf-8"))
    rows={}; strict_wins=0; losses=[]
    for name in DIMENSIONS:
        ks=_score_dimension(name,knight.get(name,{ })); cs=_score_dimension(name,candidate.get(name,{ })); delta=cs-ks
        if delta>a.tolerance: verdict="win"; strict_wins+=1
        elif delta<-a.tolerance: verdict="loss"; losses.append(name)
        else: verdict="tie"
        rows[name]={"knight":ks,"candidate":cs,"delta":delta,"verdict":verdict}
    visual_gate=_num(candidate.get("pixel",{}).get("layout_ssim"))>=0.90 and _num(candidate.get("pixel",{}).get("pixel_fidelity"))>=0.90
    editability=bool(candidate.get("editability",{}).get("formal_text_native",False)) and int(candidate.get("editability",{}).get("whole_slide_picture_count",1))==0
    blocking=int(candidate.get("blocking_count",0))==0
    key_win=rows["pixel"]["verdict"]=="win" or rows["local_crop"]["verdict"]=="win"
    beat=visual_gate and editability and blocking and not losses and strict_wins>=3 and key_win
    report={"schema":"ai-ppt-plus/beat-knight-report/v1","beat_knight":beat,"tolerance":a.tolerance,"strict_win_count":strict_wins,"loss_dimensions":losses,"visual_gate_pass":visual_gate,"editability_pass":editability,"blocking_pass":blocking,"pixel_or_local_crop_win":key_win,"dimensions":rows,"decision":"candidate_win" if beat else "not_proven"}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(report,ensure_ascii=False)); return 0 if beat else 3
if __name__=="__main__": raise SystemExit(main())
