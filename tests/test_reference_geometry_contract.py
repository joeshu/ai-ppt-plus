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
from calibrate_page_geometry import apply_page_graph_geometry  # noqa:E402


def write(path:Path,value:dict)->None:
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def main()->int:
    with tempfile.TemporaryDirectory(prefix="reference-geometry-contract-") as raw:
        root=Path(raw);write(root/"route-decision.json",{"route":"reference-reconstruction"})
        graph={
            "version":"1",
            "page":{"slide_width_in":13.333333,"slide_height_in":7.5,"reference_width":1000,"reference_height":500,"coordinate_units":"fraction"},
            "metadata":{"geometry_tolerance":{"min_iou":0.80,"max_center_error":0.02,"max_size_error":0.04}},
            "nodes":[{"id":"title","type":"text","bbox":[0.10,0.08,0.50,0.08],"confidence":0.99,"text_evidence":{
                "reference_line_count":1,"reference_line_boxes":[[100,40,500,40]],"source_bbox":[100,40,500,40],
                "font_size_pt":24,"bold":True,"color":"#111111","line_spacing":1.0
            }}]
        }
        write(root/"page-graph.json",graph)
        deck={"units":"fraction","require_measured_line_boxes":True,"slides":[{"texts":[{
            "object_id":"title","text":"Reference title","x":0.10,"y":0.08,"w":0.50,"h":0.08,
            "font_size_pt":18,"bold":False
        }]}]}
        layout=root/"layout.json";write(layout,deck)

        calibrated,calibration=apply_page_graph_geometry(deck,graph)
        title=calibrated["slides"][0]["texts"][0]
        assert title["x"]==0.10 and title["w"]==0.50,title
        assert title["reference_line_count"]==1 and title["max_lines"]==1,title
        assert title["reference_line_boxes"]==[[100,40,500,40]],title
        assert title["source_bbox"]==[100,40,500,40],title
        assert title["font_size_pt"]==24 and title["bold"] is True,title
        assert title["reference_text_evidence_locked"] is True,title
        assert calibration["applied_count"]==1 and calibration["text_evidence_applied_count"]==1,calibration

        calibrated_layout=root/"calibrated.json";write(calibrated_layout,calibrated)
        geometry=audit_page_geometry(calibrated_layout,calibrated)
        lines=audit_measured_line_boxes(calibrated_layout,calibrated)
        assert geometry["valid"] and geometry["checked"]==1,geometry
        assert lines["valid"] and lines["required"] and lines["checked"]==1,lines

        missing=json.loads(json.dumps(calibrated));del missing["slides"][0]["texts"][0]["reference_line_boxes"]
        missing_layout=root/"missing.json";write(missing_layout,missing)
        assert not audit_measured_line_boxes(missing_layout,missing)["valid"]

    gate=(EDITABLE/"text_fit_authoring_gate.py").read_text(encoding="utf-8")
    for token in ("audit_page_geometry","audit_measured_line_boxes","page_geometry_defect_count","measured_line_box_defect_count"):
        assert token in gate,token
    print("reference geometry + text evidence + measured line-box contract: ok")
    return 0


if __name__=="__main__": raise SystemExit(main())
