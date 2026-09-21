#!/usr/bin/env python3
"""Development-only comparison of Knight and candidate evidence."""
from __future__ import annotations
import argparse, json
from pathlib import Path

DIMENSIONS=("pixel","text","object","icon_asset","local_crop")
PROFILES=("standard","dense_editable","gradient","complex_illustration","competitive_ab")

def _num(value, default=0.0):
    try: return float(value)
    except (TypeError,ValueError): return default

def _score_dimension(name,evidence):
    if name=="pixel": return min(_num(evidence.get("layout_ssim")),_num(evidence.get("pixel_fidelity")))
    if name=="text":
        coverage=_num(evidence.get("coverage",evidence.get("accuracy",0))); defects=sum(_num(evidence.get(k,0)) for k in ("overflow_count","missing_count","extra_count"))
        return max(0.0,min(1.0,coverage-0.05*defects))
    if name=="object":
        return max(0.0,min(1.0,_num(evidence.get("coverage",1.0))-0.05*_num(evidence.get("unauthorized_drift_count",0))-0.10*_num(evidence.get("blocking_count",0))))
    if name=="icon_asset":
        return max(0.0,min(1.0,_num(evidence.get("mean_visible_bbox_iou",evidence.get("mean_iou",0)))-0.20*_num(evidence.get("mean_centroid_error_norm",0))-0.10*_num(evidence.get("mean_scale_error",0))-0.05*_num(evidence.get("failure_count",0))))
    if name=="local_crop": return min(_num(evidence.get("worst_layout_ssim")),_num(evidence.get("worst_pixel_fidelity")))
    raise KeyError(name)

def _absolute_floor(c,*,require_imagegen=False):
    e=c.get("editability",{}); t=c.get("text",{}); o=c.get("object",{}); i=c.get("icon_asset",{}); provenance=c.get("asset_provenance",{})
    checks={
      "formal_text_native":bool(e.get("formal_text_native",False)),
      "no_whole_slide_picture":int(e.get("whole_slide_picture_count",1))==0,
      "no_blocking_defect":int(c.get("blocking_count",0))==0,
      "no_missing_text":int(t.get("missing_count",0))==0,
      "no_text_overflow":int(t.get("overflow_count",0))==0,
      "no_blocking_object":int(o.get("blocking_count",0))==0,
      "icon_assets_independent":bool(i.get("independent_assets",True)),
      "alpha_assets_valid":int(i.get("alpha_failure_count",0))==0,
    }
    if require_imagegen:
        checks.update({
          "imagegen_final_assets":bool(provenance.get("imagegen_final_assets",False)),
          "alpha_centroid_evidence":bool(provenance.get("alpha_centroid_evidence",False)),
          "no_contact_sheet_ancestry":int(provenance.get("contact_sheet_ancestry_count",1))==0,
        })
    return all(checks.values()),checks

def _visual_gate(profile,c,rows):
    p=c.get("pixel",{}); regional=c.get("regional",{}); composite=c.get("visual_composite",{})
    if profile=="standard":
        passed=_num(p.get("layout_ssim"))>=0.90 and _num(p.get("pixel_fidelity"))>=0.90
        return passed,{"mode":"absolute_standard","layout_ssim_floor":0.90,"pixel_fidelity_floor":0.90}
    if profile=="dense_editable":
        components={
          "geometry":_num(composite.get("geometry",regional.get("geometry",rows["object"]["candidate"]))),
          "typography":_num(composite.get("typography",rows["text"]["candidate"])),
          "asset":_num(composite.get("asset",rows["icon_asset"]["candidate"])),
          "regional":_num(composite.get("regional",regional.get("mean_layout_ssim",rows["local_crop"]["candidate"]))),
          "color":_num(composite.get("color",p.get("pixel_fidelity"))),
        }
        weights={"geometry":0.25,"typography":0.25,"asset":0.20,"regional":0.20,"color":0.10}
        score=sum(components[k]*weights[k] for k in weights)
        return score>=0.75 and components["typography"]>=0.90 and components["geometry"]>=0.80,{"mode":"dense_editable_composite","score":score,"floor":0.75,"components":components,"weights":weights}
    if profile in ("gradient","complex_illustration"):
        regional_score=_num(regional.get("mean_layout_ssim",rows["local_crop"]["candidate"])); asset=rows["icon_asset"]["candidate"]
        return regional_score>=0.75 and asset>=0.75,{"mode":profile+"_regional","regional":regional_score,"asset":asset,"floor":0.75}
    return True,{"mode":"competitive_relative","whole_slide_ssim_diagnostic":_num(p.get("layout_ssim"))}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--knight",type=Path,required=True); p.add_argument("--candidate",type=Path,required=True); p.add_argument("--report",type=Path,required=True); p.add_argument("--tolerance",type=float,default=0.002); p.add_argument("--profile",choices=PROFILES,default="standard")
    a=p.parse_args(); knight=json.loads(a.knight.read_text(encoding="utf-8")); candidate=json.loads(a.candidate.read_text(encoding="utf-8")); rows={}; strict_wins=0; losses=[]
    for name in DIMENSIONS:
        ks=_score_dimension(name,knight.get(name,{})); cs=_score_dimension(name,candidate.get(name,{})); delta=cs-ks
        if delta>a.tolerance: verdict="win"; strict_wins+=1
        elif delta<-a.tolerance: verdict="loss"; losses.append(name)
        else: verdict="tie"
        rows[name]={"knight":ks,"candidate":cs,"delta":delta,"verdict":verdict}
    require_imagegen=a.profile=="competitive_ab"
    floor_pass,floor_checks=_absolute_floor(candidate,require_imagegen=require_imagegen); visual_gate,visual_evidence=_visual_gate(a.profile,candidate,rows); key_win=rows["pixel"]["verdict"]=="win" or rows["local_crop"]["verdict"]=="win"
    relative_pass=not losses and strict_wins>=3 and key_win
    beat=floor_pass and visual_gate and relative_pass
    report={"schema":"ai-ppt-plus/beat-knight-report/v2","profile":a.profile,"beat_knight":beat,"tolerance":a.tolerance,"strict_win_count":strict_wins,"loss_dimensions":losses,"relative_pass":relative_pass,"visual_gate_pass":visual_gate,"visual_gate":visual_evidence,"absolute_quality_floor_pass":floor_pass,"absolute_quality_floor":floor_checks,"imagegen_provenance_required":require_imagegen,"pixel_or_local_crop_win":key_win,"dimensions":rows,"decision":"candidate_win" if beat else "not_proven"}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(report,ensure_ascii=False)); return 0 if beat else 3
if __name__=="__main__": raise SystemExit(main())
