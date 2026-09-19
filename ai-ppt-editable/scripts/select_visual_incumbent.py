#!/usr/bin/env python3
"""Fail closed on visual regression and emit a region-level repair plan."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def load(path: Path) -> dict:
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict):
        raise ValueError(f'{path} must contain an object')
    return value


def score(report: dict) -> float:
    for key in ('whole_page_ssim','ssim','raw_ssim'):
        if key in report:
            return float(report[key])
    candidate=report.get('candidate')
    if isinstance(candidate,dict):
        for key in ('whole_page_ssim','ssim','raw_ssim'):
            if key in candidate:
                return float(candidate[key])
    rendered=report.get('rendered_fidelity')
    if isinstance(rendered,dict) and 'ssim' in rendered:
        return float(rendered['ssim'])
    raise ValueError('visual report has no whole-page SSIM')


def regional_scores(report: dict) -> dict[str,float]:
    """Return normalized region->SSIM from supported report shapes."""
    candidates=[
        report.get('regional_ssim'),
        report.get('regions'),
        (report.get('candidate') or {}).get('regional_ssim') if isinstance(report.get('candidate'),dict) else None,
        (report.get('rendered_fidelity') or {}).get('regional_ssim') if isinstance(report.get('rendered_fidelity'),dict) else None,
    ]
    for value in candidates:
        if isinstance(value,dict):
            out={}
            for key,raw in value.items():
                try:
                    out[str(key)]=float(raw)
                except (TypeError,ValueError):
                    continue
            if out:
                return out
    return {}


def _repair_priority(regions: dict[str,float], strict_threshold: float) -> list[dict]:
    return [
        {'region':name,'ssim':round(value,9),'gap_to_strict':round(max(0.0,strict_threshold-value),9)}
        for name,value in sorted(regions.items(), key=lambda item:(item[1], item[0]))
        if value < strict_threshold
    ]


def select(incumbent: dict, challenger: dict, *, strict_threshold: float=0.90) -> dict:
    old=score(incumbent); new=score(challenger)
    selected=new > old
    inc_regions=regional_scores(incumbent); chal_regions=regional_scores(challenger)
    common=sorted(set(inc_regions)&set(chal_regions))
    deltas={name:round(chal_regions[name]-inc_regions[name],9) for name in common}
    protected=[name for name,delta in deltas.items() if delta >= 0.01]
    regressed=[name for name,delta in deltas.items() if delta <= -0.005]
    active_regions=chal_regions if selected else inc_regions
    return {
      'schema':'ai-ppt-plus/visual-incumbent-selection/v2',
      'valid': selected,
      'selected':'challenger' if selected else 'incumbent',
      'incumbent_ssim':old,
      'challenger_ssim':new,
      'delta':round(new-old,9),
      'strict_threshold':strict_threshold,
      'release_ready':bool(selected and new >= strict_threshold),
      'status':'improved' if selected else 'rejected-regression',
      'regional_deltas':deltas,
      'protected_regions':protected if selected else [],
      'regressed_regions':regressed if selected else [],
      'repair_priority':_repair_priority(active_regions,strict_threshold),
      'policy':'challenger must strictly improve whole-page fidelity; preserve regional wins; repair the lowest active-region SSIM first; release additionally requires strict threshold',
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('incumbent',type=Path);p.add_argument('challenger',type=Path)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--strict-threshold',type=float,default=0.90)
    a=p.parse_args(); result=select(load(a.incumbent),load(a.challenger),strict_threshold=a.strict_threshold)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return 0 if result['valid'] else 2


if __name__=='__main__':
    raise SystemExit(main())
