#!/usr/bin/env python3
"""Validate the last-mile visual-lock evidence contract.

The validator is intentionally evidence-driven: it does not infer visual
correctness from XML object counts. It rejects missing formal text, wrong
container assignment, empty declared containers, unapproved additions,
unresolved icon style locks and typography/region regressions reported by the
render comparison stage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--report", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    path = Path(args.manifest)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"cannot_read_manifest:{type(exc).__name__}:{exc}")
        data = {}

    if data.get("schema") != "ai-ppt-editable/visual-lock/v1":
        fail("schema_mismatch", errors)

    regions = as_list(data.get("regions"))
    if not regions:
        fail("regions_missing", errors)

    ocr_text = "\n".join(str(x) for x in as_list(data.get("render_evidence", {}).get("ocr_text")))
    visible_ids = set(str(x) for x in as_list(data.get("render_evidence", {}).get("visible_regions")))
    empty_containers = set(str(x) for x in as_list(data.get("render_evidence", {}).get("empty_containers")))
    additions = as_list(data.get("added_regions"))
    approved_additions = {
        str(x.get("region_id"))
        for x in additions
        if isinstance(x, dict) and x.get("approved") is True
    }

    for index, region in enumerate(regions):
        if not isinstance(region, dict):
            fail(f"regions[{index}]:not_object", errors)
            continue
        rid = str(region.get("region_id", ""))
        if not rid:
            fail(f"regions[{index}]:region_id_missing", errors)
            continue
        for key in ("source_bbox", "render_bbox", "container_id", "z_order"):
            if key not in region or region[key] in (None, "", []):
                fail(f"{rid}:{key}_missing", errors)
        if region.get("critical") and visible_ids and rid not in visible_ids:
            fail(f"{rid}:critical_region_not_visible", errors)

        role = str(region.get("role", ""))
        required = region.get("required_text", [])
        if isinstance(required, str):
            required = [required]
        for item in as_list(required):
            text = str(item)
            if not text:
                continue
            count = ocr_text.count(text)
            exact_once = bool(region.get("exact_once", True))
            if count == 0:
                fail(f"{rid}:required_text_missing:{text}", errors)
            elif exact_once and count != 1:
                fail(f"{rid}:required_text_count_{count}:{text}", errors)

        container_id = str(region.get("container_id", ""))
        if container_id in empty_containers and required:
            fail(f"{rid}:declared_container_empty:{container_id}", errors)

        if role == "icon":
            style = region.get("style_contract", {})
            provenance = region.get("provenance", {})
            for key in ("style_anchor_id", "silhouette_evidence", "palette",
                        "container_shape", "shadow_policy"):
                if not style.get(key):
                    fail(f"{rid}:icon_style_{key}_missing", errors)
            if provenance.get("provenance_mode") not in ("imagegen", "source_reuse"):
                fail(f"{rid}:icon_provenance_mode_missing", errors)

        typography = region.get("typography_evidence", {})
        for key in ("width_delta_ratio", "height_delta_ratio", "line_count_match"):
            if key not in typography:
                continue
            value = typography[key]
            if key == "line_count_match" and value is False:
                fail(f"{rid}:line_count_mismatch", errors)
            if key != "line_count_match":
                try:
                    if abs(float(value)) > 0.12:
                        fail(f"{rid}:typography_delta_over_12_percent", errors)
                except (TypeError, ValueError):
                    fail(f"{rid}:typography_evidence_invalid:{key}", errors)

    for addition in additions:
        if isinstance(addition, dict) and addition.get("approved") is not True:
            fail(f"unapproved_added_region:{addition.get('region_id', 'unknown')}", errors)
    if not additions:
        warnings.append("added_regions_not_declared")

    scores = data.get("render_evidence", {}).get("region_scores", {})
    for rid, score in scores.items() if isinstance(scores, dict) else []:
        try:
            if float(score) < 95 and any(r.get("region_id") == rid and r.get("critical") for r in regions if isinstance(r, dict)):
                fail(f"{rid}:critical_region_score_below_95", errors)
        except (TypeError, ValueError):
            fail(f"{rid}:region_score_invalid", errors)

    result = {
        "schema": "ai-ppt-editable/visual-lock-report/v1",
        "ok": not errors,
        "strict": bool(args.strict),
        "manifest": str(path.resolve()),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "acceptance": "failed" if errors else "accept-for-human-review",
    }
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "errors": len(errors), "warnings": len(warnings)}))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
