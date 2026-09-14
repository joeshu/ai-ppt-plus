import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.validate_semantic_layout import (
    AMBIGUOUS,
    EDITABILITY_INCOMPLETE,
    FLATTENED,
    FALSE_POSITIVE,
    TYPE_MISMATCH,
    classify_table,
    validate,
)


def test_icon_title_body_region_is_repeated_component_group():
    table = {
        "object_id": "protection-actions-left",
        "semantic_type": "repeated_component_group",
        "rows": [["标题", "说明"], ["标题2", "说明2"]],
        "border": {"all": {"color": "#ddd"}},
        "x": .10, "y": .54, "w": .40, "h": .20,
    }
    slide = {"icons": [{"object_id": "icon-1", "x": .11, "y": .55, "w": .03, "h": .04}]}
    result = classify_table(table, slide)
    assert result["candidate_object_type"] == "repeated_component_group"
    assert result["blocking_code"] == FALSE_POSITIVE
    assert "independent_icons" in result["list_evidence"]


def test_data_matrix_remains_native_table():
    deck = {"slides": [{"tables": [{
        "object_id": "data-table", "headers": ["月份", "金额"],
        "field_schema": ["month", "amount"], "data_source": "source",
        "rows": [["1月", "20"], ["2月", "21"]],
    }], "icons": []}]}
    result = validate(deck)
    assert result["valid"] is True, result
    assert result["regions"][0]["candidate_object_type"] == "native_table"


def test_unproven_headerless_grid_fails_closed_as_item_list():
    result = validate({"slides": [{"tables": [{
        "object_id": "unknown-grid", "rows": [["项目", "这是一段较长的说明文字"], ["另一项", "另一段较长的解释文字"]],
    }], "icons": []}]})
    assert result["valid"] is False
    assert result["regions"][0]["candidate_object_type"] == "repeated_component_group"
    assert result["issues"][0]["code"] == FALSE_POSITIVE


def test_short_headerless_grid_is_ambiguous_instead_of_defaulting_to_table():
    result = validate({"slides": [{"tables": [{
        "object_id": "short-grid", "rows": [["甲", "乙"], ["丙", "丁"]],
    }]}]})
    assert result["valid"] is False
    assert result["regions"][0]["candidate_object_type"] == "ambiguous_table_like"
    assert result["issues"][0]["code"] == AMBIGUOUS


def test_headerless_numeric_grid_requires_explicit_table_semantics():
    unknown = validate({"slides": [{"tables": [{
        "object_id": "monthly-values", "rows": [["1月", "20"], ["2月", "21"]],
    }]}]})
    assert unknown["regions"][0]["candidate_object_type"] == "ambiguous_table_like"
    declared = validate({"slides": [{"tables": [{
        "object_id": "monthly-values", "semantic_type": "native_table",
        "rows": [["1月", "20"], ["2月", "21"]],
    }]}]})
    assert declared["valid"] is True, declared


def test_merged_title_value_matrix_remains_native_table_with_decorative_icon():
    table = {
        "object_id": "points-example", "header_bold": True,
        "rows": [[{"runs": [{"text": "普通智家畅越"}]}, ""], ["提值20元", "20×3=60分"], ["最终积分", "90分"]],
        "merges": [{"start_row": 0, "start_col": 0, "end_row": 0, "end_col": 1}],
        "x": .02, "y": .64, "w": .30, "h": .24,
    }
    slide = {"tables": [table], "icons": [{"object_id": "header-icon", "x": .08, "y": .65, "w": .03, "h": .04}]}
    result = validate({"slides": [slide]})
    assert result["valid"] is True, result
    assert result["regions"][0]["candidate_object_type"] == "native_table"


def test_repeated_group_child_contract_blocks_flattening_and_type_drift():
    region = {
        "object_id": "actions",
        "object_type": "repeated_component_group",
        "requires_independent_children": True,
        "items": [{
            "item_id": "actions-item-1",
            "icon_ids": ["icon-1"],
            "title_object_id": "actions-item-1-title",
            "body_object_id": "actions-item-1-body",
            "background_object_id": "actions-item-1-background",
            "divider_object_id": "actions-item-1-divider",
        }],
    }
    children = [
        {"object_id": "icon-1"}, {"object_id": "actions-item-1-title"},
        {"object_id": "actions-item-1-body"}, {"object_id": "actions-item-1-background"},
        {"object_id": "actions-item-1-divider"},
    ]
    valid = validate({"slides": [{"semantic_regions": [region], "shapes": children, "texts": [], "icons": []}]})
    assert valid["valid"] is True, valid
    flattened = validate({"slides": [{"semantic_regions": [{**region, "flattened": True}], "shapes": children}]})
    assert any(item["code"] == FLATTENED for item in flattened["issues"])
    mismatch = validate({"slides": [{"semantic_regions": [region], "tables": [{"object_id": "actions", "rows": [["x"]]}], "shapes": children}]})
    assert any(item["code"] == TYPE_MISMATCH for item in mismatch["issues"])
    incomplete = validate({"slides": [{"semantic_regions": [region], "shapes": []}]})
    assert any(item["code"] == EDITABILITY_INCOMPLETE for item in incomplete["issues"])
