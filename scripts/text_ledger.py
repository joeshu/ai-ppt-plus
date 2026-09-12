#!/usr/bin/env python3
"""Compare a human-verified reference text ledger with final PPTX ``a:t`` text."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from atomic_output import atomic_write_json


A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"a": A}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def extract(pptx: Path) -> dict[int, dict]:
    pages: dict[int, dict] = {}
    with zipfile.ZipFile(pptx) as archive:
        for name in sorted(archive.namelist()):
            match = re.fullmatch(r"ppt/slides/slide(\d+)\.xml", name)
            if not match:
                continue
            page = int(match.group(1))
            root = ET.fromstring(archive.read(name))
            paragraphs = []
            for paragraph in root.iter(f"{{{A}}}p"):
                text = "".join(node.text or "" for node in paragraph.iter(f"{{{A}}}t"))
                if not text:
                    continue
                runs = []
                for run in paragraph.iter(f"{{{A}}}r"):
                    value = "".join(node.text or "" for node in run.iter(f"{{{A}}}t"))
                    props = next((child for child in run if local(child.tag) == "rPr"), None)
                    color = None
                    bold = False
                    if props is not None:
                        bold = props.attrib.get("b") in {"1", "true"}
                        for node in props.iter():
                            if local(node.tag) == "srgbClr": color = node.attrib.get("val")
                    runs.append({"text": value, "color": color, "bold": bold})
                paragraphs.append({"text": text, "runs": runs})
            pages[page] = {"text": "\n".join(item["text"] for item in paragraphs), "paragraphs": paragraphs}
    return pages


def char_diff(expected: str, observed: str) -> dict:
    import difflib
    matcher = difflib.SequenceMatcher(a=expected, b=observed)
    return {"ratio": matcher.ratio(), "opcodes": [{"tag": tag, "expected": expected[i1:i2], "observed": observed[j1:j2]}
                                                     for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    pptx = Path(args.pptx).resolve()
    ledger = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
    pages = extract(pptx)
    entries = ledger.get("entries", []) if isinstance(ledger, dict) else []
    issues = []
    comparisons = []
    low_confidence = []
    for index, entry in enumerate(entries):
        expected = str(entry.get("text", ""))
        page = int(entry.get("page", 1))
        observed_page = pages.get(page, {"text": "", "paragraphs": []})
        observed = observed_page["text"]
        exact = expected in observed
        diff = char_diff(expected, observed) if not exact else {"ratio": 1.0, "opcodes": []}
        confidence = float(entry.get("ocr_confidence", 1.0))
        human = entry.get("human_verified") is True
        if confidence < 0.97: low_confidence.append({"index": index, "page": page, "region": entry.get("region"), "confidence": confidence})
        if not human: issues.append({"severity": "blocker", "code": "ledger_not_human_verified", "index": index})
        if not exact: issues.append({"severity": "blocker", "code": "reference_text_missing_or_different", "index": index, "page": page, "region": entry.get("region"), "expected": expected, "diff": diff})
        comparisons.append({"index": index, "page": page, "region": entry.get("region"), "expected": expected, "present": exact, "character_diff": diff, "declared_color": entry.get("color"), "declared_bold": entry.get("bold"), "ocr_confidence": confidence, "human_verified": human})
    if not entries: issues.append({"severity": "blocker", "code": "empty_text_ledger"})
    result = {"schema": "ai-ppt-plus/text-ledger/v1", "valid": not issues,
              "status": "passed" if not issues else "blocked", "strict": args.strict,
              "pptx": str(pptx), "pages": {str(k): {"text": v["text"], "paragraph_count": len(v["paragraphs"])} for k, v in pages.items()},
              "entry_count": len(entries), "comparisons": comparisons, "low_confidence": low_confidence,
              "issues": issues, "rule": "OCR is auxiliary; human-verified ledger text is compared character-for-character against native PPTX text."}
    atomic_write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
