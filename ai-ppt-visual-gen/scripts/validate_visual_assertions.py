#!/usr/bin/env python3
"""Read back generated slide pixels and OCR against declared assertions.

This gate belongs to the visual-generation worker. It checks the retained
project copy from the generation manifest and never edits the raster or the
later editable-PPTX artifacts. Assertions are opt-in per slide so legacy
plans remain compatible while new plans can prove that real page text and
keyword emphasis survived generation.
"""
from __future__ import annotations

import argparse
import csv
import functools
import json
import re
import subprocess
import unicodedata
from pathlib import Path

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/visual-assertions-validation/v1"
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def compact(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value) if not char.isspace())


def render_copy_values(slide: dict) -> list[str]:
    """Return the unique visible copy for all-render-copy readback."""
    contract = slide.get("copy_contract") if isinstance(slide.get("copy_contract"), dict) else {}
    declared = contract.get("render_copy")
    if isinstance(declared, list) and declared:
        values = [text(item) for item in declared if text(item)]
    else:
        values = [text(slide.get("title")), text(slide.get("sub_title"))]
        content = slide.get("content_model") if isinstance(slide.get("content_model"), dict) else {}
        values.append(text(content.get("intro")))
        for module in content.get("modules", []) if isinstance(content.get("modules"), list) else []:
            if not isinstance(module, dict):
                continue
            values.extend(text(module.get(field)) for field in ("label", "title", "kpi", "tag"))
            bullets = module.get("bullets", module.get("points", []))
            if isinstance(bullets, str):
                bullets = [bullets]
            if isinstance(bullets, list):
                values.extend(text(item) for item in bullets)
        values.append(text(content.get("footer_banner")))
        for item in slide.get("formal_text", []) if isinstance(slide.get("formal_text"), list) else []:
            values.append(text(item if isinstance(item, str) else item.get("text") if isinstance(item, dict) else ""))
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def add_issue(issues: list[dict], code: str, slide_no: int | None = None, severity: str = "blocker", **details) -> None:
    item = {"severity": severity, "code": code}
    if slide_no is not None:
        item["slide_no"] = slide_no
    item.update({key: value for key, value in details.items() if value is not None})
    issues.append(item)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[index:index + 2], 16) for index in (1, 3, 5))


def count_color_pixels(path: Path, color: str, region, tolerance: int) -> tuple[int, tuple[int, int, int]]:
    from PIL import Image

    with Image.open(path) as original:
        image = original.convert("RGB")
        width, height = image.size
        if region is None:
            box = (0, 0, width, height)
        else:
            x, y, w, h = region
            box = (
                max(0, min(width, round(x * width))),
                max(0, min(height, round(y * height))),
                max(0, min(width, round((x + w) * width))),
                max(0, min(height, round((y + h) * height))),
            )
        if box[2] <= box[0] or box[3] <= box[1]:
            return 0, (width, height, 0)
        target = rgb(color)
        count = 0
        for pixel in image.crop(box).getdata():
            if max(abs(pixel[index] - target[index]) for index in range(3)) <= tolerance:
                count += 1
        return count, (width, height, box[2] - box[0])


def ink_ratio(path: Path) -> tuple[float, tuple[int, int]]:
    from PIL import Image

    with Image.open(path) as original:
        image = original.convert("RGB")
        width, height = image.size
        sample = image.copy()
        sample.thumbnail((256, 256))
        colors = sample.getcolors(maxcolors=256 * 256) or []
        dominant = max(colors, key=lambda item: item[0])[1] if colors else (255, 255, 255)
        pixels = list(sample.getdata())
        non_background = sum(1 for pixel in pixels if max(abs(pixel[index] - dominant[index]) for index in range(3)) > 12)
        return non_background / max(1, len(pixels)), (width, height)


@functools.lru_cache(maxsize=1)
def available_ocr_languages() -> tuple[str, ...]:
    try:
        completed = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if completed.returncode != 0:
        return ()
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    return tuple(line for line in lines if not line.lower().startswith("list of available languages"))


