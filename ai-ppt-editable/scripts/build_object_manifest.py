#!/usr/bin/env python3
"""Build a semantic object manifest from layout and asset manifests.

Geometry remains in layout.json; this command only creates the canonical
identity/provenance/editability inventory consumed by the release gates. File
references are normalized relative to the output manifest when the referenced
asset lives below the project bundle. That keeps semantic audits working when
``layout.json`` uses a separate ``assets_dir``.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from atomic_output import atomic_write_json
from text_model import normalize_text_spec


def read(path: str | None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _asset_path(layout: dict, value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    candidate = Path(value.split("#", 1)[0].strip())
    if not str(candidate):
        return None
    if not candidate.is_absolute():
        candidate = Path(layout.get("assets_dir") or ".") / candidate
    return candidate.resolve()


def _source_fields(layout: dict, value: object) -> dict:
    """Return reproducible source evidence when a referenced file is present."""
    path = _asset_path(layout, value)
    if path is None or not path.is_file():
        return {}
    return {"source_sha256": _file_sha256(path)}


def _source_reference(layout: dict, value: object, output_base: Path | None) -> str:
    """Return an audit-resolvable path without losing the raw provenance.

    ``assets_dir`` is the authoring lookup root, while semantic audits resolve
    object-manifest paths from the manifest directory.  A path that is valid
    for composition can therefore be invisible to the audit.  Normalize only
    when the file exists and an output base is known; otherwise preserve the
    legacy value so incomplete exploratory layouts remain inspectable.
    """
    raw = str(value) if value is not None else ""
    resolved = _asset_path(layout, value)
    if output_base is None or resolved is None or not resolved.is_file():
        return raw
    try:
        return resolved.relative_to(output_base.resolve()).as_posix()
    except ValueError:
        # A source outside the project bundle cannot be made portable without
        # copying it. Keep an absolute evidence path so the failure is
        # explicit rather than silently pointing at the wrong directory.
        return str(resolved)


def _data_source_fields(layout: dict, value: object) -> dict:
    path = _asset_path(layout, value)
    if path is None or not path.is_file():
        return {}
    return {"data_source_path": str(path), "data_source_sha256": _file_sha256(path)}


def _rectangular_rows(rows: object, columns: int | None = None) -> list[list[object]] | None:
    if not isinstance(rows, list) or not rows or any(not isinstance(row, list) for row in rows):
        return None
    width = columns or max((len(row) for row in rows), default=0)
    if width <= 0:
        return None
    return [[row[index] if index < len(row) else "" for index in range(width)] for row in rows]


def _table_cell_value(value: object) -> object:
    """Normalize a rich-text cell to its visible text for data snapshots."""
    if isinstance(value, dict):
        runs = value.get("runs")
        if isinstance(runs, list):
            return "".join(str(run.get("text", "")) for run in runs if isinstance(run, dict))
        if "text" in value:
            return str(value.get("text") or "")
    return value


def _table_snapshot(spec: dict) -> dict | None:
    rows = _rectangular_rows(spec.get("rows"), int(spec["columns"]) if spec.get("columns") is not None else None)
    if rows is None:
        return None
    # A merged cell has one authoritative top-left value.  Blank the covered
    # cells in the manifest so the expected snapshot matches PowerPoint's
    # native table model after the merge is applied.
    for merge in spec.get("merges", []):
        if not isinstance(merge, list) or len(merge) != 4:
            continue
        r1, c1, r2, c2 = [int(value) for value in merge]
        for row in range(max(0, r1), min(len(rows), r2 + 1)):
            for column in range(max(0, c1), min(len(rows[row]), c2 + 1)):
                if row != r1 or column != c1:
                    rows[row][column] = ""
    return {"kind": "table", "values": [[_table_cell_value(value) for value in row] for row in rows], "rows": len(rows), "columns": len(rows[0])}


def _chart_snapshot(spec: dict) -> dict | None:
    categories = spec.get("categories")
    series = spec.get("series")
    if not isinstance(categories, list) or not categories or not isinstance(series, list) or not series:
        return None
    values = []
    for item in series:
        if not isinstance(item, dict) or not isinstance(item.get("values"), list):
            return None
        if len(item["values"]) != len(categories):
            return None
        values.append({
            "name": str(item.get("name", "Series")),
            "values": list(item["values"]),
        })
    return {"kind": "category_chart", "categories": list(categories), "series": values}


def obj(object_id, role, object_type, level, *, required=True, review=False, **extra):
    base = {
        "object_id": object_id,
        "role": role,
        "object_type": object_type,
        "editability_level": level,
        "required_for_delivery": required,
        "human_review_required": review,
    }
    base.update(extra)
    return base


def build(
    layout: dict,
    panel_manifest: dict | None,
    imagegen: dict | None,
    *,
    output_base: Path | None = None,
) -> dict:
    has_components = bool(layout.get("components")) or any(isinstance(slide, dict) and slide.get("components") for slide in layout.get("slides", []))
    if has_components:
        from compose_pptx import _expand_components
        layout = _expand_components(copy.deepcopy(layout))
    slides = layout.get("slides")
    if not isinstance(slides, list):
        slides = [{k: layout[k] for k in ("background", "frame", "panels", "shapes", "groups", "tables", "charts", "speaker_notes", "notes", "icons", "texts") if k in layout}]
    panels_by_file = {}
    for panel in (panel_manifest or {}).get("panels", []):
        if isinstance(panel, dict) and panel.get("file"):
            key = str(panel["file"])
            panels_by_file[key] = panel
            panels_by_file[Path(key).name] = panel
    output = []
    for slide_no, slide in enumerate(slides, 1):
        objects = []
        bg = slide.get("background")
        if bg:
            objects.append(obj(slide.get("background_object_id", "background"), "background", "independent_image", "L2", review=True, replaceable=True, contains_formal_content=False, provenance=str(bg), source_path=_source_reference(layout, bg, output_base), **_source_fields(layout, bg)))
        frame = slide.get("frame")
        if frame:
            objects.append(obj(slide.get("frame_object_id", "frame"), "frame", "traceable_static_graphic", "L3", review=True, reduced_editability_accepted=True, contains_formal_content=False, provenance=str(frame), source_path=_source_reference(layout, frame, output_base), **_source_fields(layout, frame)))
        for i, panel in enumerate(slide.get("panels", []), 1):
            pid = str(panel.get("object_id") or panel.get("panel_id") or f"panel-{i:02d}")
            layout_file = str(panel.get("file", ""))
            evidence = panels_by_file.get(layout_file) or panels_by_file.get(Path(layout_file).name) or {}
            baked = bool(panel.get("formal_text_baked_in", evidence.get("formal_text_baked_in", False)))
            objects.append(obj(pid, "semantic-panel", "traceable_static_graphic", "L3", review=True, reduced_editability_accepted=True, independent=True, contains_formal_content=baked, provenance=str(evidence.get("source") or panel.get("file")), source_path=_source_reference(layout, layout_file, output_base), source_bbox=evidence.get("source_bbox"), **_source_fields(layout, layout_file)))
        for i, shape in enumerate(slide.get("shapes", []), 1):
            sid = str(shape.get("object_id") or shape.get("name") or f"shape-{i:02d}")
            role = str(shape.get("role") or shape.get("semantic_role") or ("semantic-panel" if shape.get("native_required") else "native-shape"))
            objects.append(obj(
                sid,
                role,
                "native_shape",
                "L1",
                review=False,
                contains_formal_content=False,
                native_required=bool(shape.get("native_required") or role in {"semantic-panel", "panel", "card", "framework"}),
                component_ref=shape.get("component_id"),
            ))
        for i, group in enumerate(slide.get("groups", []), 1):
            gid = str(group.get("object_id") or group.get("name") or f"group-{i:02d}")
            children = [child.get("object_id") or child.get("name") for child in group.get("children", []) if isinstance(child, dict)]
            group_role = str(group.get("role") or group.get("semantic_role") or ("semantic-panel" if group.get("native_required") else "component-group"))
            objects.append(obj(
                gid,
                group_role,
                "native_group",
                "L1",
                review=False,
                contains_formal_content=False,
                native_required=bool(group.get("native_required") or group_role in {"semantic-panel", "panel", "card", "framework"}),
                editable_components=True,
                children=[child for child in children if child],
                component_ref=group.get("component_id"),
            ))
            # Group children are real editable objects too.  Keeping them in
            # the manifest makes --require-complete-manifest meaningful while
            # the parent group still records the movable semantic container.
            for child_index, child in enumerate(group.get("children", []), 1):
                if not isinstance(child, dict):
                    continue
                child_id = str(child.get("object_id") or child.get("name") or f"{gid}-child-{child_index:02d}")
                child_role = str(child.get("role") or child.get("semantic_role") or "native-shape")
                objects.append(obj(
                    child_id,
                    child_role,
                    "native_shape",
                    "L1",
                    review=False,
                    contains_formal_content=False,
                    native_required=bool(child.get("native_required") or child_role in {"semantic-panel", "panel", "card", "framework"}),
                    parent_group=gid,
                ))
        for i, table in enumerate(slide.get("tables", []), 1):
            tid = str(table.get("object_id") or table.get("name") or f"table-{i:02d}")
            snapshot = _table_snapshot(table)
            source_fields = _data_source_fields(layout, table.get("data_source"))
            if snapshot is not None and "data_source_sha256" not in source_fields:
                source_fields["data_source_sha256"] = _json_sha256(snapshot)
            objects.append(obj(
                tid,
                "data-table",
                "editable_table",
                "L1",
                review=True,
                contains_formal_content=True,
                data_source=table.get("data_source"),
                data_snapshot=snapshot,
                merges=[list(merge) for merge in table.get("merges", []) if isinstance(merge, list) and len(merge) == 4],
                rich_text_required=bool(table.get("rich_text_required")),
                **source_fields,
                component_ref=table.get("component_id"),
            ))
        for i, chart in enumerate(slide.get("charts", []), 1):
            cid = str(chart.get("object_id") or chart.get("name") or f"chart-{i:02d}")
            snapshot = _chart_snapshot(chart)
            source_fields = _data_source_fields(layout, chart.get("data_source"))
            if snapshot is not None and "data_source_sha256" not in source_fields:
                source_fields["data_source_sha256"] = _json_sha256(snapshot)
            objects.append(obj(cid, "data-chart", "editable_chart", "L1", review=True, contains_formal_content=True, data_source=chart.get("data_source"), data_snapshot=snapshot, **source_fields, chart_type=chart.get("type", "column"), component_ref=chart.get("component_id")))
        for i, icon in enumerate(slide.get("icons", []), 1):
            iid = str(icon.get("object_id") or icon.get("name") or f"icon-{i:02d}")
            role = str(icon.get("role") or "decorative-art")
            icon_file = str(icon.get("file", ""))
            is_svg = Path(icon_file).suffix.casefold() == ".svg"
            vector_editable = bool(icon.get("vector_editable", False))
            brand = role in {"brand_lockup", "logo", "brand-logo"} or icon.get("asset_policy") == "brand_lockup"
            objects.append(obj(iid, role, "editable_vector" if vector_editable else "extracted_icon", "L1" if vector_editable else "L2", review=True, replaceable=True, vector_asset=is_svg, contains_formal_content=False, source_path=_source_reference(layout, icon_file, output_base), provenance=icon_file, asset_policy="brand_lockup" if brand else icon.get("asset_policy", "normal_asset"), brand_asset_contract={"whole_asset": True, "allow_crop": False} if brand else None, **_source_fields(layout, icon_file), component_ref=icon.get("component_id")))
        for i, text in enumerate(slide.get("texts", []), 1):
            tid = str(text.get("object_id") or text.get("name") or f"text-{i:02d}")
            objects.append(obj(
                tid, "formal-text", "editable_text", "L1", review=False,
                contains_formal_content=False,
                provenance=str(text.get("source_ref") or "layout.json"), component_ref=text.get("component_id"),
                text_spec=normalize_text_spec(
                    text, slide_no, i,
                    units=str(layout.get("units", "fraction")),
                    ref_width=layout.get("ref_width"),
                    ref_height=layout.get("ref_height"),
                ),
            ))
        output.append({"slide_no": slide_no, "objects": objects})
    refs = [item.get("component_ref") for slide in output for item in slide["objects"] if item.get("component_ref")]
    counts = Counter(refs)
    return {"schema": "ai-ppt-plus/slide-object-manifest/v1", "project_id": layout.get("project_id", ""), "layout_ref": "layout.json", "slides": output, "component_usage": {"instances": len(refs), "distinct_components": len(counts), "by_component": dict(sorted(counts.items())), "reused_component_types": sum(1 for count in counts.values() if count > 1)}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("layout")
    ap.add_argument("--panel-manifest")
    ap.add_argument("--imagegen-manifest")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    out = Path(args.output)
    data = build(
        read(args.layout),
        read(args.panel_manifest) if args.panel_manifest else None,
        read(args.imagegen_manifest) if args.imagegen_manifest else None,
        output_base=out.resolve().parent,
    )
    atomic_write_json(out, data)
    print(json.dumps({"valid": True, "slides": len(data["slides"]), "objects": sum(len(s["objects"]) for s in data["slides"]), "output": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
