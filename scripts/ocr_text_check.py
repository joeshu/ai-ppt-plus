#!/usr/bin/env python3
"""Read rendered text back with Tesseract and compare it to PPTX text.

OCR is an evidence layer for missing/blank text, not a replacement for human
review. If the requested language model is unavailable, the result is
explicitly `unavailable`; `--require-ocr` turns that condition into a blocker.
"""
import argparse
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


def slide_texts(deck: Path):
    with zipfile.ZipFile(deck) as archive:
        names = sorted((name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)), key=lambda name: int(re.search(r"\d+", name).group()))
        texts = []
        for name in names:
            root = ET.fromstring(archive.read(name))
            texts.append(" ".join(node.text or "" for node in root.findall(".//a:t", NS)).strip())
        return texts


def tokens(text):
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    cjk_tokens = re.findall(r"[\u3400-\u9fff]", text)
    return ascii_tokens + cjk_tokens


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck")
    parser.add_argument("render_dir")
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--require-ocr", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    deck = Path(args.deck)
    render_dir = Path(args.render_dir)
    issues = []
    tesseract = shutil.which("tesseract")
    languages = set()
    if tesseract:
        listing = subprocess.run([tesseract, "--list-langs"], capture_output=True, text=True)
        languages = {line.strip() for line in listing.stdout.splitlines() if line.strip() and not line.startswith("List of available")}
    available = bool(tesseract and args.lang in languages)
    if not available:
        if args.require_ocr:
            issues.append({"severity": "blocker", "code": "ocr_unavailable", "tool": bool(tesseract), "language": args.lang, "available_languages": sorted(languages)})
        result = {"schema": "ai-ppt-plus/ocr-text-check/v1", "valid": not issues, "status": "unavailable", "deck": str(deck.resolve()), "render_dir": str(render_dir.resolve()), "language": args.lang, "slides": [], "issues": issues, "human_visual_review_required": True}
        if args.report:
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["valid"] else 2

    expected = slide_texts(deck)
    observed_pages = sorted(render_dir.glob("slide-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    slide_results = []
    if len(observed_pages) != len(expected):
        issues.append({"severity": "blocker", "code": "page_count_mismatch", "expected": len(expected), "observed": len(observed_pages)})
    for index, page in enumerate(observed_pages):
        ocr = subprocess.run([tesseract, str(page), "stdout", "--psm", "11", "-l", args.lang], capture_output=True, text=True)
        observed = ocr.stdout.strip()
        expected_tokens = tokens(expected[index]) if index < len(expected) else []
        observed_text = observed.lower()
        matched = sum(1 for token in expected_tokens if token in observed_text)
        ratio = matched / len(expected_tokens) if expected_tokens else 1.0
        slide_results.append({"slide": index + 1, "page": page.name, "expected_token_count": len(expected_tokens), "matched_token_count": matched, "match_ratio": round(ratio, 4), "ocr_text_path": None, "ocr_text": observed})
        if ratio < args.threshold:
            issues.append({"severity": "blocker", "code": "ocr_text_match_below_threshold", "slide": index + 1, "threshold": args.threshold, "observed": round(ratio, 4)})
    result = {"schema": "ai-ppt-plus/ocr-text-check/v1", "valid": not issues, "status": "passed" if not issues else "failed", "deck": str(deck.resolve()), "render_dir": str(render_dir.resolve()), "language": args.lang, "slides": slide_results, "issues": issues, "human_visual_review_required": True, "limitation": "OCR can miss small, stylized, or overlapping text; use it as a diagnostic, not as formal content authority"}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
