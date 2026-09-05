from __future__ import annotations

from copy import deepcopy

from reconstruction.object_drift_guard import compare_object_drift, fingerprint_deck


def _deck():
    return {
        "units": "fraction",
        "slides": [{
            "texts": [
                {"object_id": "title", "x": 0.1, "y": 0.1, "w": 0.4, "h": 0.08, "text": "标题", "font_size": 24, "color": "#111111"},
                {"object_id": "body", "x": 0.1, "y": 0.25, "w": 0.5, "h": 0.3, "text": "正文", "font_size": 16},
            ],
            "icons": [
                {"object_id": "icon", "x": 0.8, "y": 0.1, "w": 0.08, "h": 0.08, "file": "icon.png", "source_sha256": "abc"},
            ],
        }],
    }


def test_fingerprint_is_stable_for_identical_decks():
    first = fingerprint_deck(_deck())
    second = fingerprint_deck(deepcopy(_deck()))
    assert first == second


def test_allowed_target_change_does_not_count_as_drift():
    before = _deck()
    after = deepcopy(before)
    after["slides"][0]["texts"][0]["font_size"] = 28
    report = compare_object_drift(before, after, allowed_object_ids={"title"})
    assert report["valid"] is True
    assert report["unauthorized_drift_count"] == 0


def test_unrelated_text_change_is_detected():
    before = _deck()
    after = deepcopy(before)
    after["slides"][0]["texts"][1]["text"] = "正文被误改"
    report = compare_object_drift(before, after, allowed_object_ids={"title"})
    assert report["valid"] is False
    assert report["drift"][0]["object_id"] == "body"
    assert "text" in report["drift"][0]["changed_domains"]


def test_unrelated_geometry_and_asset_hash_changes_are_detected():
    before = _deck()
    after = deepcopy(before)
    after["slides"][0]["texts"][1]["x"] = 0.11
    after["slides"][0]["icons"][0]["source_sha256"] = "def"
    report = compare_object_drift(before, after, allowed_object_ids={"title"})
    assert report["valid"] is False
    domains = {item["object_id"]: set(item["changed_domains"]) for item in report["drift"]}
    assert "geometry" in domains["body"]
    assert "asset" in domains["icon"]


def test_unrelated_object_add_remove_are_detected():
    before = _deck()
    after = deepcopy(before)
    after["slides"][0]["texts"] = [item for item in after["slides"][0]["texts"] if item["object_id"] != "body"]
    after["slides"][0]["texts"].append({"object_id": "unexpected", "x": 0.2, "y": 0.2, "w": 0.1, "h": 0.1, "text": "X"})
    report = compare_object_drift(before, after, allowed_object_ids={"title"})
    assert report["valid"] is False
    assert report["missing"] == ["body"]
    assert report["added"] == ["unexpected"]


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("Object drift guard tests passed")
