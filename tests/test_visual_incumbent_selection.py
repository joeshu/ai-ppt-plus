#!/usr/bin/env python3
"""Regression proof for incumbent-controlled regional visual repair planning."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from select_visual_incumbent import select  # noqa:E402


def main()->int:
    incumbent={'ssim':0.60,'regional_ssim':{'outcome':0.49,'header':0.63,'chart':0.59}}
    challenger={'ssim':0.61,'regional_ssim':{'outcome':0.52,'header':0.62,'chart':0.61}}
    result=select(incumbent,challenger,strict_threshold=0.90)
    assert result['valid'] and result['selected']=='challenger'
    assert result['repair_priority'][0]['region']=='outcome'
    assert result['protected_regions']==['chart','outcome']
    assert result['regressed_regions']==['header']
    assert result['regional_deltas']['chart']==0.02
    assert not result['release_ready']

    regressed=select(incumbent,{'ssim':0.59,'regional_ssim':{'outcome':0.70}},strict_threshold=0.90)
    assert not regressed['valid'] and regressed['selected']=='incumbent'
    assert regressed['repair_priority'][0]['region']=='outcome'
    assert regressed['protected_regions']==[] and regressed['regressed_regions']==[]
    print('visual incumbent regional repair plan: ok')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
