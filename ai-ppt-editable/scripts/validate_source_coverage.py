#!/usr/bin/env python3
"""Validate independent source inventory -> PageGraph -> final PPTX coverage."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atomic_output import atomic_write_json
from reconstruction.graph_ir import PageGraph
from reconstruction.source_coverage import audit_source_coverage, extract_pptx_objects


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _page_values(value, count: int, label: str) -> list:
    if isinstance(value, dict) and isinstance(value.get("pages"), list):
        if len(value["pages"]) != count:
            raise ValueError(f"{label}.pages count does not match deck pages")
        return value["pages"]
    if count != 1:
        raise ValueError(f"{label} must contain pages[] for a multi-page deck")
    return [value]


def validate(reference, inventory, page_graph, deck):
    import zipfile
    from pptx import Presentation
    with zipfile.ZipFile(deck) as package:
        package.testzip()
    presentation = Presentation(deck)
    page_count = len(presentation.slides)
    inventory_pages = _page_values(inventory, page_count, "inventory")
    graph_pages = _page_values(page_graph, page_count, "page_graph")
    if isinstance(reference, dict):
        references = _page_values(reference, page_count, "reference")
    elif isinstance(reference, str) and Path(reference).is_dir():
        references = [str(Path(reference) / f"slide-{index}.png") for index in range(1, page_count + 1)]
    else:
        references = [reference]
    if len(references) != page_count:
        raise ValueError("reference count does not match deck pages")
    pages = []
    for index, (inv, graph_data, ref) in enumerate(zip(inventory_pages, graph_pages, references)):
        if not isinstance(inv, dict) or not isinstance(graph_data, dict):
            raise ValueError(f"page {index + 1}: inventory and graph must be objects")
        ref_path = Path(ref) if isinstance(ref, str) else None
        if ref_path is None or not ref_path.is_file():
            raise ValueError(f"page {index + 1}: reference file missing")
        graph = PageGraph.from_dict(graph_data)
        actual_hash = _sha(ref_path)
        if inv.get("source_sha256") != actual_hash:
            result = {"valid": False, "errors": [f"page {index + 1}: inventory/reference hash mismatch"]}
        else:
            result = audit_source_coverage(inv, graph,
                                           extract_pptx_objects(str(deck), slide_index=index))
        result["page"] = index + 1
        result["reference_sha256"] = actual_hash
        pages.append(result)
    errors = [f"page {item['page']}: {error}" for item in pages for error in item.get("errors", [])]
    return {"schema": "ai-ppt-plus/source-coverage-validation/v1", "valid": not errors,
            "status": "passed" if not errors else "failed", "page_count": page_count,
            "pages": pages, "errors": errors, "human_visual_review_required": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="reference PNG or JSON pages manifest")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--page-graph", required=True)
    parser.add_argument("--deck", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    try:
        reference = _read(Path(args.reference)) if args.reference.endswith(".json") else args.reference
        report = validate(reference, _read(Path(args.inventory)), _read(Path(args.page_graph)), Path(args.deck).resolve())
    except Exception as exc:
        report = {"schema": "ai-ppt-plus/source-coverage-validation/v1", "valid": False,
                  "status": "failed", "errors": [f"{type(exc).__name__}: {exc}"],
                  "human_visual_review_required": True}
    atomic_write_json(Path(args.report).resolve(), report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
