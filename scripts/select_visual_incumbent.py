#!/usr/bin/env python3
"""Fail closed when a fresh fixed-reference iteration regresses visual fidelity."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def load(path: Path) -> dict:
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict): raise ValueError(f'{path} must contain an object')
    return value


def score(report: dict) -> float:
    for key in ('whole_page_ssim','ssim','raw_ssim'):
        if key in report: return float(report[key])
    candidate=report.get('candidate')
    if isinstance(candidate,dict):
        for key in ('whole_page_ssim','ssim','raw_ssim'):
            if key in candidate: return float(candidate[key])
    rendered=report.get('rendered_fidelity')
    if isinstance(rendered,dict) and 'ssim' in rendered: return float(rendered['ssim'])
    raise ValueError('visual report has no whole-page SSIM')


def select(incumbent: dict, challenger: dict, *, strict_threshold: float=0.90) -> dict:
    old=score(incumbent); new=score(challenger)
    selected=new > old
    return {
      'schema':'ai-ppt-plus/visual-incumbent-selection/v1',
      'valid': selected,
      'selected':'challenger' if selected else 'incumbent',
      'incumbent_ssim':old,
      'challenger_ssim':new,
      'delta':round(new-old,9),
      'strict_threshold':strict_threshold,
      'release_ready':bool(selected and new >= strict_threshold),
      'status':'improved' if selected else 'rejected-regression',
      'policy':'challenger must strictly improve whole-page fidelity; release additionally requires strict threshold',
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('incumbent',type=Path);p.add_argument('challenger',type=Path)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--strict-threshold',type=float,default=0.90)
    a=p.parse_args(); result=select(load(a.incumbent),load(a.challenger),strict_threshold=a.strict_threshold)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0 if result['valid'] else 2

if __name__=='__main__': raise SystemExit(main())
