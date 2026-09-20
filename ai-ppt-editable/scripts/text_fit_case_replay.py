#!/usr/bin/env python3
"""Aggregate B1-B4 text-fit evidence across frozen real replay cases.

A case may PASS only when its real source is resolved and every acceptance
requirement has materialized evidence. Missing source/evidence is NOT_RUN;
invalid evidence is FAIL. Synthetic substitutes are never accepted.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from typing import Any
SCHEMA="ai-ppt-plus/text-fit-case-replay/v2"
def _load(path:Path)->Any:return json.loads(path.read_text(encoding="utf-8"))
def _resolve(base:Path,value:Any)->Path|None:
    if not isinstance(value,str) or not value.strip():return None
    path=Path(value);return path if path.is_absolute() else (base/path).resolve()
def _required(a:dict)->list[str]:
    out=["text_fit_report","text_render_feedback"]
    if int(a.get("text_loss_allowed",0))==0 or a.get("native_text_required",True):out.append("text_coverage_audit")
    if int(a.get("whole_slide_raster_allowed",0))==0 or a.get("native_text_required",True):out.append("editability_audit")
    if a.get("fresh_render_required_after_repair",True):out.append("render_provenance")
    return out
def _c(name:str,passed:bool,**details:Any)->dict:
    row={"name":name,"passed":bool(passed)}
    if details:row["details"]=details
    return row
def _fit(r:dict,a:dict)->list[dict]:
    slots=[x for x in r.get("slots") or [] if isinstance(x,dict)]
    overflow=[x.get("object_id") for x in slots if x.get("overflow") is True or x.get("fits") is False or x.get("target_fits") is False]
    bad=[x.get("object_id") for x in slots if a.get("font_shrink_last",True) and (x.get("repair") or {}).get("font_shrink_last") is False]
    return [_c("text_fit_report_valid",r.get("valid") is not False),_c("all_text_slots_measured",r.get("all_slots_measured") is True),_c("no_text_overflow",len(overflow)<=int(a.get("overflow_allowed",0)),overflow_slots=overflow),_c("font_shrink_last",not bad,violations=bad)]
def _feedback(r:dict)->list[dict]:
    records=[x for x in r.get("records") or [] if isinstance(x,dict)];missing=[];bad=[]
    for x in records:
        if not (x.get("reference") or {}).get("render_sha256") or not (x.get("candidate") or {}).get("render_sha256"):missing.append(x.get("object_id"))
        if x.get("repair_required") and not (x.get("repair") or {}).get("requires_fresh_render"):bad.append(x.get("object_id"))
    return [_c("render_feedback_valid",r.get("valid") is True),_c("render_hashes_bound",not missing,violations=missing),_c("fresh_render_contract_after_repair",not bad,violations=bad)]
def _coverage(r:dict)->list[dict]:
    uncovered=r.get("uncovered_native_text") or []
    return [_c("text_coverage_audit_valid",r.get("valid") is True and r.get("status")=="passed"),_c("zero_native_text_loss",not uncovered,uncovered_native_text=uncovered)]
def _editable(r:dict,a:dict)->list[dict]:
    s=r.get("summary") if isinstance(r.get("summary"),dict) else r;raster=int(s.get("whole_slide_raster_count") or s.get("full_slide_raster_count") or 0);native=int(s.get("native_text_count") or s.get("editable_text_count") or 0)
    out=[_c("editability_audit_valid",r.get("valid") is True),_c("whole_slide_raster_limit",raster<=int(a.get("whole_slide_raster_allowed",0)),observed=raster)]
    if a.get("native_text_required",True):out.append(_c("native_text_present",native>0,observed=native))
    return out
def _provenance(r:dict)->list[dict]:
    cand=r.get("candidate_artifact_sha256");rendered=r.get("rendered_from_candidate_sha256")
    return [_c("render_provenance_valid",r.get("valid") is True),_c("fresh_candidate_render",r.get("fresh_candidate_render") is True),_c("render_bound_to_candidate",bool(cand) and cand==rendered,candidate_artifact_sha256=cand,rendered_from_candidate_sha256=rendered)]
def evaluate(manifest:dict,*,root:Path)->dict:
    a=manifest.get("acceptance") or {};required=_required(a);rows=[]
    for case in manifest.get("cases") or []:
        ev=case.get("evidence") or {};paths={k:_resolve(root,ev.get(k)) for k in required};missing=[k for k,p in paths.items() if p is None or not p.is_file()]
        source_status=str(case.get("status") or "")
        if source_status!="source_resolved":missing.insert(0,"source_reference")
        checks=[]
        if not missing:
            checks+=_fit(_load(paths["text_fit_report"]),a);checks+=_feedback(_load(paths["text_render_feedback"]));checks+=_coverage(_load(paths["text_coverage_audit"]));checks+=_editable(_load(paths["editability_audit"]),a);checks+=_provenance(_load(paths["render_provenance"]))
        status="NOT_RUN" if missing else ("PASS" if all(x["passed"] for x in checks) else "FAIL")
        rows.append({"id":str(case.get("id") or ""),"name":case.get("name"),"source_status":source_status,"source":case.get("source"),"focus":case.get("focus") or [],"status":status,"required_evidence":required,"missing_evidence":missing,"checks":checks})
    summary={"case_count":len(rows),"pass_count":sum(x["status"]=="PASS" for x in rows),"fail_count":sum(x["status"]=="FAIL" for x in rows),"not_run_count":sum(x["status"]=="NOT_RUN" for x in rows)}
    return {"schema":SCHEMA,"batch":manifest.get("batch"),"release_ready":bool(rows) and summary["pass_count"]==len(rows),"acceptance":a,"required_evidence":required,"summary":summary,"cases":rows}
def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",required=True,type=Path);p.add_argument("--root",type=Path);p.add_argument("--report",required=True,type=Path);p.add_argument("--require-complete",action="store_true");args=p.parse_args();mp=args.manifest.resolve();root=args.root.resolve() if args.root else mp.parent;report=evaluate(_load(mp),root=root);args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps({**report["summary"],"release_ready":report["release_ready"],"report":str(args.report)},ensure_ascii=False));return 2 if report["summary"]["fail_count"] else (3 if args.require_complete and not report["release_ready"] else 0)
if __name__=="__main__":raise SystemExit(main())
