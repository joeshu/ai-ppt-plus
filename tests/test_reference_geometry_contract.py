#!/usr/bin/env python3
"""Regression proof for fixed-reference PageGraph geometry and measured line boxes."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EDITABLE=ROOT/"ai-ppt-editable"/"scripts"
sys.path.insert(0,str(EDITABLE))

from validate_page_geometry import audit_page_geometry  # noqa:E402
from validate_measured_line_boxes import audit_measured_line_boxes  # noqa:E402


def write(path:Path,value:dict)->None:
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main()->int:
    with tempfile.TemporaryDirectory(prefix="reference-geometry-contract-") as raw:
        root=Path(raw)
        write(root/"route-decision.json",{"route":"reference-reconstruction"})
        write(root/"page-graph.json",{
            "version":"1",
            "page":{"slide_width_in":13.333333,"slide_height_in":7.5,"reference_width":1000,"reference_height":500,"coordinate_units":"fraction"},
            "metadata":{"geometry_tolerance":{"min_iou":0.80,"max_center_error":0.02,"max_size_error":0.04}},
            "nodes":[{"id":"title","type":"text","bbox":[0.10,0.08,0.50,0.08],"confidence":0.99}]
        })
        deck={
            "units":"fraction",
            "require_measured_line_boxes":True,
            "slides":[{"texts":[{
                "object_id":"title","text":"Reference title","x":0.10,"y":0.08,"w":0.50,"h":0.08,
                "reference_line_count":1,
                "source_bbox":[100,40,500,40],
                "reference_line_boxes":[[100,40,500,40]]
            }]}]
        }
        layout=root/"layout.json";write(layout,deck)
        geometry=audit_page_geometry(layout,deck)
        lines=audit_measured_line_boxes(layout,deck)
        assert geometry["valid"] and geometry["checked"]==1,geometry
        assert lines["valid"] and lines["required"] and lines["checked"]==1,lines

        drift=json.loads(json.dumps(deck));drift["slides"][0]["texts"][0]["x"]=0.20
        assert not audit_page_geometry(layout,drift)["valid"]

        missing=json.loads(json.dumps(deck));del missing["slides"][0]["texts"][0]["reference_line_boxes"]
        assert not audit_measured_line_boxes(layout,missing)["valid"]

    gate=(EDITABLE/"text_fit_authoring_gate.py").read_text(encoding="utf-8")
    for token in ("audit_page_geometry","audit_measured_line_boxes","page_geometry_defect_count","measured_line_box_defect_count"):
        assert token in gate,token
    print("reference geometry + measured line-box contract: ok")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
