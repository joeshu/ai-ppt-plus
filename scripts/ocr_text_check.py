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


def parse_pages(value: str | None) -> set[int] | None:
    if not value:
        return None
    selected: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty page selector")
        if "-" in part:
            lo, hi = (int(item.strip()) for item in part.split("-", 1))
            if lo > hi:
                raise ValueError("page range is reversed")
            selected.update(range(lo, hi + 1))
        else:
            selected.add(int(part))
    if not selected or min(selected) < 1:
        raise ValueError("pages must be positive")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck")
    parser.add_argument("render_dir")
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--pages", help="only OCR selected slide numbers, e.g. 1,3-4")
    parser.add_argument("--require-ocr", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        selected_pages = parse_pages(args.pages)
    except (TypeError, ValueError) as exc:
        result = {"schema": "ai-ppt-plus/ocr-text-check/v1", "valid": False, "status": "failed", "deck": str(Path(args.deck).resolve()), "render_dir": str(Path(args.render_dir).resolve()), "language": args.lang, "slides": [], "issues": [{"severity": "blocker", "code": "invalid_pages", "message": str(exc)}], "human_visual_review_required": True}
        if args.report:
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 2
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
        result = {"schema": "ai-ppt-plus/ocr-text-check/v1", "valid": not issues, "status": "unavailable", "deck": str(deck.resolve()), "render_dir": str(render_dir.resolve()), "language": args.lang, "selected_pages": sorted(selected_pages) if selected_pages is not None else "all", "slides": [], "issues": issues, "human_visual_review_required": True}
        if args.report:
            report = Path(args.report)
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["valid"] else 2

    expected = slide_texts(deck)
    observed_pages = sorted(render_dir.glob("slide-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    if selected_pages is not None:
        observed_pages = [page for page in observed_pages if int(page.stem.split("-")[-1]) in selected_pages]
    slide_results = []
    expected_count = len(selected_pages) if selected_pages is not None else len(expected)
    if len(observed_pages) != expected_count:
        issues.append({"severity": "blocker", "code": "page_count_mismatch", "expected": expected_count, "observed": len(observed_pages)})
    for page in observed_pages:
        slide_number = int(page.stem.split("-")[-1])
        ocr = subprocess.run([tesseract, str(page), "stdout", "--psm", "11", "-l", args.lang], capture_output=True, text=True)
        observed = ocr.stdout.strip()
        expected_tokens = tokens(expected[slide_number - 1]) if 0 < slide_number <= len(expected) else []
        observed_text = observed.lower()
        matched = sum(1 for token in expected_tokens if token in observed_text)
        ratio = matched / len(expected_tokens) if expected_tokens else 1.0
        slide_results.append({"slide": slide_number, "page": page.name, "expected_token_count": len(expected_tokens), "matched_token_count": matched, "match_ratio": round(ratio, 4), "ocr_text_path": None, "ocr_text": observed})
        if ratio < args.threshold:
            issues.append({"severity": "blocker", "code": "ocr_text_match_below_threshold", "slide": slide_number, "threshold": args.threshold, "observed": round(ratio, 4)})
    result = {"schema": "ai-ppt-plus/ocr-text-check/v1", "valid": not issues, "status": "passed" if not issues else "failed", "deck": str(deck.resolve()), "render_dir": str(render_dir.resolve()), "language": args.lang, "selected_pages": sorted(selected_pages) if selected_pages is not None else "all", "slides": slide_results, "issues": issues, "human_visual_review_required": True, "limitation": "OCR can miss small, stylized, or overlapping text; use it as a diagnostic, not as formal content authority"}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
