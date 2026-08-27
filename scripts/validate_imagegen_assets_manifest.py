#!/usr/bin/env python3
"""Validate per-page imagegen provenance required by the image-to-PPTX contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = ("generated_source", "copied_to", "layer", "prompt_file", "backend", "key_color")
LAYERS = {"background", "frame_raw", "icons"}
IMAGEGEN_WORD = re.compile(r"(^|[-_.:/ ])imagegen($|[-_.:/ ])", re.I)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def add(items, code, **extra):
    row = {"severity": "blocker", "code": code}
    row.update(extra)
    items.append(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--report")
    args = parser.parse_args()
    path = Path(args.manifest).resolve()
    issues = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/imagegen-assets-validation/v1",
                  "valid": False, "status": "blocked",
                  "issues": [{"severity": "blocker", "code": "manifest_unreadable",
                              "message": f"{type(exc).__name__}: {exc}"}]}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not isinstance(data, dict):
        add(issues, "manifest_not_object")
        data = {}
    assets = data.get("assets")
    if assets is None:
        assets = []
        for layer in ("background", "frame_raw"):
            if isinstance(data.get(layer), dict):
                assets.append(data[layer] | {"layer": layer})
        if isinstance(data.get("icons"), list):
            assets.extend(x | {"layer": "icons"} for x in data["icons"] if isinstance(x, dict))
    if not isinstance(assets, list) or not assets:
        add(issues, "assets_missing_or_empty")
        assets = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            add(issues, "asset_not_object", asset_index=index)
            continue
        for field in REQUIRED:
            if not isinstance(asset.get(field), str) or not asset[field].strip():
                add(issues, "required_evidence_missing", asset_index=index, field=field)
        layer = asset.get("layer")
        if layer not in LAYERS and not (isinstance(layer, str) and layer.startswith("icons")):
            add(issues, "invalid_layer", asset_index=index, layer=layer)
        backend = asset.get("backend", "")
        if not isinstance(backend, str) or not IMAGEGEN_WORD.search(backend):
            add(issues, "non_imagegen_backend", asset_index=index, backend=backend)
        key_color = asset.get("key_color")
        if not isinstance(key_color, str) or not HEX.fullmatch(key_color):
            add(issues, "invalid_key_color", asset_index=index, key_color=key_color)
        copied = asset.get("copied_to")
        if isinstance(copied, str) and copied:
            copied_path = Path(copied)
            if not copied_path.is_absolute():
                copied_path = path.parent / copied_path
            copied_path = copied_path.resolve()
            if not copied_path.is_file():
                add(issues, "copied_asset_missing", asset_index=index, path=str(copied_path))
            elif path.parent not in copied_path.parents:
                add(issues, "copied_asset_outside_run_root", asset_index=index, path=str(copied_path))
        prompt = asset.get("prompt_file")
        if isinstance(prompt, str) and prompt:
            prompt_path = Path(prompt)
            if not prompt_path.is_absolute():
                prompt_path = path.parent / prompt_path
            prompt_path = prompt_path.resolve()
            if not prompt_path.is_file():
                add(issues, "prompt_file_missing", asset_index=index, path=str(prompt_path))
            elif path.parent not in prompt_path.parents:
                add(issues, "prompt_file_outside_run_root", asset_index=index, path=str(prompt_path))
    result = {
        "schema": "ai-ppt-plus/imagegen-assets-validation/v1",
        "valid": not issues,
        "status": "passed" if not issues else "blocked",
        "manifest": str(path),
        "asset_count": len(assets),
        "issues": issues,
        "human_visual_review_required": True,
    }
    if args.report:
        report = Path(args.report).resolve()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