def ocr(path: Path, language: str) -> tuple[str | None, str | None, list[dict]]:
    requested = tuple(item for item in language.split("+") if item)
    available = available_ocr_languages()
    missing = [item for item in requested if item not in available]
    if missing:
        return None, f"missing OCR languages: {', '.join(missing)}; available: {', '.join(available) or 'none'}", []
    command = ["tesseract", str(path), "stdout", "--psm", "6", "-l", language, "tsv"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}: {exc}", []
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "tesseract failed").strip()
        return None, message, []
    words = []
    rows = csv.DictReader((completed.stdout or "").splitlines(), delimiter="\t")
    for row in rows:
        value = (row.get("text") or "").strip()
        if not value:
            continue
        try:
            left = int(row.get("left", "0"))
            top = int(row.get("top", "0"))
            width = int(row.get("width", "0"))
            height = int(row.get("height", "0"))
        except (TypeError, ValueError):
            continue
        if width > 0 and height > 0:
            words.append({"text": value, "left": left, "top": top, "right": left + width, "bottom": top + height})
    return " ".join(item["text"] for item in words), None, words


def text_bbox(words: list[dict], target: str) -> list[int] | None:
    """Find a contiguous OCR word span for a declared keyword."""
    wanted = compact(target)
    if not wanted:
        return None
    for start in range(len(words)):
        assembled = ""
        for end in range(start, min(len(words), start + 16)):
            assembled += compact(str(words[end].get("text", "")))
            if wanted in assembled:
                span = words[start:end + 1]
                return [
                    min(int(item["left"]) for item in span),
                    min(int(item["top"]) for item in span),
                    max(int(item["right"]) for item in span),
                    max(int(item["bottom"]) for item in span),
                ]
    return None


def occurrence_count(haystack: str, needle: str) -> int:
    """Count non-overlapping normalized occurrences in OCR output."""
    wanted = compact(needle)
    if not wanted:
        return 0
    return haystack.count(wanted)


def intersect_region(first: list[float], second: list[float] | None) -> list[float]:
    if second is None:
        return first
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    return [left, top, max(0.0, right - left), max(0.0, bottom - top)]


