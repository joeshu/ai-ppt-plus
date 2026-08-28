#!/usr/bin/env python3
"""Validate ai-ppt-plus outline CSV/XLSX. Read-only and idempotent.

Usage: validate_outline.py OUTLINE [--report FILE] [--require-approved]
Output JSON. Exit 0 valid, 2 contract failure, 3 runtime/dependency error.
XLSX requires openpyxl. Example: python validate_outline.py outline.csv
"""
import argparse,csv,json,re
from pathlib import Path
from atomic_output import atomic_write_json
FIELDS=['slide_no','section','title','core_message','purpose','body_content','data_sources','visual_type','audience_takeaway','owner_notes','status','revision_reason']
TYPES={'title','agenda','section','comparison','timeline','process','framework','matrix','funnel','pyramid','map','chart','table','infographic','scene','quote','summary','appendix'}
STATES={'draft','needs_user','approved','blocked','superseded'}
def read_rows(path):
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    if path.suffix.lower()!='.xlsx':raise ValueError('only CSV and XLSX are supported')
    import openpyxl
    wb=openpyxl.load_workbook(path,read_only=True,data_only=False); ws=wb.active; data=list(ws.iter_rows(values_only=True)); wb.close()
    if not data:return []
    heads=[str(v or '').strip() for v in data[0]]
    return [dict(zip(heads,row)) for row in data[1:] if any(v not in (None,'') for v in row)]
def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument('outline'); ap.add_argument('--report'); ap.add_argument('--require-approved',action='store_true'); ap.add_argument('--max-body-chars',type=int,default=900); a=ap.parse_args(); p=Path(a.outline); issues=[]
    try:
        if not p.is_file():raise FileNotFoundError(p)
        rows=read_rows(p)
    except Exception as e:print(json.dumps({'valid':False,'error':f'{type(e).__name__}: {e}'},ensure_ascii=False));return 3
    headers=set(rows[0]) if rows else set()
    for f in FIELDS:
        if f not in headers:issues.append({'severity':'blocker','code':'missing_column','field':f})
    nums=[]
    for line,r in enumerate(rows,2):
        try:nums.append(int(r.get('slide_no')))
        except Exception:issues.append({'severity':'blocker','code':'invalid_slide_no','row':line});continue
        status=str(r.get('status') or '').strip(); visual=str(r.get('visual_type') or '').strip()
        if status not in STATES:issues.append({'severity':'blocker','code':'invalid_status','row':line,'value':status})
        if visual not in TYPES:issues.append({'severity':'major','code':'invalid_visual_type','row':line,'value':visual})
        for f in ('section','title','core_message','purpose','body_content','audience_takeaway'):
            if not str(r.get(f) or '').strip():issues.append({'severity':'major','code':'empty_required','row':line,'field':f})
        body=str(r.get('body_content') or ''); source=str(r.get('data_sources') or '').strip()
        if len(body)>a.max_body_chars:issues.append({'severity':'major','code':'body_too_long','row':line,'chars':len(body)})
        if (re.search(r'\d',body) or status=='approved') and not source:issues.append({'severity':'critical','code':'fact_or_approval_without_source_treatment','row':line})
        if a.require_approved and status not in {'approved','superseded'}:issues.append({'severity':'blocker','code':'narrative_not_approved','row':line,'status':status})
    if len(nums)!=len(set(nums)):issues.append({'severity':'blocker','code':'duplicate_slide_no','observed':nums})
    if nums and sorted(nums)!=list(range(1,max(nums)+1)):issues.append({'severity':'blocker','code':'non_contiguous_slide_no','observed':nums})
    valid=bool(rows) and not any(i['severity'] in {'blocker','critical'} for i in issues); out={'schema':'ai-ppt-plus/outline-validation/v1','valid':valid,'rows':len(rows),'issues':issues}
    if a.report:atomic_write_json(Path(a.report).resolve(), out)
    print(json.dumps(out,ensure_ascii=False));return 0 if valid else 2
if __name__=='__main__':raise SystemExit(main())
