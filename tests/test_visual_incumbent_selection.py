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
    assert result['valid'] and result['selected']=='challenger' and result['accepted_challenger']
    assert result['repair_priority'][0]['region']=='outcome'
    assert result['protected_regions']==['chart','outcome']
    assert result['regressed_regions']==['header']
    assert result['regional_deltas']['chart']==0.02
    assert result['release_ready'] is None

    regressed=select(incumbent,{'ssim':0.59,'regional_ssim':{'outcome':0.70}},strict_threshold=0.90)
    assert regressed['valid'] and not regressed['accepted_challenger'] and regressed['selected']=='incumbent'
    assert regressed['repair_priority'][0]['region']=='outcome'
    assert regressed['protected_regions']==[]

    current_shape={'metrics':{'reference_fidelity_score':0.84},'regions':[{'region_id':'header','score':0.58},{'region_id':'footer','score':0.63}]}
    better_shape={'metrics':{'reference_fidelity_score':0.85},'regions':[{'region_id':'header','score':0.60},{'region_id':'footer','score':0.64}]}
    modern=select(current_shape,better_shape)
    assert modern['selected']=='challenger'
    assert modern['repair_priority'][0]['region']=='header'

    unsafe_shape={'metrics':{'reference_fidelity_score':0.86},'regions':[{'region_id':'header','score':0.61},{'region_id':'footer','score':0.60}]}
    guarded=select(better_shape,unsafe_shape,max_region_regression=0.02)
    assert guarded['selected']=='incumbent'
    assert guarded['severe_regressions']==['footer']
    print('visual incumbent regional repair plan: ok')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
