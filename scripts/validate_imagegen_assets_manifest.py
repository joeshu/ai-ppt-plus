#!/usr/bin/env python3
"""Validate per-page visual-asset provenance.

The historical filename is retained for compatibility. Assets may use the
imagegen B4 route, or a deterministic ``source_reuse`` route when authoritative
source pixels are already available and no reconstruction is needed. Both
routes still require an independent delivered asset, hashes and human visual
review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from atomic_output import atomic_write_json


REQUIRED = ("generated_source", "copied_to", "layer", "prompt_file", "backend", "key_color")
SOURCE_REUSE_REQUIRED = ("source_ref", "source_bbox", "source_sha256", "copied_to", "layer", "extraction_method")
LAYERS = {"background", "frame_raw", "icons"}
IMAGEGEN_WORD = re.compile(r"(^|[-_.:/ ])imagegen($|[-_.:/ ])", re.I)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROVENANCE_MODES = {"imagegen", "source_reuse"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add(items, code, **extra):
    row = {"severity": "blocker", "code": code}
    row.update(extra)
    items.append(row)


def valid_bbox(value) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    try:
        numbers = [float(item) for item in value]
    except (TypeError, ValueError):
        return False
    return all(number >= 0 for number in numbers) and numbers[2] > 0 and numbers[3] > 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--require-hashes", action="store_true", help="require a current SHA-256 for every copied asset")
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
        if args.report:
            report = Path(args.report).resolve()
            atomic_write_json(report.resolve(), result)
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
    hashed_asset_count = 0
    provenance_modes: dict[str, int] = {}
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            add(issues, "asset_not_object", asset_index=index)
            continue
        mode = asset.get("provenance_mode") or data.get("provenance_mode") or "imagegen"
        if mode not in PROVENANCE_MODES:
            add(issues, "invalid_provenance_mode", asset_index=index, provenance_mode=mode)
            mode = "imagegen"
        provenance_modes[mode] = provenance_modes.get(mode, 0) + 1
        for field in (SOURCE_REUSE_REQUIRED if mode == "source_reuse" else REQUIRED):
            if field == "source_bbox":
                if not valid_bbox(asset.get(field)):
                    add(issues, "required_evidence_missing", asset_index=index, field=field)
            elif not isinstance(asset.get(field), str) or not asset[field].strip():
                add(issues, "required_evidence_missing", asset_index=index, field=field)
        if mode == "source_reuse" and not valid_bbox(asset.get("source_bbox")):
            add(issues, "source_bbox_invalid", asset_index=index, source_bbox=asset.get("source_bbox"))
        layer = asset.get("layer")
        if layer not in LAYERS and not (isinstance(layer, str) and layer.startswith("icons")):
            add(issues, "invalid_layer", asset_index=index, layer=layer)
        if mode == "imagegen":
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
            else:
                observed_hash = sha256(copied_path)
                declared_hash = asset.get("sha256") or asset.get("asset_sha256") or asset.get("copied_to_sha256")
                if declared_hash:
                    hashed_asset_count += 1
                if args.require_hashes and not isinstance(declared_hash, str):
                    add(issues, "asset_hash_missing", asset_index=index, path=str(copied_path))
                elif declared_hash is not None and (not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash)):
                    add(issues, "asset_hash_invalid", asset_index=index, path=str(copied_path), declared_sha256=declared_hash, observed_sha256=observed_hash)
                elif declared_hash and declared_hash != observed_hash:
                    add(issues, "asset_hash_mismatch", asset_index=index, path=str(copied_path), declared_sha256=declared_hash, observed_sha256=observed_hash)
        source_ref = asset.get("source_ref")
        if mode == "source_reuse" and isinstance(source_ref, str) and source_ref:
            source_path = Path(source_ref)
            if not source_path.is_absolute():
                source_path = path.parent / source_path
            source_path = source_path.resolve()
            if not source_path.is_file():
                add(issues, "source_file_missing", asset_index=index, path=str(source_path))
            else:
                observed_source_hash = sha256(source_path)
                declared_source_hash = asset.get("source_sha256")
                if not isinstance(declared_source_hash, str) or not SHA256_RE.fullmatch(declared_source_hash):
                    add(issues, "source_hash_invalid", asset_index=index, path=str(source_path), declared_sha256=declared_source_hash)
                elif declared_source_hash != observed_source_hash:
                    add(issues, "source_hash_mismatch", asset_index=index, path=str(source_path), declared_sha256=declared_source_hash, observed_sha256=observed_source_hash)
        prompt = asset.get("prompt_file")
        if mode == "imagegen" and isinstance(prompt, str) and prompt:
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
        "hashed_asset_count": hashed_asset_count,
        "provenance_modes": provenance_modes,
        "hashes_required": args.require_hashes,
        "issues": issues,
        "human_visual_review_required": True,
    }
    if args.report:
        report = Path(args.report).resolve()
        atomic_write_json(report.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
