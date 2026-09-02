#!/usr/bin/env python3
"""Normalize deck input and expand reusable component instances."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _die(message: str, code: int = 2):
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


SLIDE_KEYS = {
    "background", "frame", "panels", "shapes", "groups", "tables", "charts",
    "components", "native_panels", "native_tables", "speaker_notes", "notes", "icons", "texts",
}


def _load_deck(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "slides" not in data:
        # Treat the whole object as a single slide; lift deck-level keys out.
        slide = {key: data[key] for key in SLIDE_KEYS if key in data}
        deck = {key: value for key, value in data.items() if key not in SLIDE_KEYS}
        deck["slides"] = [slide]
        data = deck
    data.setdefault("slide_width_in", 13.333)
    data.setdefault("slide_height_in", 7.5)
    data.setdefault("units", "fraction")
    data.setdefault("assets_dir", str(path.parent))
    if data["units"] not in {"fraction", "px"}:
        _die(f"unsupported coordinate units: {data['units']}")
    return data


def _resolve(assets_dir: Path, file: str) -> Path:
    path = Path(file)
    return path if path.is_absolute() else assets_dir / path


def _frac(deck: dict, item: dict, key_xy: str, axis: str, reference: float) -> float:
    """Return a fraction for a coordinate expressed in fraction or pixels."""
    value = item[key_xy]
    if deck["units"] == "px":
        return value / reference
    return value


def _promote_native_structures(deck: dict) -> dict:
    """Promote explicitly native panel/table declarations into native arrays.

    Legacy panel images remain available when their treatment is explicitly
    raster/traceable. A native-required panel is never silently emitted as a
    picture; it becomes a shape or group before authoring.
    """
    for slide_no, slide in enumerate(deck.get("slides", []), 1):
        if not isinstance(slide, dict):
            continue
        native_panels = list(slide.pop("native_panels", []) or [])
        retained_panels = []
        for panel in slide.get("panels", []) or []:
            if not isinstance(panel, dict):
                _die(f"slide {slide_no}: panel must be an object")
            treatment = str(panel.get("treatment", "")).casefold()
            if panel.get("native") is True or panel.get("native_required") is True or treatment in {"native", "native-shape", "native_shape", "native-group", "native_group"}:
                native_panels.append(panel)
            else:
                retained_panels.append(panel)
        if retained_panels:
            slide["panels"] = retained_panels
        else:
            slide.pop("panels", None)
        for raw_panel in native_panels:
            panel = dict(raw_panel)
            treatment = str(panel.get("treatment", "")).casefold()
            if panel.get("file"):
                _die(
                    f"slide {slide_no}: native-required panel {panel.get('object_id') or panel.get('panel_id') or panel.get('name') or 'unnamed'} "
                    "cannot be promoted from a raster file; provide native geometry or mark it raster-only"
                )
            object_id = str(panel.get("object_id") or panel.get("panel_id") or panel.get("name") or f"native-panel-{slide_no:02d}")
            children = panel.get("children")
            is_group = treatment in {"native-group", "native_group"} or isinstance(children, list) and bool(children)
            if is_group:
                group = {
                    key: panel[key]
                    for key in ("object_id", "name", "x", "y", "w", "h", "children_coordinate_space", "alt_text")
                    if key in panel
                }
                group["object_id"] = object_id
                group["children"] = list(children or [])
                slide.setdefault("groups", []).append(group)
            else:
                shape = {
                    key: panel[key]
                    for key in ("object_id", "name", "x", "y", "w", "h", "type", "fill", "gradient", "fill_gradient", "line", "line_width", "opacity", "shadow", "rotation", "alt_text", "allow_bleed")
                    if key in panel
                }
                shape["object_id"] = object_id
                shape.setdefault("type", panel.get("shape_type", "rounded_rect"))
                slide.setdefault("shapes", []).append(shape)
        native_tables = slide.pop("native_tables", []) or []
        if native_tables:
            promoted_tables = []
            for table in native_tables:
                if not isinstance(table, dict):
                    _die(f"slide {slide_no}: native table must be an object")
                if table.get("file"):
                    _die(
                        f"slide {slide_no}: native-required table {table.get('object_id') or table.get('name') or 'unnamed'} "
                        "cannot be promoted from a raster file; provide rows/columns data"
                    )
                promoted_tables.append(dict(table, representation="native"))
            slide.setdefault("tables", []).extend(promoted_tables)
    return deck


def _expand_components(deck: dict) -> dict:
    """Expand validated component instances into the existing object arrays."""
    if not isinstance(deck.get("slides"), list):
        slide = {key: deck[key] for key in SLIDE_KEYS if key in deck}
        deck = dict(deck)
        deck["slides"] = [slide]
    has_instances = any(isinstance(slide, dict) and slide.get("components") for slide in deck.get("slides", []))
    if not has_instances:
        return deck

    source = deck.get("component_library") or deck.get("component_library_path")
    if not source:
        _die("component instances require component_library")
    if isinstance(source, dict):
        library = source
    else:
        path = _resolve(Path(deck["assets_dir"]), str(source))
        if not path.exists():
            _die(f"component library not found: {path}")
        try:
            library = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            _die(f"component library is not valid JSON: {exc}")
    if library.get("schema") != "ai-ppt-plus/component-library/v1":
        _die("component library schema is invalid")

    definitions = {
        item.get("component_id"): item
        for item in library.get("components", [])
        if isinstance(item, dict)
    }
    theme = dict(library.get("tokens", {}))
    theme.update(deck.get("theme", {}) if isinstance(deck.get("theme", {}), dict) else {})
    deck["theme"] = theme
    if isinstance(deck.get("layout_library"), str):
        layout_path = _resolve(Path(deck["assets_dir"]), deck["layout_library"])
        if not layout_path.exists():
            _die(f"layout library not found: {layout_path}")
        deck["layout_library"] = json.loads(layout_path.read_text(encoding="utf-8"))

    target_arrays = {
        "text": "texts", "shape": "shapes", "group": "groups",
        "table": "tables", "chart": "charts", "image": "icons", "vector": "icons",
    }
    for slide_no, slide in enumerate(deck["slides"], 1):
        layout = slide.get("layout_name", theme.get("layout_name", "Blank"))
        layout_names = {layout}
        layout_id = slide.get("layout_id", theme.get("layout_id"))
        layout_library = deck.get("layout_library")
        if layout_id and isinstance(layout_library, dict):
            layout_definition = next(
                (
                    item for item in layout_library.get("layouts", [])
                    if isinstance(item, dict) and item.get("layout_id") == layout_id
                ),
                None,
            )
            if layout_definition and layout_definition.get("pptx_layout_name"):
                layout_names.add(layout_definition["pptx_layout_name"])
        for instance in slide.get("components", []):
            if not isinstance(instance, dict):
                _die(f"slide {slide_no}: component instance must be an object")
            component_id = str(instance.get("component_id", ""))
            definition = definitions.get(component_id)
            if definition is None:
                _die(f"slide {slide_no}: component not found: {component_id}")
            if not layout_names.intersection(definition.get("allowed_layouts", [])):
                _die(f"slide {slide_no}: component {component_id} is not allowed on layout {layout}")
            primitive = dict(definition.get("template", {}))
            primitive.update(definition.get("defaults", {}))
            primitive.update(instance.get("object", {}))
            primitive["object_id"] = str(instance.get("object_id") or primitive.get("object_id") or component_id)
            primitive["component_id"] = component_id
            target = target_arrays[definition["type"]]
            slide.setdefault(target, []).append(primitive)
        slide.pop("components", None)
    return deck


def _choose_slide_layout(prs, slide_spec: dict, theme: dict, deck: dict):
    """Select an existing template layout without inventing a new master."""
    requested = slide_spec.get("layout_name", theme.get("layout_name"))
    layout_id = slide_spec.get("layout_id", theme.get("layout_id"))
    if layout_id:
        library = deck.get("layout_library")
        if isinstance(library, str):
            path = _resolve(Path(deck["assets_dir"]), library)
            if not path.exists():
                _die(f"layout library not found: {path}")
            library = json.loads(path.read_text(encoding="utf-8"))
        layouts = {
            item.get("layout_id"): item
            for item in (library or {}).get("layouts", [])
            if isinstance(item, dict)
        }
        definition = layouts.get(str(layout_id))
        if definition is None:
            _die(f"layout ID not found: {layout_id}")
        requested = definition.get("pptx_layout_name")
    if requested:
        for layout in prs.slide_layouts:
            if layout.name == str(requested):
                return layout
        _die(f"slide layout not found: {requested}")
    if slide_spec.get("layout_index") is not None:
        index = int(slide_spec["layout_index"])
        if index < 0 or index >= len(prs.slide_layouts):
            _die(f"slide layout index out of range: {index}")
        return prs.slide_layouts[index]
    return prs.slide_layouts[6]
