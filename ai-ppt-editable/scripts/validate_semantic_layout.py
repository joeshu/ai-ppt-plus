#!/usr/bin/env python3
"""Classify table-like regions before authoring and fail closed on false tables.

The classifier deliberately separates visual grid evidence from semantic table
evidence.  A repeated icon/title/body list may have lines and aligned columns,
but it is not a native table unless it also represents a field/data matrix.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


FALSE_POSITIVE = "TABLE-SEMANTIC-FALSE-POSITIVE-001"
FLATTENED = "REPEATED-COMPONENT-FLATTENED-001"
EDITABILITY_INCOMPLETE = "COMPONENT-EDITABILITY-INCOMPLETE-001"
TYPE_MISMATCH = "OBJECT-TYPE-REFERENCE-MISMATCH-001"
REPEATED_TYPES = {"repeated_component_group", "information_list", "card_list"}


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
    has_uniform_fields = bool(table.get("field_schema") or table.get("columns_schema") or table.get("data_source") or (has_header and rectangular))
    explicit_data_relation = bool(table.get("data_source") or table.get("data_snapshot") or table.get("data_relation"))
    inferred_data_relation = bool(has_header and rectangular and any(str(value).strip() for row in rows[1:] for value in row))
    has_data_relation = explicit_data_relation or inferred_data_relation
    semantic_type = str(table.get("semantic_type") or "").casefold()
    list_evidence = []
    table_evidence = ["aligned_rows"]
    if table.get("border") or table.get("grid"):
        table_evidence.append("separators_or_border")
    if table.get("column_widths"):
        table_evidence.append("aligned_columns")
    if inferred_header:
        table_evidence.append("declared_table_field_labels")
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
    # A two-column, headerless, source-less region with a real list signal
    # (icons, long explanatory copy, explicit item metadata or paragraph
    # breaks) is a repeated-item candidate.  Short, data-shaped fixtures with
    # no list signal remain available for an explicit table contract; the
    # caller still has to supply field/data evidence before release.
    list_signal = bool(icons or table.get("item_ids") or table.get("list_items") or any(
        "\n" in str(value) or len(str(value).strip()) >= 12
        for row in rows for value in (row if isinstance(row, list) else [])
    ))
    headerless_item_rows = bool(rows) and not has_header and not has_data_relation and column_count == 2 and list_signal
    if headerless_item_rows:
        list_evidence.append("two_column_item_layout")
    is_repeated = semantic_type in REPEATED_TYPES or headerless_item_rows
    if is_repeated:
        candidate = "repeated_component_group"
        decision = "Lines and aligned columns divide repeated information items; they do not define a data matrix."
    else:
        candidate = "native_table"
        decision = "The region has sufficient field/data evidence for a native table."
    return {
        "region_id": str(table.get("object_id") or table.get("name") or "table-region"),
        "visual_structure": "repeated_rows_with_separators" if rows else "unknown",
        "semantic_structure": "icon_title_description_list" if is_repeated else "field_data_matrix",
        "candidate_object_type": candidate,
        "table_evidence": table_evidence,
        "list_evidence": list_evidence,
        "associated_icon_ids": icons,
        "confidence": 0.96 if is_repeated else 0.90,
        "decision_reason": decision,
        "blocking_code": FALSE_POSITIVE if is_repeated else None,
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
