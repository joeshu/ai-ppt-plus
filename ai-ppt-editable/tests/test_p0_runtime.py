"""P0 integration/negative fixtures; not a visual acceptance of user cases."""
from pathlib import Path
import sys
import tempfile
import json
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from reconstruction.graph_ir import PageGraph
from reconstruction.relation_geometry import solve_graph_relations
from reconstruction.asset_metrics import compare_asset_subjects
from run_p0_repairs import run


def test_graph():
    graph = PageGraph.from_dict({"nodes": [
        {"id": "a", "type": "shape", "bbox": [.1, .1, .2, .1]},
        {"id": "b", "type": "shape", "bbox": [.5, .2, .3, .1], "relations": [
            {"kind": "aligned_top", "target": "a"}, {"kind": "equal_width", "target": "a"}]}]})
    result = solve_graph_relations(graph, locked_ids=["a"])
    assert abs(result["boxes"]["b"][1] - .1) < 1e-7
    assert abs(result["boxes"]["b"][2] - .2) < 1e-7
    try:
        solve_graph_relations(graph, locked_ids=["a", "b"])
    except ValueError:
        pass
    else:
        raise AssertionError("locked graph cannot be silently moved")


def test_nonfinite_gate():
    from reconstruction.quality_gate import QualityGate
    from reconstruction.difference_graph import DifferenceGraph
    differences = DifferenceGraph.from_dict({"findings": []})
    for value in (float("nan"), float("inf"), -1):
        result = QualityGate().evaluate(differences=differences, global_visual_similarity=value,
                                        editable_ratio=1, semantic_accuracy=1, full_slide_raster_detected=False)
        assert not result.passed
    string_result = QualityGate().evaluate(
        differences=differences,
        global_visual_similarity="not-a-number",
        editable_ratio=1,
        semantic_accuracy=1,
        full_slide_raster_detected=False,
    )
    assert not string_result.passed


def test_asset(root):
    from PIL import Image, ImageDraw
    a = Image.new("RGBA", (100, 100))
    ImageDraw.Draw(a).rectangle((20, 20, 79, 79), fill="red")
    a.save(root / "square.png")
    b = Image.new("RGBA", (100, 100))
    ImageDraw.Draw(b).ellipse((20, 20, 79, 79), fill="red")
    b.save(root / "circle.png")
    assert compare_asset_subjects(root / "square.png", root / "square.png")["silhouette_iou"] == 1
    assert compare_asset_subjects(root / "square.png", root / "circle.png")["silhouette_iou"] < .9


def test_entrypoint(root):
    from PIL import Image
    reference = root / "reference.png"
    Image.new("RGB", (1600, 900), "white").save(reference)
    digest = sha256(reference.read_bytes()).hexdigest()
    def save(name, data):
        (root / name).write_text(json.dumps(data), encoding="utf-8")
    save("inventory.json", {"source_sha256": digest, "observation_id": "fixture-observation",
        "method": "source-image-observation", "evidence": "synthetic integration fixture only",
        "objects": [{"id": "source-title"}]})
    save("page-graph.json", {"metadata": {"source_sha256": digest, "planning_observation_id": "fixture-plan"},
        "nodes": [{"id": "title", "type": "text", "bbox": [.1, .1, .8, .2],
                   "source": {"source_object_id": "source-title"}}]})
    save("route-decision.json", {"route": "reference-reconstruction"})
    save("slide-object-manifest.json", {"objects": [{"id": "title"}]})
    save("layout.json", {"assets_dir": ".", "units": "fraction", "slide_width_in": 13.33333,
        "slide_height_in": 7.5, "slides": [{"texts": [{"object_id": "title", "x": .1, "y": .1,
            "w": .8, "h": .2, "text": "Technical integration fixture", "font": "DejaVu Sans", "size": 24}]}]})
    save("plan.json", {"reference": "reference.png", "inventory": "inventory.json",
        "graph": "page-graph.json", "layout": "layout.json"})
    result = run(root / "plan.json", root / "output")
    assert result["status"] == "pending-visual-review" and result["release_eligible"] is False
    assert result["final_coverage"]["valid"]
    Image.new("RGB", (1600, 900), "black").save(reference)
    try:
        run(root / "plan.json", root / "stale")
    except ValueError:
        pass
    else:
        raise AssertionError("stale source must block before authoring")


if __name__ == "__main__":
    test_graph()
    test_nonfinite_gate()
    with tempfile.TemporaryDirectory(prefix="p0-test-") as directory:
        test_asset(Path(directory))
        test_entrypoint(Path(directory))
    print("PASS P0 graph, silhouette and actual compose/render integration")
