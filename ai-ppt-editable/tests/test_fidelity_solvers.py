import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reconstruction.typography_search import calibrate_typography
from reconstruction.relation_geometry import solve_peer_layout
from reconstruction.asset_subject import subject_placement


def test_typography_search():
    obj = {"text": "高质量发展", "font_size": 20, "runs": [{"text": "高质量", "color": "FF0000"}]}
    target = {"ink_bbox": [0, 0, .4, .1], "line_count": 1, "baselines": [.08]}
    def renderer(candidate):
        return {"renderer": "test-double", "render_sha256": "a" * 64,
                "font_verified": True, "overflow": False, "line_count": 1,
                "ink_bbox": [0, 0, .4 if candidate["font_size"] == 22 else .3, .1],
                "baselines": [.08]}
    result = calibrate_typography(obj, target, [{"font_size": 22}], renderer)
    assert result["status"] == "accepted" and result["render_calls"] == 2
    assert obj["font_size"] == 20
    assert result["best"]["object"]["runs"] == obj["runs"]
    assert calibrate_typography(obj, target, [{"font_size": 22}], renderer, budget=1)["status"] == "needs-review"
    try:
        calibrate_typography(obj, target, [{"text": "changed"}], renderer)
    except ValueError:
        pass
    else:
        raise AssertionError("must reject copy edits")


def test_relations():
    objects = {"a": {"x": .1, "w": .2}, "b": {"x": .4, "w": .2}, "c": {"x": .6, "w": .2},
               "unrelated": {"x": .8, "w": .1}}
    result = solve_peer_layout(objects, ["a", "b", "c"], start=.1, end=.9)
    assert abs(result["objects"]["c"]["x"] - .7) < 1e-9
    assert result["objects"]["unrelated"] == objects["unrelated"]
    assert objects["c"]["x"] == .6
    for kwargs in ({"locked_ids": ["c"]}, {"end": .5}):
        options = {"start": .1, "end": .9, **kwargs}
        try:
            solve_peer_layout(objects, ["a", "b", "c"], **options)
        except ValueError:
            pass
        else:
            raise AssertionError("must reject locked or infeasible constraints")


def test_subject():
    from PIL import Image
    with TemporaryDirectory() as folder:
        path = Path(folder) / "subject.png"
        im = Image.new("RGBA", (100, 100))
        im.paste((255, 0, 0, 255), (25, 25, 75, 75))
        im.save(path)
        original = path.read_bytes()
        result = subject_placement(path, [10, 10, 20, 20])
        assert result["image_bbox"] == [0, 0, 40, 40]
        assert path.read_bytes() == original
        try:
            subject_placement(path, [10, 10, 40, 20])
        except ValueError:
            pass
        else:
            raise AssertionError("must reject stretching")


def test_authoring_integration():
    from reconstruction.repair_executors import execute_peer_layout, execute_typography_search
    deck = {"units": "fraction", "slides": [{"shapes": [
        {"id": "a", "x": .1, "y": .1, "w": .2, "h": .1},
        {"id": "b", "x": .4, "y": .1, "w": .2, "h": .1}],
        "texts": [{"id": "t", "text": "immutable", "font_size": 20}]}]}
    result = execute_peer_layout(deck, ["a", "b"], start=.1, end=.9)
    assert abs(result["deck"]["slides"][0]["shapes"][1]["x"] - .7) < 1e-9
    assert result["report"]["applied"] == [{"object_id": "b", "domain": "geometry"}]
    target = {"ink_bbox": [0, 0, .4, .1], "line_count": 1, "baselines": [.08]}
    def bad_renderer(candidate, object_id):
        assert object_id == "t"
        return {"renderer": "test-double", "render_sha256": "a" * 64,
                "font_verified": False, "overflow": False}
    result = execute_typography_search(deck, "t", target, [{"font_size": 22}], bad_renderer)
    assert not result["report"]["valid"]
    assert result["deck"] == deck and result["report"]["applied"] == []


if __name__ == "__main__":
    test_typography_search()
    test_relations()
    test_subject()
    test_authoring_integration()
    print("4 fidelity solver test groups passed (renderer is a test double)")
