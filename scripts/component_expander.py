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
    "components", "speaker_notes", "notes", "icons", "texts",
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
