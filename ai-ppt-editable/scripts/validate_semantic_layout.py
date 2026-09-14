#!/usr/bin/env python3
"""Classify table-like regions before authoring and fail closed on false tables.

The classifier deliberately separates visual grid evidence from semantic table
evidence.  A repeated icon/title/body list may have lines and aligned columns,
but it is not a native table unless it also represents a field/data matrix.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


FALSE_POSITIVE = "TABLE-SEMANTIC-FALSE-POSITIVE-001"
FLATTENED = "REPEATED-COMPONENT-FLATTENED-001"
EDITABILITY_INCOMPLETE = "COMPONENT-EDITABILITY-INCOMPLETE-001"
TYPE_MISMATCH = "OBJECT-TYPE-REFERENCE-MISMATCH-001"
AMBIGUOUS = "TABLE-SEMANTIC-AMBIGUOUS-001"
REPEATED_TYPES = {"repeated_component_group", "information_list", "card_list"}
TABLE_TYPES = {"native_table", "editable_table", "data_table", "field_data_matrix"}


def _associated_icons(table: dict, slide: dict) -> list[str]:
    ids = table.get("associated_icon_ids")
    if isinstance(ids, list):
        return [str(value) for value in ids]
    tx, ty, tw, th = (float(table.get(k, 0)) for k in ("x", "y", "w", "h"))
    found = []
    for item in slide.get("icons", []) or []:
        if not isinstance(item, dict):
            continue
        ix, iy, iw, ih = (float(item.get(k, 0)) for k in ("x", "y", "w", "h"))
        if max(tx, ix) < min(tx + tw, ix + iw) and max(ty, iy) < min(ty + th, iy + ih):
            found.append(str(item.get("object_id") or item.get("name") or "icon"))
    return found


def _cell_text(value) -> str:
    if isinstance(value, dict):
        if value.get("text") is not None:
            return str(value.get("text") or "").strip()
        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(str(run.get("text") or "") for run in runs if isinstance(run, dict)).strip()
        return ""
    return str(value or "").strip()


def _numeric_or_formula(value: str) -> bool:
    compact = re.sub(r"\s+", "", value)
    return bool(compact) and bool(re.fullmatch(r"[\d.,%￥¥$€£+\-×xX*/=:（）()年月日张分元户]+", compact))


def classify_table(table: dict, slide: dict) -> dict:
    rows = table.get("rows") or []
    first_row = rows[0] if rows else []
    column_count = max((len(row) for row in rows if isinstance(row, list)), default=0)
    rectangular = bool(rows) and column_count > 0 and all(isinstance(row, list) and len(row) == column_count for row in rows)
    icons = _associated_icons(table, slide)
    explicit_header = bool(table.get("headers") or table.get("header_row") is True or table.get("header_bold") is True)
    first_row_is_field_labels = bool(first_row) and all(
        not isinstance(value, dict) and "\n" not in str(value) and 0 < len(str(value).strip()) <= 8
        for value in first_row
    )
    inferred_header = bool(
        rectangular and len(rows) >= 2 and not icons and first_row_is_field_labels and
        (table.get("native_required") or table.get("merges") or table.get("rich_text_required"))
    )
    has_header = explicit_header or inferred_header
    schema_evidence = bool(table.get("field_schema") or table.get("columns_schema"))
    source_evidence = bool(table.get("data_source") or table.get("data_snapshot"))
    operation_evidence = bool(table.get("requires_cell_editing") or table.get("requires_row_column_operations") or table.get("grid_data_required"))
    has_uniform_fields = bool(schema_evidence or (has_header and rectangular))
    explicit_data_relation = bool(table.get("data_source") or table.get("data_snapshot") or table.get("data_relation"))
    inferred_data_relation = bool(has_header and rectangular and any(str(value).strip() for row in rows[1:] for value in row))
    has_data_relation = explicit_data_relation or inferred_data_relation
    semantic_type = str(table.get("semantic_type") or "").casefold()
    list_evidence = []
    table_evidence = ["aligned_rows"] if rectangular else []
    if table.get("border") or table.get("grid"):
        table_evidence.append("separators_or_border")
    if table.get("column_widths"):
        table_evidence.append("aligned_columns")
    if inferred_header:
        table_evidence.append("declared_table_field_labels")
    if explicit_header:
        table_evidence.append("explicit_header")
    if schema_evidence:
        table_evidence.append("field_schema")
    if source_evidence:
        table_evidence.append("data_source")
    if explicit_data_relation:
        table_evidence.append("data_relation")
    if operation_evidence:
        table_evidence.append("row_column_editing")
    if not has_header:
        list_evidence.append("no_header")
    if not has_uniform_fields:
        list_evidence.append("no_uniform_fields")
    if not has_data_relation:
        list_evidence.append("no_data_relation")
    if icons:
        list_evidence.append("independent_icons")
    if semantic_type in {"repeated_component_group", "information_list", "card_list"}:
        list_evidence.append("declared_repeated_component")
    if any("\n" in str(row[0]) for row in rows if row):
        list_evidence.append("heterogeneous_descriptions")
    body_rows = rows[1:] if has_header else rows
    two_column_rows = [row for row in body_rows if isinstance(row, list) and len(row) == 2]
    label_description = False
    if not has_header and len(two_column_rows) >= 2:
        left = [_cell_text(row[0]) for row in two_column_rows]
        right = [_cell_text(row[1]) for row in two_column_rows]
        left_avg = sum(len(value) for value in left) / max(1, len(left))
        right_avg = sum(len(value) for value in right) / max(1, len(right))
        label_description = bool(
            left_avg <= 10
            and right_avg >= max(4, left_avg * 2)
            and any(not _numeric_or_formula(value) for value in right if value)
        )
    paragraph_signal = any("\n" in _cell_text(value) for row in rows if isinstance(row, list) for value in row)
    item_metadata = bool(table.get("item_ids") or table.get("list_items"))
    headerless_item_rows = bool(
        rows and not has_header and not has_data_relation and column_count == 2
        and (icons or item_metadata or label_description or paragraph_signal)
    )
    if headerless_item_rows:
        list_evidence.append("two_column_item_layout")
    if label_description:
        list_evidence.append("short_label_long_description")
    if item_metadata:
        list_evidence.append("declared_item_metadata")
    if paragraph_signal:
        list_evidence.append("paragraph_content")

    explicit_repeated = semantic_type in REPEATED_TYPES
    # Geometric overlap alone does not make an icon an item marker: decorative
    # header icons commonly sit inside a real table's bounding box.  Require
    # explicit list semantics, item metadata, or a headerless item-row pattern.
    strong_list = bool(explicit_repeated or item_metadata or headerless_item_rows)
    has_body_values = bool(body_rows and any(_cell_text(value) for row in body_rows if isinstance(row, list) for value in row))
    strong_table = bool(
        rectangular and has_body_values and (
            semantic_type in TABLE_TYPES
            or (has_header and has_data_relation)
            or (explicit_data_relation and (schema_evidence or operation_evidence or explicit_header))
            or (schema_evidence and operation_evidence)
        )
    )

    if explicit_repeated or (strong_list and not strong_table):
        candidate = "repeated_component_group"
        semantic_structure = "icon_title_description_list"
        confidence = 0.96 if explicit_repeated or icons else 0.90
        decision = "Lines and aligned columns divide repeated information items; they do not define a data matrix."
        blocking_code = FALSE_POSITIVE
    elif strong_table and not strong_list:
        candidate = "native_table"
        semantic_structure = "field_data_matrix"
        confidence = 0.95
        decision = "The region has sufficient field/data evidence for a native table."
        blocking_code = None
    else:
        candidate = "ambiguous_table_like"
        semantic_structure = "unresolved_table_or_list"
        confidence = 0.50
        decision = "Visual alignment alone does not prove either a data table or a repeated information list."
        blocking_code = AMBIGUOUS
    return {
        "region_id": str(table.get("object_id") or table.get("name") or "table-region"),
        "visual_structure": "repeated_rows_with_separators" if rows else "unknown",
        "semantic_structure": semantic_structure,
        "candidate_object_type": candidate,
        "table_evidence": table_evidence,
        "list_evidence": list_evidence,
        "associated_icon_ids": icons,
        "confidence": confidence,
        "decision_reason": decision,
        "blocking_code": blocking_code,
    }


def validate(deck: dict) -> dict:
    regions = []
    issues = []
    for slide_no, slide in enumerate(deck.get("slides", []), 1):
        for table in slide.get("tables", []) or []:
            result = classify_table(table, slide)
            result["slide"] = slide_no
            regions.append(result)
            if result["candidate_object_type"] == "repeated_component_group" and table.get("representation", "native") == "native":
                issues.append({"severity": "blocker", "code": FALSE_POSITIVE, "slide": slide_no, "object_id": result["region_id"]})
            elif result["candidate_object_type"] == "ambiguous_table_like":
                issues.append({"severity": "blocker", "code": AMBIGUOUS, "slide": slide_no, "object_id": result["region_id"]})
        # A converted repeated group carries an explicit child contract.  Keep
        # this check independent from the table classifier so a later authoring
        # change cannot silently flatten the icon/title/body children.
        object_ids = set()
        for key in ("icons", "images", "texts", "shapes", "groups"):
            for item in slide.get(key, []) or []:
                if isinstance(item, dict):
                    value = item.get("object_id") or item.get("name")
                    if value:
                        object_ids.add(str(value))
        table_ids = {str(table.get("object_id") or table.get("name")) for table in slide.get("tables", []) or []}
        for declared in slide.get("semantic_regions", []) or []:
            if not isinstance(declared, dict):
                continue
            region_id = str(declared.get("object_id") or declared.get("region_id") or declared.get("name") or "semantic-region")
            object_type = str(declared.get("object_type") or declared.get("candidate_object_type") or "").casefold()
            if object_type not in REPEATED_TYPES:
                continue
            icon_ids = []
            for item in declared.get("items") or []:
                if isinstance(item, dict):
                    icon_ids.extend(str(value) for value in item.get("icon_ids") or [] if value)
            regions.append({
                "region_id": region_id,
                "slide": slide_no,
                "visual_structure": declared.get("visual_structure", "repeated_rows_with_separators"),
                "semantic_structure": declared.get("semantic_structure", "icon_title_description_list"),
                "candidate_object_type": "repeated_component_group",
                "table_evidence": list(declared.get("table_evidence") or ["aligned_rows", "separators_or_border"]),
                "list_evidence": list(declared.get("list_evidence") or ["no_header", "no_uniform_fields", "independent_icons"]),
                "associated_icon_ids": sorted(set(icon_ids)),
                "confidence": float(declared.get("confidence", 0.96)),
                "decision_reason": declared.get("decision_reason", "Lines divide repeated information items; they do not define a data matrix."),
                "blocking_code": None,
            })
            if region_id in table_ids:
                issues.append({"severity": "blocker", "code": TYPE_MISMATCH, "slide": slide_no, "object_id": region_id, "expected": "repeated_component_group", "actual": "native_table"})
            representation = str(declared.get("representation") or "").casefold()
            if declared.get("flattened") is True or representation in {"picture", "raster", "single_textbox", "single-textbox", "bitmap"}:
                issues.append({"severity": "blocker", "code": FLATTENED, "slide": slide_no, "object_id": region_id})
            items = declared.get("items")
            if declared.get("requires_independent_children") or items is not None:
                if not isinstance(items, list) or not items:
                    issues.append({"severity": "blocker", "code": EDITABILITY_INCOMPLETE, "slide": slide_no, "object_id": region_id, "missing": "items"})
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        issues.append({"severity": "blocker", "code": EDITABILITY_INCOMPLETE, "slide": slide_no, "object_id": region_id, "missing": "item_record"})
                        continue
                    required = [item.get("title_object_id"), item.get("body_object_id"), item.get("background_object_id"), item.get("divider_object_id")]
                    required.extend(item.get("icon_ids") or [])
                    missing = [str(value) for value in required if value and str(value) not in object_ids]
                    if missing:
                        issues.append({"severity": "blocker", "code": EDITABILITY_INCOMPLETE, "slide": slide_no, "object_id": region_id, "item_id": item.get("item_id"), "missing": missing})
    return {
        "schema": "ai-ppt-plus/semantic-layout-classification/v1",
        "valid": not issues,
        "regions": regions,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = validate(json.loads(Path(args.deck).read_text(encoding="utf-8")))
    if args.report:
        Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