def validate_assertions(plan_path: Path, manifest_path: Path, expected_pages: int | None) -> tuple[dict, list[dict]]:
    issues: list[dict] = []
    try:
        plan = read_json(plan_path)
        manifest = read_json(manifest_path)
    except Exception as exc:
        return {}, [{"severity": "blocker", "code": "assertion_input_unreadable", "message": f"{type(exc).__name__}: {exc}"}]
    slides = plan.get("slides") if isinstance(plan.get("slides"), list) else []
    records = manifest.get("slides") if isinstance(manifest.get("slides"), list) else []
    by_number = {record.get("slide_no"): record for record in records if isinstance(record, dict)}
    assertion_slides = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        raw = slide.get("visual_assertions")
        if raw is None:
            continue
        slide_no = slide.get("slide_no")
        if not isinstance(raw, dict):
            add_issue(issues, "visual_assertions_not_object", slide_no=slide_no)
            continue
        assertion_slides.append(slide_no)
        must = raw.get("must_contain_text", [])
        forbidden = raw.get("forbidden_text", [])
        readback_scope = text(raw.get("readback_scope")) or "declared"
        if readback_scope not in {"declared", "all-render-copy", "title-and-key-anchors"}:
            add_issue(issues, "visual_assertions_readback_scope_invalid", slide_no=slide_no, observed=readback_scope)
        for field, values in (("must_contain_text", must), ("forbidden_text", forbidden)):
            if not isinstance(values, list) or any(not text(value) for value in values):
                add_issue(issues, "visual_assertions_text_list_invalid", slide_no=slide_no, field=field)
        emphasis = raw.get("keyword_emphasis", [])
        failure_policy = text(raw.get("ocr_failure_policy")) or "block"
        if failure_policy not in {"block", "manual-review"}:
            add_issue(issues, "visual_assertions_ocr_failure_policy_invalid", slide_no=slide_no, observed=failure_policy)
        if not isinstance(emphasis, list):
            add_issue(issues, "visual_assertions_emphasis_list_invalid", slide_no=slide_no)
            emphasis = []
        for index, item in enumerate(emphasis, start=1):
            if not isinstance(item, dict) or not text(item.get("text")) or not HEX_RE.fullmatch(text(item.get("color"))):
                add_issue(issues, "visual_assertions_emphasis_invalid", slide_no=slide_no, item=index)
                continue
            minimum = item.get("min_pixels", 8)
            tolerance = item.get("tolerance", 24)
            if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
                add_issue(issues, "visual_assertions_min_pixels_invalid", slide_no=slide_no, item=index)
            if isinstance(tolerance, bool) or not isinstance(tolerance, int) or not 0 <= tolerance <= 255:
                add_issue(issues, "visual_assertions_tolerance_invalid", slide_no=slide_no, item=index)
            region = item.get("region")
            if region is not None and (
                not isinstance(region, list)
                or len(region) != 4
                or any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in region)
                or region[0] < 0
                or region[1] < 0
                or region[2] <= 0
                or region[3] <= 0
                or region[0] + region[2] > 1
                or region[1] + region[3] > 1
            ):
                add_issue(issues, "visual_assertions_region_invalid", slide_no=slide_no, item=index)
        minimum_ink = raw.get("min_ink_ratio")
        if minimum_ink is not None and (isinstance(minimum_ink, bool) or not isinstance(minimum_ink, (int, float)) or not 0 <= minimum_ink <= 1):
            add_issue(issues, "visual_assertions_ink_ratio_invalid", slide_no=slide_no)

    if not assertion_slides:
        return {"configured": False, "slides": [], "ocr": {"requested": False}}, issues
    if expected_pages is not None and len(slides) != expected_pages:
        add_issue(issues, "visual_assertions_page_count_mismatch", expected=expected_pages, observed=len(slides))

    results = []
    for slide in slides:
        if not isinstance(slide, dict) or slide.get("slide_no") not in assertion_slides:
            continue
        slide_no = slide.get("slide_no")
        assertions = slide.get("visual_assertions") or {}
        record = by_number.get(slide_no)
        image_path = None
        if isinstance(record, dict) and text(record.get("copied_to")):
            candidate = Path(record["copied_to"])
            image_path = candidate.resolve() if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()
        if image_path is None or not image_path.is_file():
            add_issue(issues, "visual_assertions_image_missing", slide_no=slide_no, path=str(image_path) if image_path else None)
            continue
        slide_result = {"slide_no": slide_no, "image": str(image_path), "text": {}, "keyword_emphasis": []}
        must = [text(value) for value in assertions.get("must_contain_text", []) if text(value)]
        if text(assertions.get("readback_scope")) == "all-render-copy":
            must = list(dict.fromkeys(must + render_copy_values(slide)))
        forbidden = [text(value) for value in assertions.get("forbidden_text", []) if text(value)]
        emphasis_items = [item for item in assertions.get("keyword_emphasis", []) if isinstance(item, dict) and text(item.get("text"))]
        emphasis_texts = [text(item.get("text")) for item in emphasis_items]
        recognized_compact = ""
        recognized_words = []
        ocr_needed = bool(must or forbidden or emphasis_texts)
        ocr_available = False
        if ocr_needed:
            language = text(assertions.get("ocr_lang")) or "eng"
            failure_policy = text(assertions.get("ocr_failure_policy")) or "block"
            recognized, error, recognized_words = ocr(image_path, language)
            slide_result["ocr"] = {"language": language, "available": error is None, "error": error, "text": recognized or ""}
            if error is not None:
                if failure_policy == "manual-review":
                    add_issue(issues, "visual_ocr_manual_review_required", slide_no=slide_no, language=language, message=error, severity="warning")
                else:
                    add_issue(issues, "visual_ocr_unavailable", slide_no=slide_no, language=language, message=error)
            else:
                ocr_available = True
                recognized_compact = compact(recognized or "")
                for value in must:
                    passed = compact(value) in recognized_compact
                    slide_result["text"][value] = {"kind": "must_contain", "passed": passed}
                    if not passed:
                        add_issue(issues, "visual_text_missing", slide_no=slide_no, text=value, recognized=recognized_compact[:500])
                if text(assertions.get("readback_scope")) == "all-render-copy":
                    for value in render_copy_values(slide):
                        occurrences = occurrence_count(recognized_compact, value)
                        slide_result["text"].setdefault(value, {})["occurrences"] = occurrences
                        if occurrences > 1:
                            add_issue(issues, "visual_text_repeated", slide_no=slide_no, text=value, occurrences=occurrences)
                for value in forbidden:
                    passed = compact(value) not in recognized_compact
                    slide_result["text"][value] = {"kind": "forbidden", "passed": passed}
                    if not passed:
                        add_issue(issues, "visual_forbidden_text_present", slide_no=slide_no, text=value)
        minimum_ink = assertions.get("min_ink_ratio")
        if minimum_ink is not None:
            try:
                observed_ink, dimensions = ink_ratio(image_path)
            except Exception as exc:
                add_issue(issues, "visual_ink_measurement_failed", slide_no=slide_no, message=f"{type(exc).__name__}: {exc}")
            else:
                slide_result["ink_ratio"] = {"observed": round(observed_ink, 6), "minimum": minimum_ink, "dimensions": list(dimensions), "passed": observed_ink >= minimum_ink}
                if observed_ink < minimum_ink:
                    add_issue(issues, "visual_ink_ratio_low", slide_no=slide_no, minimum=minimum_ink, observed=round(observed_ink, 6))
        for index, item in enumerate(assertions.get("keyword_emphasis", []), start=1):
            if not isinstance(item, dict) or not HEX_RE.fullmatch(text(item.get("color"))):
                continue
            region = item.get("region")
            minimum = item.get("min_pixels", 8)
            tolerance = item.get("tolerance", 24)
            try:
                count, dimensions = count_color_pixels(image_path, text(item.get("color")), region, tolerance)
            except Exception as exc:
                add_issue(issues, "visual_color_measurement_failed", slide_no=slide_no, item=index, message=f"{type(exc).__name__}: {exc}")
                continue
            passed = count >= minimum
            keyword = text(item.get("text"))
            keyword_box = text_bbox(recognized_words, keyword) if ocr_available else None
            text_readback = {
                "requested": bool(keyword),
                "passed": keyword_box is not None and compact(keyword) in recognized_compact if ocr_available else False,
                "recognized": recognized_compact[:500] if ocr_available else None,
                "bbox": keyword_box,
                "status": "passed" if ocr_available and keyword_box is not None and compact(keyword) in recognized_compact else ("manual-review" if not ocr_available and (text(assertions.get("ocr_failure_policy")) or "block") == "manual-review" else "failed"),
            }
            if ocr_available and not text_readback["passed"]:
                add_issue(issues, "visual_keyword_text_missing", slide_no=slide_no, item=index, text=keyword, recognized=recognized_compact[:500])
            if ocr_available and keyword and keyword_box is None:
                add_issue(issues, "visual_keyword_bbox_missing", slide_no=slide_no, item=index, text=keyword)
            effective_region = region
            if keyword_box is not None:
                width, height = dimensions[:2]
                effective_region = [
                    keyword_box[0] / max(1, width),
                    keyword_box[1] / max(1, height),
                    (keyword_box[2] - keyword_box[0]) / max(1, width),
                    (keyword_box[3] - keyword_box[1]) / max(1, height),
                ]
                if isinstance(region, list) and len(region) == 4 and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in region):
                    effective_region = intersect_region(effective_region, [float(value) for value in region])
                try:
                    count, dimensions = count_color_pixels(image_path, text(item.get("color")), effective_region, tolerance)
                    passed = count >= minimum
                except Exception as exc:
                    add_issue(issues, "visual_color_measurement_failed", slide_no=slide_no, item=index, message=f"{type(exc).__name__}: {exc}")
                    count = 0
                    passed = False
            manual_text_review = not ocr_available and (text(assertions.get("ocr_failure_policy")) or "block") == "manual-review"
            item_result = {"text": keyword, "color": text(item.get("color")), "pixel_count": count, "minimum": minimum, "tolerance": tolerance, "region": region, "text_region": effective_region, "passed": passed and ((text_readback["passed"] if bool(keyword) else True) or manual_text_review), "color_passed": passed, "text_readback": text_readback, "dimensions": list(dimensions[:2])}
            slide_result["keyword_emphasis"].append(item_result)
            if not passed:
                add_issue(issues, "visual_keyword_emphasis_missing", slide_no=slide_no, item=index, text=text(item.get("text")), color=text(item.get("color")), minimum=minimum, observed=count)
        results.append(slide_result)
    return {"configured": True, "slides": results, "ocr": {"requested": any(bool((slide.get("visual_assertions") or {}).get("must_contain_text") or (slide.get("visual_assertions") or {}).get("forbidden_text") or (slide.get("visual_assertions") or {}).get("keyword_emphasis")) for slide in slides if isinstance(slide, dict))}}, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--report")
    args = parser.parse_args()
    plan_path = Path(args.plan).resolve()
    manifest_path = Path(args.manifest).resolve()
    try:
        evidence, issues = validate_assertions(plan_path, manifest_path, args.expected_pages)
    except Exception as exc:
        evidence = {}
        issues = [{"severity": "blocker", "code": "visual_assertions_failed", "message": f"{type(exc).__name__}: {exc}"}]
    blockers = [item for item in issues if item.get("severity") == "blocker"]
    result = {
        "schema": SCHEMA,
        "valid": not blockers,
        "status": "passed" if not issues else ("needs-human-review" if not blockers else "blocked"),
        "plan": str(plan_path),
        "manifest": str(manifest_path),
        "evidence": evidence,
        "issues": issues,
        "human_visual_review_required": True,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
