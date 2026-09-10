import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_semantic_layout import EDITABILITY_INCOMPLETE, FLATTENED, FALSE_POSITIVE, TYPE_MISMATCH, validate


def test_repeated_component_is_blocked_when_still_authored_as_table():
    table = {
        "object_id": "actions", "semantic_type": "repeated_component_group",
        "rows": [["标题", "正文"]], "representation": "native",
    }
    result = validate({"slides": [{"tables": [table], "icons": []}]})
    assert result["valid"] is False
    assert result["issues"][0]["code"] == FALSE_POSITIVE


def test_repeated_group_children_are_independent():
    region = {
        "object_id": "actions", "object_type": "repeated_component_group",
        "requires_independent_children": True,
        "items": [{"item_id": "item-1", "icon_ids": ["icon-1"], "title_object_id": "title-1", "body_object_id": "body-1", "background_object_id": "bg-1", "divider_object_id": "divider-1"}],
    }
    objects = [{"object_id": value} for value in ("icon-1", "title-1", "body-1", "bg-1", "divider-1")]
    assert validate({"slides": [{"semantic_regions": [region], "shapes": objects}]})["valid"]
    assert any(item["code"] == FLATTENED for item in validate({"slides": [{"semantic_regions": [{**region, "flattened": True}], "shapes": objects}]} )["issues"])
    assert any(item["code"] == TYPE_MISMATCH for item in validate({"slides": [{"semantic_regions": [region], "tables": [{"object_id": "actions", "rows": [["x"]]}], "shapes": objects}]} )["issues"])
    assert any(item["code"] == EDITABILITY_INCOMPLETE for item in validate({"slides": [{"semantic_regions": [region], "shapes": []}]} )["issues"])


def test_unproven_headerless_grid_is_not_promoted_to_native_table():
    result = validate({"slides": [{"tables": [{"object_id": "unknown-grid", "rows": [["项目", "这是一段较长的说明文字"], ["另一项", "另一段较长的解释文字"]]}]}]})
    assert result["valid"] is False
    assert result["regions"][0]["candidate_object_type"] == "repeated_component_group"
    assert result["issues"][0]["code"] == FALSE_POSITIVE
