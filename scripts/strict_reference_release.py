#!/usr/bin/env python3
"""Fresh reference reconstruction render/review entrypoint.

Hard authoring/provenance failures remain fail-closed. Fresh render comparison,
local crops and Repair Trace always run. Visual metrics are diagnostic evidence;
normal execution has no universal numeric visual threshold.
"""
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
SCRIPT_DIR=Path(__file__).resolve().parent

def run(command:list[str],label:str)->None:
    completed=subprocess.run(command,text=True,capture_output=True,check=False)
    if completed.stdout: print(completed.stdout,end="")
    if completed.returncode!=0:
        if completed.stderr: print(completed.stderr,file=sys.stderr)
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")

def load(path:Path)->dict:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"{path} must contain an object")
    return value

def bbox(spec:dict,deck:dict)->list[float]|None:
    raw=spec.get("bbox")
    if isinstance(raw,list) and len(raw)>=4: x,y,w,h=map(float,raw[:4])
    else:
        try:
            x=float(spec.get("x",spec.get("left")));y=float(spec.get("y",spec.get("top")))
            w=float(spec.get("w",spec.get("width")));h=float(spec.get("h",spec.get("height")))
        except (TypeError,ValueError): return None
    if deck.get("units","fraction")=="px":
        rw=float(deck.get("ref_width") or deck.get("reference_width") or deck.get("slide_width_px") or 1)
        rh=float(deck.get("ref_height") or deck.get("reference_height") or deck.get("slide_height_px") or 1)
        x,y,w,h=x/rw,y/rh,w/rw,h/rh
    if w<=0 or h<=0 or x<0 or y<0 or x+w>1.001 or y+h>1.001:return None
    return [round(x,7),round(y,7),round(w,7),round(h,7)]

def region_manifest(layout:Path,output:Path)->dict:
    deck=load(layout);regions=[]
    for slide_no,slide in enumerate(deck.get("slides") or [],1):
        for kind in ("texts","shapes","tables","charts","images"):
            for index,spec in enumerate(slide.get(kind) or [],1):
                if not isinstance(spec,dict):continue
                box=bbox(spec,deck)
                if box is None or box[2]*box[3]<0.0005:continue
                oid=str(spec.get("object_id") or spec.get("name") or f"{kind}-{index}")
                regions.append({"region_id":f"s{slide_no}:{kind}:{oid}","role":"foreground","weight":1.0,"bbox":box})
    payload={"schema":"ai-ppt-plus/auto-layout-regions/v1","regions":regions}
    output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return payload

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("project");p.add_argument("--source",required=True);p.add_argument("--layout",required=True);p.add_argument("--out",required=True)
    p.add_argument("--request-id");p.add_argument("--font-dir");p.add_argument("--font-manifest");p.add_argument("--preview-dir")
    p.add_argument("--authoring-backend",choices=("artifact-tool","python-pptx"),default="artifact-tool");p.add_argument("--node");p.add_argument("--node-modules")
    p.add_argument("--overwrite",action="store_true");p.add_argument("--dpi",type=int,default=144)
    a=p.parse_args();project=Path(a.project).resolve();source=Path(a.source).resolve();layout=Path(a.layout).resolve();out=Path(a.out).resolve()
    command=[sys.executable,str(SCRIPT_DIR/"strict_reference_rerun.py"),str(project),"--source",str(source),"--layout",str(layout),"--out",str(out),"--authoring-backend",a.authoring_backend]
    for flag,value in (("--request-id",a.request_id),("--font-dir",a.font_dir),("--font-manifest",a.font_manifest),("--preview-dir",a.preview_dir),("--node",a.node),("--node-modules",a.node_modules)):
        if value:command += [flag,value]
    if a.overwrite:command.append("--overwrite")
    run(command,"strict authoring transaction")
    current_path=project/"current-rerun.json";current=load(current_path);run_dir=Path(current["authoring_provenance"]).resolve().parent
    render_dir=run_dir/"final-render";render_report=run_dir/"final-render.json"
    render_cmd=[sys.executable,str(SCRIPT_DIR/"render_pptx.py"),str(out),"--output-dir",str(render_dir),"--dpi",str(a.dpi),"--report",str(render_report)]
    if a.font_dir:render_cmd += ["--font-dir",str(Path(a.font_dir).resolve())]
    run(render_cmd,"fresh PPTX render");rendered=render_dir/"slide-1.png"
    if not rendered.is_file():raise SystemExit("fresh render did not produce slide-1.png")
    visual_report=run_dir/"reference-visual.json";visual_cmd=[sys.executable,str(SCRIPT_DIR/"compare_visual.py"),str(rendered),str(source),"--raw-slide","--report",str(visual_report)]
    visual=subprocess.run(visual_cmd,text=True,capture_output=True,check=False)
    if visual.stdout:print(visual.stdout,end="")
    regions_path=run_dir/"auto-layout-regions.json";region_manifest(layout,regions_path);region_report=run_dir/"auto-region-visual.json";crop_dir=run_dir/"local-crop-qa"
    region_run=subprocess.run([sys.executable,str(SCRIPT_DIR/"compare_visual_regions.py"),str(rendered),str(source),str(regions_path),"--report",str(region_report),"--crop-dir",str(crop_dir)],text=True,capture_output=True,check=False)
    if region_run.stdout:print(region_run.stdout,end="")
    if region_run.returncode!=0:
        if region_run.stderr:print(region_run.stderr,file=sys.stderr)
        raise SystemExit("local crop QA failed to produce valid same-coordinate region evidence")
    repair_trace=run_dir/"render-repair-trace.json"
    run([sys.executable,str(SCRIPT_DIR/"build_render_repair_trace.py"),str(layout),str(region_report),"--report",str(repair_trace)],"render review Repair Trace")
    if visual.returncode!=0:
        if visual.stderr:print(visual.stderr,file=sys.stderr)
        raise SystemExit("fresh render comparison failed structural validation")
    status="review-ready"
    current.update({"render":str(rendered),"render_report":str(render_report),"reference_visual":str(visual_report),"auto_region_visual":str(region_report),"local_crop_qa":str(crop_dir),"repair_trace":str(repair_trace),"visual_review_required":True,"visual_metrics_diagnostic_only":True,"status":status})
    current_path.write_text(json.dumps(current,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"deck":str(out),"render":str(rendered),"visual_report":str(visual_report),"region_report":str(region_report),"repair_trace":str(repair_trace),"local_crop_qa":str(crop_dir),"visual_metrics_diagnostic_only":True},ensure_ascii=False,indent=2));return 0

if __name__=="__main__":raise SystemExit(main())
