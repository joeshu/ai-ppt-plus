#!/usr/bin/env python3
"""Materialize a task-local CJK font cache from system/runtime fonts.

The repository intentionally does not carry large TTF/TTC binaries. Runtime
font discovery may resolve a TTC collection (common for Noto CJK and Windows
CJK fonts), while downstream text-fit/font QA expects a standalone SFNT face.
This helper therefore extracts the requested family/weight from a collection
instead of merely renaming TTC bytes to ``.ttf``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from runtime_fonts import resolve_font_file

FONT_WEIGHTS = (400, 500, 600, 700)
FONT_NAMES = {400: "NotoSansSC-Regular.ttf", 500: "NotoSansSC-Medium.ttf", 600: "NotoSansSC-SemiBold.ttf", 700: "NotoSansSC-Bold.ttf"}
FONT_ROLES = {400: "regular", 500: "medium", 600: "semibold", 700: "bold"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_collection(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) == b"ttcf"
    except OSError:
        return False


def _name_values(face) -> set[str]:
    table = face.get("name")
    values: set[str] = set()
    if table is None:
        return values
    for record in table.names:
        if record.nameID not in {1, 4, 6, 16, 21}:
            continue
        try:
            value = record.toUnicode().strip()
        except Exception:
            continue
        if value:
            values.add(value)
    return values


def _font_weight(path: Path) -> int | None:
    from fontTools.ttLib import TTFont

    font = TTFont(str(path))
    try:
        os2 = font.get("OS/2")
        return int(os2.usWeightClass) if os2 is not None else None
    finally:
        font.close()


def _select_collection_face(source: Path, family: str, *, target_weight: int):
    from fontTools.ttLib import TTCollection

    collection = TTCollection(str(source))
    wanted = family.casefold().strip()
    ranked = []
    for index, face in enumerate(collection.fonts):
        names = _name_values(face)
        folded = {name.casefold() for name in names}
        family_score = 0
        if wanted in folded:
            family_score = 3
        elif any(wanted in name or name in wanted for name in folded):
            family_score = 2
        os2 = face.get("OS/2")
        weight = int(os2.usWeightClass) if os2 is not None else 400
        ranked.append((family_score, -abs(weight - target_weight), -index, index, face, names, weight))
    if not ranked:
        collection.close()
        raise RuntimeError(f"empty font collection: {source}")
    ranked.sort(reverse=True, key=lambda item: item[:3])
    best = ranked[0]
    if best[0] == 0 and len(collection.fonts) > 1:
        collection.close()
        raise RuntimeError(f"requested family {family!r} not found in collection {source}")
    if best[6] != target_weight:
        collection.close()
        raise RuntimeError(f"requested weight {target_weight} not found in collection {source}; observed {best[6]}")
    return collection, best[3], best[4], best[5], best[6]


def materialize_runtime_face(source: Path, target: Path, family: str, *, bold: bool | None = None, weight: int | None = None) -> dict:
    """Copy a standalone font or extract one family/weight face from a TTC."""
    target_weight = int(weight) if weight is not None else (700 if bold else 400)
    source = Path(source).resolve()
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not _is_collection(source):
        source_weight = _font_weight(source)
        if source_weight != target_weight:
            raise RuntimeError(f"resolved standalone font has weight {source_weight}, requested {target_weight}: {source}")
        shutil.copyfile(source, target)
        mode = "copied-standalone-sfnt"
        face_index = None
        names = []
        source_face_weight = source_weight
    else:
        collection, face_index, face, face_names, source_face_weight = _select_collection_face(source, family, target_weight=target_weight)
        try:
            face.save(str(target))
        finally:
            collection.close()
        mode = "extracted-standalone-face-from-collection"
        names = sorted(face_names)
    if _is_collection(target):
        raise RuntimeError(f"runtime cache must be standalone SFNT, got collection bytes: {target}")
    # Prove the materialized output opens as a standalone face.
    from fontTools.ttLib import TTFont

    probe = TTFont(str(target))
    try:
        os2 = probe.get("OS/2")
        output_weight = int(os2.usWeightClass) if os2 is not None else None
    finally:
        probe.close()
    return {
        "source": str(source),
        "target": str(target),
        "mode": mode,
        "source_face_index": face_index,
        "source_face_names": names,
        "source_weight": source_face_weight,
        "output_weight": output_weight,
        "sha256": sha256(target),
        "standalone_sfnt": True,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family", default="Noto Sans CJK SC")
    p.add_argument("--output-dir", default=".runtime/fonts")
    p.add_argument("--report", default=".runtime/font-runtime.json")
    p.add_argument("--weights", default="400,500,600,700", help="comma-separated real font weights to materialize")
    a = p.parse_args()
    try:
        weights = tuple(dict.fromkeys(int(value.strip()) for value in a.weights.split(",") if value.strip()))
    except ValueError as exc:
        print(json.dumps({"valid": False, "code": "runtime_font_weights_invalid", "message": str(exc)}, ensure_ascii=False))
        return 2
    if not weights or any(weight not in FONT_WEIGHTS for weight in weights):
        print(json.dumps({"valid": False, "code": "runtime_font_weights_unsupported", "allowed": list(FONT_WEIGHTS), "requested": list(weights)}, ensure_ascii=False))
        return 2
    out = Path(a.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for weight in weights:
        name = FONT_NAMES[weight]
        source = resolve_font_file(a.family, weight=weight)
        if source is None:
            print(json.dumps({"valid": False, "code": "runtime_cjk_font_unresolved", "family": a.family, "weight": weight}, ensure_ascii=False))
            return 2
        target = out / name
        try:
            record = materialize_runtime_face(source, target, a.family, weight=weight)
        except Exception as exc:
            print(json.dumps({"valid": False, "code": "runtime_cjk_font_materialization_failed", "family": a.family, "weight": weight, "source": str(source), "message": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
            return 2
        record["role"] = FONT_ROLES[weight]
        record["weight"] = weight
        records.append(record)
    report = {
        "schema": "ai-ppt-plus/runtime-font-materialization/v2",
        "valid": True,
        "family": a.family,
        "repository_font_binary_required": False,
        "runtime_cache": str(out),
        "weights": list(weights),
        "files": records,
    }
    report_path = Path(a.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
