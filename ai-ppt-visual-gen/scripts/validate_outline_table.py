#!/usr/bin/env python3
"""Validate the user-reviewable PPT thought table.

The compact table keeps the owner's four working columns visible:
``slide_no``, ``title_core_idea``, ``page_outline`` and ``owner_notes``.
The validator also accepts the canonical ai-ppt-plus outline columns and
normalizes common Chinese headings.  It never rewrites the user's notes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/outline-table-validation/v1"
STATES = {"draft", "needs_user", "approved", "blocked", "superseded"}
FACT_RE = re.compile(r"(?:\d|%|同比|环比|增长|下降|金额|收入|用户|客户|成本|预算|目标|日期|季度|年度)")


def normalize_header(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s\-_/\\:：|（）()·•]+", "", text)


ALIASES = {
    "slide_no": {"slideno", "pageno", "页码", "页号", "页数", "page"},
    "title_core_idea": {
        "titlecoreidea", "标题核心思想", "标题核心", "标题/核心思想", "标题核心结论",
        "核心思想", "核心结论", "核心消息",
    },
    "page_outline": {
        "pageoutline", "页面大纲", "页面内容", "本页大纲", "页面要点", "大纲",
        "bodycontent", "正文内容", "content",
    },
    "owner_notes": {
        "ownernotes", "我的修改意见", "修改意见", "我的意见", "批注", "用户批注",
        "备注", "notes", "comments",
    },
    "section": {"section", "章节", "部分", "所属章节"},
    "purpose": {"purpose", "页面目的", "本页目的"},
    "data_sources": {"datasources", "数据来源", "来源", "引用来源", "source"},
    "visual_type": {"visualtype", "页面类型", "视觉类型", "表达类型"},
    "audience_takeaway": {"audiencetakeaway", "观众带走什么", "听众收获", "受众结论"},
    "status": {"status", "状态", "审批状态"},
    "revision_reason": {"revisionreason", "修订原因", "修改原因"},
}

# The canonical outline contract uses separate ``title`` and ``core_message``
# fields.  Keep those distinct while still accepting the compact user-facing
# ``标题 / 核心思想`` column.
TITLE_ALIASES = {"title", "标题"}
CORE_MESSAGE_ALIASES = {"coremessage", "核心思想", "核心结论", "核心消息"}
COMPACT_TITLE_CORE_ALIASES = {
    "titlecoreidea", "标题核心思想", "标题核心", "标题/核心思想", "标题核心结论",
}


def text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def read_rows(path: Path) -> tuple[list[str], list[dict[str, object]]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
            return headers, [dict(row) for row in reader if any(text(value) for value in row.values())]
    if path.suffix.lower() != ".xlsx":
        raise ValueError("only CSV and XLSX are supported")
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError(f"openpyxl unavailable for XLSX outline: {exc}") from exc
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not values:
        return [], []
    header_row_index, header_row = next(
        ((index, row) for index, row in enumerate(values) if any(value not in (None, "") for value in row)),
        (0, ()),
    )
    headers = [str(value or "").strip() for value in header_row]
    header_index = {index: header for index, header in enumerate(headers) if header}
    rows = []
    for raw in values[header_row_index + 1:]:
        row = {header: raw[index] if index < len(raw) else None for index, header in header_index.items()}
        if any(text(value) for value in row.values()):
            rows.append(row)
    return headers, rows


def canonical_header_map(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalized_aliases = {key: {normalize_header(alias) for alias in values} for key, values in ALIASES.items()}
    for header in headers:
        normalized = normalize_header(header)
        if normalized in {normalize_header(alias) for alias in COMPACT_TITLE_CORE_ALIASES}:
            mapping.setdefault("title_core_idea", header)
            continue
        if normalized in {normalize_header(alias) for alias in TITLE_ALIASES}:
            mapping.setdefault("title", header)
            continue
        if normalized in {normalize_header(alias) for alias in CORE_MESSAGE_ALIASES}:
            mapping.setdefault("core_message", header)
            continue
        for field, aliases in normalized_aliases.items():
            if normalized in aliases and field not in mapping:
                mapping[field] = header
                break
    # A canonical title/core-message pair is accepted as the compact required
    # column and combined without losing either part of the source table.
    if "title_core_idea" not in mapping and ("title" in mapping or "core_message" in mapping):
        mapping["title_core_idea"] = mapping.get("title") or mapping.get("core_message")  # type: ignore[assignment]
    return mapping


def canonical_rows(headers: list[str], rows: list[dict[str, object]]) -> list[dict[str, str]]:
    mapping = canonical_header_map(headers)
    result = []
    for row in rows:
        value = {field: text(row.get(header)) for field, header in mapping.items()}
        # The canonical ai-ppt-plus table has separate title/core_message and
        # body_content fields.  Preserve it as the compact four-column view.
        if "title" in mapping or "core_message" in mapping:
            title = text(row.get(mapping.get("title", "")))
            core = text(row.get(mapping.get("core_message", "")))
            value["title_core_idea"] = "｜".join(part for part in (title, core) if part)
        if not value.get("page_outline"):
            value["page_outline"] = text(row.get(mapping.get("body_content", "")))
        value.setdefault("owner_notes", text(row.get(mapping.get("owner_notes", ""))))
        value.setdefault("status", text(row.get(mapping.get("status", ""))) or "draft")
        result.append(value)
    return result


def validate_rows(headers: list[str], rows: list[dict[str, str]], *, require_approved: bool, max_outline_chars: int) -> dict:
    issues: list[dict] = []
    mapping = canonical_header_map(headers)
    required_columns = ("slide_no", "title_core_idea", "page_outline", "owner_notes")
    for field in required_columns:
        if field not in mapping:
            issues.append({"severity": "blocker", "code": "missing_column", "field": field})
    if require_approved and "status" not in mapping:
        issues.append({"severity": "blocker", "code": "approval_status_column_missing", "field": "status"})

    numbers: list[int] = []
    normalized = []
    if not rows:
        issues.append({"severity": "blocker", "code": "empty_table"})
    for row_index, row in enumerate(rows, start=2):
        normalized_row = {
            "row": row_index,
            "slide_no": text(row.get("slide_no")),
            "title_core_idea": text(row.get("title_core_idea")),
            "page_outline": text(row.get("page_outline")),
            "owner_notes": text(row.get("owner_notes")),
            "section": text(row.get("section")),
            "purpose": text(row.get("purpose")),
            "data_sources": text(row.get("data_sources")),
            "visual_type": text(row.get("visual_type")),
            "audience_takeaway": text(row.get("audience_takeaway")),
            "status": text(row.get("status")) or "draft",
            "revision_reason": text(row.get("revision_reason")),
        }
        normalized.append(normalized_row)
        try:
            slide_no = int(normalized_row["slide_no"])
            if slide_no < 1:
                raise ValueError
            numbers.append(slide_no)
        except (TypeError, ValueError):
            issues.append({"severity": "blocker", "code": "invalid_slide_no", "row": row_index, "value": normalized_row["slide_no"]})
        for field in ("title_core_idea", "page_outline"):
            if not normalized_row[field]:
                issues.append({"severity": "blocker", "code": "empty_required", "row": row_index, "field": field})
        if len(normalized_row["page_outline"]) > max_outline_chars:
            issues.append({"severity": "major", "code": "page_outline_too_long", "row": row_index, "chars": len(normalized_row["page_outline"]), "maximum": max_outline_chars})
        status = normalized_row["status"]
        if status not in STATES:
            issues.append({"severity": "blocker", "code": "invalid_status", "row": row_index, "value": status})
        if (status == "approved" or require_approved) and FACT_RE.search(normalized_row["page_outline"]) and not normalized_row["data_sources"]:
            issues.append({"severity": "critical", "code": "fact_or_approval_without_source", "row": row_index})
        if require_approved and status != "approved":
            issues.append({"severity": "blocker", "code": "narrative_not_approved", "row": row_index, "status": status})

    if numbers:
        if len(numbers) != len(set(numbers)):
            issues.append({"severity": "blocker", "code": "duplicate_slide_no", "observed": numbers})
        if sorted(numbers) != list(range(1, max(numbers) + 1)):
            issues.append({"severity": "blocker", "code": "non_contiguous_slide_no", "observed": sorted(numbers)})
    blockers = [item for item in issues if item["severity"] in {"blocker", "critical"}]
    return {
        "schema": SCHEMA,
        "valid": not blockers,
        "technical_valid": not blockers,
        "status": "passed" if not blockers else "blocked",
        "require_approved": require_approved,
        "headers": headers,
        "canonical_columns": sorted(mapping),
        "rows": normalized,
        "row_count": len(normalized),
        "issues": issues,
    }


def validate_file(path: Path, *, require_approved: bool = False, max_outline_chars: int = 1800) -> dict:
    try:
        headers, rows = read_rows(path)
        result = validate_rows(headers, canonical_rows(headers, rows), require_approved=require_approved, max_outline_chars=max_outline_chars)
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "valid": False,
            "technical_valid": False,
            "status": "blocked",
            "require_approved": require_approved,
            "issues": [{"severity": "blocker", "code": "outline_read_failed", "message": f"{type(exc).__name__}: {exc}"}],
        }
    result["path"] = str(path.resolve())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outline", help="PPT thought table in CSV or XLSX format")
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--max-outline-chars", type=int, default=1800)
    parser.add_argument("--normalized-output", help="write normalized rows as JSON")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.outline).resolve()
    result = validate_file(path, require_approved=args.require_approved, max_outline_chars=args.max_outline_chars)
    if args.normalized_output:
        atomic_write_json(Path(args.normalized_output).resolve(), result)
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
