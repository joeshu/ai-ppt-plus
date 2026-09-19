#!/usr/bin/env python3
"""Audit that every visible native text-producing path has Text Slot Preflight evidence."""
from __future__ import annotations
import argparse, json
from pathlib import Path

TEXT_PRODUCERS={"text_box","add_run","table_cell","badge_label","legend","number_unit","chart_label","caption","title","subtitle"}
REQUIRED_EVIDENCE=("slot_bbox","font_face")

def audit(plan, ledger):
    entries=ledger.get("entries",ledger.get("texts",[])); by_id={str(e.get("object_id") or e.get("id")):e for e in entries if isinstance(e,dict)}
    issues=[]; required=[]; covered=[]
    for obj in plan.get("objects",[]):
        if obj.get("implementation_type")!="native_text": continue
        contract=obj.get("text_contract") or {}; producer=str(contract.get("producer") or "text_box")
        if producer not in TEXT_PRODUCERS: issues.append({"code":"unknown_text_producer","object_id":obj.get("object_id"),"producer":producer})
        oid=str(obj.get("object_id")); required.append(oid); ev=by_id.get(oid)
        if not ev:
            issues.append({"code":"missing_text_fit_evidence","object_id":oid,"producer":producer}); continue
        missing=[k for k in REQUIRED_EVIDENCE if ev.get(k) is None and contract.get(k) is None]
        fit=ev.get("fit_evidence") or ev.get("fit") or ev.get("measurement")
        if fit is None: missing.append("fit_evidence")
        if missing: issues.append({"code":"incomplete_text_fit_evidence","object_id":oid,"missing":missing,"producer":producer})
        else: covered.append(oid)
    extra=sorted(set(by_id)-set(required))
    return {"schema":"ai-ppt-plus/text-coverage-audit/v1","valid":not issues,"required_count":len(required),"covered_count":len(covered),"coverage":1.0 if not required else len(covered)/len(required),"required_object_ids":required,"covered_object_ids":covered,"extra_ledger_object_ids":extra,"issues":issues,"policy":{"all_visible_native_text_paths_require_preflight":True,"font_shrink_is_not_a_substitute":True}}

def main():
    p=argparse.ArgumentParser(); p.add_argument("authoring_plan",type=Path); p.add_argument("text_ledger",type=Path); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    result=audit(json.loads(a.authoring_plan.read_text(encoding="utf-8")),json.loads(a.text_ledger.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"valid":result["valid"],"coverage":result["coverage"],"output":str(a.output)})); return 0 if result["valid"] else 2
if __name__=="__main__": raise SystemExit(main())
