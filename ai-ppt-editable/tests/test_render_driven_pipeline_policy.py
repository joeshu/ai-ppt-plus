from __future__ import annotations

import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from reconstruction.difference_graph import DifferenceGraph
from reconstruction.graph_ir import PageGraph
from reconstruction.pipeline import ReconstructionPipeline, Stage
from reconstruction.quality_gate import QualityGate
from reconstruction.repair_executors import execute_plan


def _page_graph()->PageGraph:
    return PageGraph.from_dict({
        "version":"1.0",
        "page":{"slide_width_in":13.333333,"slide_height_in":7.5,"reference_width":1600,"reference_height":900},
        "nodes":[{"id":"title","type":"text","bbox":[0.1,0.1,0.4,0.08],"semantic":{"text":"标题"}}],
    })


def _deck()->dict:
    return {"units":"fraction","slides":[{"texts":[{"object_id":"title","x":0.1,"y":0.1,"w":0.4,"h":0.08,"text":"标题","font_size":24}]}]}


def _empty_diff()->DifferenceGraph:
    return DifferenceGraph.from_dict({"version":"1.0","source_id":"source","rendered_id":"render","findings":[]})


def _metrics(score:float)->dict:
    return {
        "global_visual_similarity":score,
        "critical_region_scores":{"title":score},
        "editable_ratio":1.0,
        "semantic_accuracy":1.0,
        "full_slide_raster_detected":False,
        "renderer_regressions":[],
    }


def test_visual_metrics_are_diagnostic_not_numeric_gate():
    gate=QualityGate()
    result=gate.evaluate(
        differences=_empty_diff(),global_visual_similarity=0.10,critical_region_scores={"title":0.05},
        editable_ratio=1.0,semantic_accuracy=1.0,full_slide_raster_detected=False,renderer_regressions=[],
    )
    assert result.passed is True
    assert result.metrics["visual_metrics_diagnostic_only"] is True
    assert result.metrics["global_visual_similarity"]==0.10


def test_pipeline_completes_when_hard_correctness_passes_and_no_repairs_remain():
    pipe=ReconstructionPipeline(max_iterations=2)
    state=pipe.run(
        understand=_page_graph,
        author=lambda graph:_deck(),
        render=lambda deck:"render.png",
        inspect=lambda graph,deck,rendered:_empty_diff(),
        apply_repairs=lambda deck,plan:execute_plan(deck,plan),
        measure=lambda graph,deck,rendered,differences:_metrics(0.20),
    )
    assert state.stage==Stage.COMPLETE
    assert "final" in state.artifacts
    assert state.history[-1].metrics["visual_metrics_diagnostic_only"] is True


def test_pipeline_applies_safe_object_repair_before_completion():
    calls={"inspect":0}
    def inspect(graph,deck,rendered):
        calls["inspect"]+=1
        if calls["inspect"]==1:
            return DifferenceGraph.from_dict({
                "version":"1.0","source_id":"source","rendered_id":"render",
                "findings":[{
                    "id":"title-width","object_id":"title","domain":"geometry","severity":"P1",
                    "message":"title width too narrow","confidence":0.99,"proposed_patch":{"w":0.45},
                }],
            })
        return _empty_diff()
    pipe=ReconstructionPipeline(max_iterations=3)
    state=pipe.run(
        understand=_page_graph,
        author=lambda graph:_deck(),
        render=lambda deck:"render.png",
        inspect=inspect,
        apply_repairs=lambda deck,plan:execute_plan(deck,plan),
        measure=lambda graph,deck,rendered,differences:_metrics(0.25),
    )
    assert state.stage==Stage.COMPLETE
    repaired=state.artifacts["candidate_2"]
    assert repaired["slides"][0]["texts"][0]["w"]==0.45
    assert len(state.history)>=2


if __name__=="__main__":
    for name,value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("render-driven reconstruction policy tests passed")
