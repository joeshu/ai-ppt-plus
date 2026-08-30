#!/usr/bin/env python3
"""Validate the ai-ppt-visual-gen A1-A5 visual-generation contract.

This gate is intentionally scoped to the ``visual-creation`` route.  It
checks the planning and image-generation evidence used to make a visual
intermediate or image-based slide.  It does not inspect, compose or alter the
later image-to-editable-PPTX reconstruction route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json


PLAN_SCHEMA = "ai-ppt-plus/visual-generation-plan/v1"
MANIFEST_SCHEMA = "ai-ppt-plus/visual-generation-manifest/v1"
MODES = {"image-slide", "layout-reference"}
DENSITY_PROFILES = {"dense", "balanced", "minimal"}
EXEMPT_PAGE_TYPES = {"title", "section", "quote", "summary"}
REFERENCE_MODES = {"none", "layout-only", "layout-and-style"}
RETRY_SCOPES = {"single-slide"}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
GENERATION_CONTRACT = {
    "skill": "ai-ppt-visual-gen",
    "tool_resolution": "runtime-discovery",
    "preferred_tool": "imagegen",
    "backend_policy": "raster-only",
    "source_retention": "generated-source-and-project-copy",
}
PROHIBITED_GENERATION_TOKEN_RE = re.compile(
    r"(?:^|[^a-z])(svg|html|canvas|pillow|imagemagick|image\s*magick|code\s*draw)(?:$|[^a-z])",
    re.IGNORECASE,
)
PLACEHOLDER_RE = re.compile(
    r"(?:lorem\s+ipsum|placeholder|占位|待填写|待补充|TBD)|<[^>\n]{1,60}>", re.IGNORECASE
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_issue(issues: list[dict], severity: str, code: str, **details) -> None:
    item = {"severity": severity, "code": code}
    item.update({key: value for key, value in details.items() if value is not None})
    issues.append(item)


def text_value(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def resolve_path(base: Path, value) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def ratio_value(ratio: str) -> float | None:
    return {"16:9": 16 / 9, "3:2": 3 / 2}.get(ratio)


def formal_text_entries(slide: dict) -> list[dict]:
    entries = []
    for index, value in enumerate(slide.get("formal_text") or []):
        if isinstance(value, str):
            entries.append({"id": f"text-{index + 1}", "text": value.strip(), "role": "copy"})
        elif isinstance(value, dict):
            entries.append({
                "id": value.get("id") or f"text-{index + 1}",
                "text": text_value(value.get("text")),
                "role": value.get("role") or "copy",
                "source_ref": value.get("source_ref"),
            })
    return entries


def content_text_entries(slide: dict) -> list[str]:
    """Return every visible copy declared in the structured content model."""
    content = slide.get("content_model") if isinstance(slide.get("content_model"), dict) else {}
    values = [text_value(content.get("intro"))]
    modules = content.get("modules") or []
    if isinstance(modules, list):
        for module in modules:
            if not isinstance(module, dict):
                continue
            values.extend(text_value(module.get(field)) for field in ("label", "title", "kpi", "tag"))
            bullets = module.get("bullets", module.get("points", []))
            if isinstance(bullets, str):
                bullets = [bullets]
            if isinstance(bullets, list):
                values.extend(text_value(item) for item in bullets)
    values.append(text_value(content.get("footer_banner")))
    return [value for value in values if value]


def copy_values(slide: dict) -> list[str]:
    """Return copy-bearing strings against which emphasis tokens are checked."""
    values = [text_value(slide.get("title")), text_value(slide.get("sub_title"))]
    values.extend(content_text_entries(slide))
    values.extend(entry["text"] for entry in formal_text_entries(slide) if entry["text"])
    return [value for value in values if value]


def diagram_annotation_entries(slide: dict) -> list[dict]:
    """Return explicitly approved non-formal relationship labels."""
    annotations = slide.get("diagram_annotations") if isinstance(slide.get("diagram_annotations"), list) else []
    entries = []
    for index, item in enumerate(annotations, start=1):
        if isinstance(item, dict):
            entries.append({
                "index": index,
                "text": text_value(item.get("text")),
                "purpose": text_value(item.get("purpose")),
                "scope": text_value(item.get("scope")),
            })
        else:
            entries.append({"index": index, "text": "", "purpose": "", "scope": ""})
    return entries


def detailed_content_entries(slide: dict) -> list[str]:
    """Return A2's thick-content reserve without treating it as visible copy."""
    paragraphs = slide.get("detailed_content_paragraphs") if isinstance(slide.get("detailed_content_paragraphs"), list) else []
    return [text_value(item) for item in paragraphs if text_value(item)]


def reference_path(value) -> str:
    """Read a reference path from either the legacy string or structured form."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for field in ("path", "file", "id"):
            path = text_value(value.get(field))
            if path:
                return path
    return ""


def module_metrics(content: dict) -> tuple[int, int, int, list[dict]]:
    modules = content.get("modules") if isinstance(content, dict) else []
    if not isinstance(modules, list):
        return 0, 0, 0, []
    info_points = int(bool(text_value(content.get("intro")))) + int(bool(text_value(content.get("footer_banner"))))
    bullet_counts = []
    summaries = []
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            bullet_counts.append(0)
            summaries.append({"index": index + 1, "title": "", "bullets": 0, "info_points": 0})
            continue
        bullets = module.get("bullets", module.get("points", []))
        if isinstance(bullets, str):
            bullets = [bullets]
        if not isinstance(bullets, list):
            bullets = []
        bullets = [text_value(item) for item in bullets if text_value(item)]
        points = (
            int(bool(text_value(module.get("label"))))
            + int(bool(text_value(module.get("title"))))
            + len(bullets)
            + int(bool(text_value(module.get("kpi"))))
            + int(bool(text_value(module.get("tag"))))
        )
        info_points += points
        bullet_counts.append(len(bullets))
        summaries.append({
            "index": index + 1,
            "title": text_value(module.get("title")),
            "bullets": len(bullets),
            "info_points": points,
            "source_refs": [text_value(item) for item in (module.get("source_refs") or []) if text_value(item)] if isinstance(module.get("source_refs"), list) else [],
        })
    return len(modules), min(bullet_counts) if bullet_counts else 0, info_points, summaries


def density_threshold(profile: str) -> tuple[int, int, int]:
    return {
        "dense": (4, 2, 18),
        "balanced": (2, 1, 8),
        "minimal": (1, 0, 2),
    }[profile]


def validate_image(path: Path) -> tuple[bool, tuple[int, int] | None, str | None]:
    try:
        from PIL import Image
    except ImportError as exc:
        return False, None, f"Pillow unavailable: {exc}"
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            return True, image.size, None
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"


def validate_evidence(plan_path: Path, plan: dict, manifest_path: Path, issues: list[dict], require: bool) -> dict:
    evidence = {"manifest_path": str(manifest_path), "slides": []}
    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        add_issue(issues, "blocker", "generation_manifest_invalid", message=f"{type(exc).__name__}: {exc}")
        return evidence
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        add_issue(issues, "blocker", "generation_manifest_schema_invalid", observed=manifest.get("schema") if isinstance(manifest, dict) else None)
        return evidence
    if manifest.get("project_id") != plan.get("project_id"):
        add_issue(issues, "blocker", "generation_manifest_project_mismatch", expected=plan.get("project_id"), observed=manifest.get("project_id"))
    if plan.get("mode") == "image-slide":
        expected_contract = plan.get("generation_contract") if isinstance(plan.get("generation_contract"), dict) else {}
        expected_contract = {**GENERATION_CONTRACT, **expected_contract}
        manifest_contract_fields = {
            "generator_skill": expected_contract.get("skill"),
            "tool_resolution": expected_contract.get("tool_resolution"),
            "backend_policy": expected_contract.get("backend_policy"),
            "source_retention": expected_contract.get("source_retention"),
            "no_code_overlay": True,
        }
        for field, expected in manifest_contract_fields.items():
            observed = manifest.get(field)
            if observed != expected:
                add_issue(issues, "blocker", "generation_manifest_contract_mismatch", field=field, expected=expected, observed=observed)
    declared_plan_hash = manifest.get("plan_sha256")
    actual_plan_hash = sha256(plan_path)
    if not isinstance(declared_plan_hash, str) or not SHA256_RE.fullmatch(declared_plan_hash):
        add_issue(issues, "blocker", "generation_plan_hash_missing")
    elif declared_plan_hash != actual_plan_hash:
        add_issue(issues, "blocker", "generation_plan_hash_mismatch", expected=actual_plan_hash, observed=declared_plan_hash)
    records = manifest.get("slides")
    if not isinstance(records, list):
        add_issue(issues, "blocker", "generation_manifest_slides_missing")
        return evidence
    expected_slides = {slide.get("slide_no"): slide for slide in plan.get("slides", []) if isinstance(slide, dict)}
    observed = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            add_issue(issues, "blocker", "generation_manifest_slide_invalid", index=index)
            continue
        slide_no = record.get("slide_no")
        if not isinstance(slide_no, int) or slide_no < 1:
            add_issue(issues, "blocker", "generation_manifest_slide_number_invalid", index=index)
            continue
        if slide_no in observed:
            add_issue(issues, "blocker", "generation_manifest_slide_duplicate", slide_no=slide_no)
        observed[slide_no] = record
        plan_slide = expected_slides.get(slide_no, {})
        record_summary = {"slide_no": slide_no, "files": {}}
        backend_label = " ".join(text_value(record.get(field)) for field in ("backend", "model_or_tool"))
        if PROHIBITED_GENERATION_TOKEN_RE.search(backend_label):
            add_issue(issues, "blocker", "generation_backend_not_raster", slide_no=slide_no, observed=backend_label)
        for field in ("prompt_file", "generated_source", "copied_to", "backend", "model_or_tool", "canvas"):
            value = record.get(field)
            missing = not isinstance(value, dict) if field == "canvas" else not text_value(value)
            if missing:
                add_issue(issues, "blocker", "generation_evidence_field_missing", slide_no=slide_no, field=field)
        prompt_path = resolve_path(manifest_path.parent, record.get("prompt_file"))
        plan_prompt_path = resolve_path(plan_path.parent, plan_slide.get("prompt_file"))
        if prompt_path and plan_prompt_path and prompt_path != plan_prompt_path:
            add_issue(issues, "blocker", "generation_prompt_plan_mismatch", slide_no=slide_no, expected=str(plan_prompt_path), observed=str(prompt_path))
        if prompt_path is None or not prompt_path.is_file():
            add_issue(issues, "blocker" if require else "warning", "generation_prompt_file_missing", slide_no=slide_no, path=str(prompt_path) if prompt_path else None)
        else:
            try:
                prompt_text = prompt_path.read_text(encoding="utf-8")
            except Exception as exc:
                prompt_text = ""
                add_issue(issues, "blocker", "generation_prompt_file_unreadable", slide_no=slide_no, message=f"{type(exc).__name__}: {exc}")
            production_prompt = text_value(plan_slide.get("production_prompt"))
            if production_prompt and production_prompt not in prompt_text:
                add_issue(issues, "blocker", "generation_prompt_file_not_materialized", slide_no=slide_no)
            for entry in formal_text_entries(plan_slide):
                if entry["text"] and entry["text"] not in prompt_text:
                    add_issue(issues, "blocker", "generation_prompt_copy_mismatch", slide_no=slide_no, text_id=entry["id"])
            if plan.get("mode") == "image-slide":
                declared_prompt_hash = record.get("prompt_sha256")
                if not isinstance(declared_prompt_hash, str) or not SHA256_RE.fullmatch(declared_prompt_hash):
                    add_issue(issues, "blocker" if require else "warning", "generation_prompt_hash_missing", slide_no=slide_no)
                elif sha256(prompt_path) != declared_prompt_hash:
                    add_issue(issues, "blocker", "generation_prompt_hash_mismatch", slide_no=slide_no, expected=sha256(prompt_path), observed=declared_prompt_hash)
        record_canvas = record.get("canvas")
        expected_ratio = text_value((plan.get("canvas") or {}).get("ratio")) if isinstance(plan.get("canvas"), dict) else ""
        if isinstance(record_canvas, dict) and expected_ratio and record_canvas.get("ratio") != expected_ratio:
            add_issue(issues, "blocker", "generation_canvas_ratio_mismatch", slide_no=slide_no, expected=expected_ratio, observed=record_canvas.get("ratio"))
        for field, hash_field in (("generated_source", "generated_source_sha256"), ("copied_to", "copied_to_sha256")):
            path = resolve_path(manifest_path.parent, record.get(field))
            record_summary["files"][field] = str(path) if path else None
            if path is None or not path.is_file():
                add_issue(issues, "blocker" if require else "warning", "generation_image_missing", slide_no=slide_no, field=field, path=str(path) if path else None)
                continue
            valid_image, size, error = validate_image(path)
            if not valid_image:
                add_issue(issues, "blocker", "generation_image_decode_failed", slide_no=slide_no, field=field, message=error)
                continue
            record_summary["files"][field + "_size"] = list(size or ())
            expected_ratio_value = ratio_value(expected_ratio)
            if size and expected_ratio_value and size[1] and abs((size[0] / size[1]) - expected_ratio_value) > 0.02:
                add_issue(issues, "blocker", "generation_image_ratio_mismatch", slide_no=slide_no, field=field, expected=expected_ratio, observed=f"{size[0]}:{size[1]}")
            declared_hash = record.get(hash_field)
            actual_hash = sha256(path)
            if not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash):
                add_issue(issues, "blocker", "generation_image_hash_missing", slide_no=slide_no, field=hash_field)
            elif actual_hash != declared_hash:
                add_issue(issues, "blocker", "generation_image_hash_mismatch", slide_no=slide_no, field=hash_field, expected=actual_hash, observed=declared_hash)
        source_path = resolve_path(manifest_path.parent, record.get("generated_source"))
        copied_path = resolve_path(manifest_path.parent, record.get("copied_to"))
        if source_path and copied_path and source_path == copied_path:
            add_issue(issues, "blocker", "generation_source_copy_same_path", slide_no=slide_no)
        evidence["slides"].append(record_summary)
    for slide_no in sorted(set(expected_slides) - set(observed)):
        add_issue(issues, "blocker", "generation_manifest_slide_missing", slide_no=slide_no)
    for slide_no in sorted(set(observed) - set(expected_slides)):
        add_issue(issues, "blocker", "generation_manifest_slide_unexpected", slide_no=slide_no)
    deck_strip = manifest.get("deck_strip")
    if plan.get("mode") == "image-slide":
        if not isinstance(deck_strip, dict):
            add_issue(issues, "blocker" if require else "warning", "generation_deck_strip_missing")
        else:
            strip_path = resolve_path(manifest_path.parent, deck_strip.get("path"))
            if strip_path is None or not strip_path.is_file():
                add_issue(issues, "blocker", "generation_deck_strip_file_missing", path=str(strip_path) if strip_path else None)
            else:
                valid_strip, _strip_size, strip_error = validate_image(strip_path)
                if not valid_strip:
                    add_issue(issues, "blocker", "generation_deck_strip_decode_failed", message=strip_error)
                declared_strip_hash = deck_strip.get("sha256")
                if not isinstance(declared_strip_hash, str) or not SHA256_RE.fullmatch(declared_strip_hash):
                    add_issue(issues, "blocker", "generation_deck_strip_hash_missing")
                else:
                    actual_strip_hash = sha256(strip_path)
                    if actual_strip_hash != declared_strip_hash:
                        add_issue(issues, "blocker", "generation_deck_strip_hash_mismatch", expected=actual_strip_hash, observed=declared_strip_hash)
            strip_sources = deck_strip.get("source_slides")
            if not isinstance(strip_sources, list):
                add_issue(issues, "blocker", "generation_deck_strip_sources_missing")
            else:
                expected_numbers = set(expected_slides)
                strip_numbers = []
                manifest_by_number = {record.get("slide_no"): record for record in records if isinstance(record, dict)}
                for index, source in enumerate(strip_sources):
                    if not isinstance(source, dict) or not isinstance(source.get("slide_no"), int):
                        add_issue(issues, "blocker", "generation_deck_strip_source_invalid", index=index)
                        continue
                    strip_slide_no = source["slide_no"]
                    strip_numbers.append(strip_slide_no)
                    manifest_record = manifest_by_number.get(strip_slide_no)
                    if manifest_record is None:
                        add_issue(issues, "blocker", "generation_deck_strip_source_unexpected", slide_no=strip_slide_no)
                        continue
                    expected_image = resolve_path(manifest_path.parent, manifest_record.get("copied_to"))
                    observed_image = resolve_path(manifest_path.parent, source.get("image"))
                    if expected_image is None or observed_image is None or expected_image != observed_image:
                        add_issue(issues, "blocker", "generation_deck_strip_source_mismatch", slide_no=strip_slide_no)
                    source_hash = source.get("sha256")
                    if observed_image and observed_image.is_file():
                        if not isinstance(source_hash, str) or not SHA256_RE.fullmatch(source_hash):
                            add_issue(issues, "blocker", "generation_deck_strip_source_hash_missing", slide_no=strip_slide_no)
                        elif sha256(observed_image) != source_hash:
                            add_issue(issues, "blocker", "generation_deck_strip_source_hash_mismatch", slide_no=strip_slide_no)
                if len(strip_numbers) != len(set(strip_numbers)) or set(strip_numbers) != expected_numbers:
                    add_issue(issues, "blocker", "generation_deck_strip_slide_coverage_mismatch", expected=sorted(expected_numbers), observed=sorted(strip_numbers))
            if not text_value(deck_strip.get("review_status")):
                add_issue(issues, "blocker", "generation_deck_strip_review_status_missing")
    evidence["plan_sha256"] = actual_plan_hash
    evidence["record_count"] = len(records)
    if isinstance(deck_strip, dict):
        strip_path = resolve_path(manifest_path.parent, deck_strip.get("path"))
        evidence["deck_strip"] = {
            "path": str(strip_path) if strip_path else None,
            "review_status": text_value(deck_strip.get("review_status")),
            "slide_count": len(deck_strip.get("source_slides") or []) if isinstance(deck_strip.get("source_slides"), list) else 0,
        }
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--manifest", help="visual-generation-manifest.json; omit during A1-A3 plan-only validation")
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--require-evidence", action="store_true", help="require retained source/copy images, hashes and prompt files")
    parser.add_argument("--report")
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    issues: list[dict] = []
    try:
        plan = read_json(plan_path)
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/visual-generation-validation/v1", "valid": False, "status": "blocked", "issues": [{"severity": "blocker", "code": "plan_invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}
        if args.report:
            atomic_write_json(Path(args.report).resolve(), result)
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not isinstance(plan, dict):
        add_issue(issues, "blocker", "plan_not_object")
        plan = {}
    if plan.get("schema") != PLAN_SCHEMA:
        add_issue(issues, "blocker", "plan_schema_invalid", observed=plan.get("schema"))
    if plan.get("route") != "visual-creation":
        add_issue(issues, "blocker", "plan_route_invalid", observed=plan.get("route"))
    mode = plan.get("mode")
    if mode not in MODES:
        add_issue(issues, "blocker", "plan_mode_invalid", observed=mode)
    if mode == "image-slide":
        generation_contract = plan.get("generation_contract")
        if not isinstance(generation_contract, dict):
            add_issue(issues, "blocker", "generation_contract_missing")
            generation_contract = {}
        for field, expected in GENERATION_CONTRACT.items():
            observed = generation_contract.get(field)
            if observed != expected:
                add_issue(issues, "blocker", "generation_contract_mismatch", field=field, expected=expected, observed=observed)
        if generation_contract.get("no_code_overlay") is not True:
            add_issue(issues, "blocker", "generation_contract_no_code_overlay_missing")
        generation_context = plan.get("generation_context")
        if not isinstance(generation_context, dict):
            add_issue(issues, "blocker", "generation_context_missing")
            generation_context = {}
        for field in ("audience", "language", "presentation_context"):
            if not text_value(generation_context.get(field)):
                add_issue(issues, "blocker", "generation_context_field_missing", field=field)
        retry = plan.get("retry_policy")
        if not isinstance(retry, dict):
            add_issue(issues, "blocker", "retry_policy_missing")
            retry = {}
        attempts = retry.get("max_attempts_per_slide")
        if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1 or attempts > 3:
            add_issue(issues, "blocker", "retry_policy_attempts_invalid", observed=attempts)
        if retry.get("scope") not in RETRY_SCOPES:
            add_issue(issues, "blocker", "retry_policy_scope_invalid", observed=retry.get("scope"))
        triggers = retry.get("triggers")
        if not isinstance(triggers, list) or not any(text_value(item) for item in triggers):
            add_issue(issues, "blocker", "retry_policy_triggers_missing")
    else:
        generation_context = plan.get("generation_context") if isinstance(plan.get("generation_context"), dict) else {}
        retry = plan.get("retry_policy") if isinstance(plan.get("retry_policy"), dict) else {}
    if not text_value(plan.get("project_id")):
        add_issue(issues, "blocker", "plan_project_id_missing")
    for field in ("outline_revision", "design_system_revision"):
        if not text_value(plan.get(field)):
            add_issue(issues, "blocker", "plan_revision_missing", field=field)
    try:
        page_count = int(plan.get("page_count"))
    except (TypeError, ValueError):
        page_count = 0
        add_issue(issues, "blocker", "plan_page_count_invalid")
    if page_count < 1:
        add_issue(issues, "blocker", "plan_page_count_invalid", observed=plan.get("page_count"))
    if args.expected_pages is not None and page_count != args.expected_pages:
        add_issue(issues, "blocker", "plan_page_count_mismatch", expected=args.expected_pages, observed=page_count)
    style_lock = plan.get("style_lock")
    if not isinstance(style_lock, dict):
        add_issue(issues, "blocker", "style_lock_missing")
        style_lock = {}
    palette = style_lock.get("palette")
    palette_hexes = []
    if not isinstance(palette, list) or len(palette) < 3:
        add_issue(issues, "blocker", "style_lock_palette_too_small", minimum=3)
    else:
        for index, item in enumerate(palette):
            color = item.get("hex") if isinstance(item, dict) else item
            if not isinstance(color, str) or not HEX_RE.fullmatch(color):
                add_issue(issues, "blocker", "style_lock_palette_color_invalid", index=index, observed=color)
            else:
                palette_hexes.append(color.lower())
    for field in ("font_style", "surface", "icon_style"):
        if not text_value(style_lock.get(field)):
            add_issue(issues, "blocker", "style_lock_field_missing", field=field)
    avoid_items = style_lock.get("avoid_items")
    if not isinstance(avoid_items, list) or not all(text_value(item) for item in avoid_items):
        add_issue(issues, "blocker", "style_lock_avoid_items_invalid")
    canvas = plan.get("canvas")
    if not isinstance(canvas, dict):
        add_issue(issues, "blocker", "canvas_missing")
        canvas = {}
    ratio = text_value(canvas.get("ratio"))
    if ratio not in {"16:9", "3:2"}:
        add_issue(issues, "blocker", "canvas_ratio_invalid", observed=ratio)
    density_profile = plan.get("density_profile", "dense")
    if density_profile not in DENSITY_PROFILES:
        add_issue(issues, "blocker", "density_profile_invalid", observed=density_profile)
        density_profile = "dense"
    if density_profile != "dense" and not text_value(plan.get("density_override_reason")):
        add_issue(issues, "blocker", "density_override_reason_missing")
    slides = plan.get("slides")
    if not isinstance(slides, list):
        slides = []
        add_issue(issues, "blocker", "plan_slides_missing")
    if len(slides) != page_count:
        add_issue(issues, "blocker", "plan_slide_count_mismatch", expected=page_count, observed=len(slides))
    slide_numbers = []
    frameworks = {}
    slide_summaries = []
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            add_issue(issues, "blocker", "plan_slide_invalid", index=index)
            continue
        slide_no = slide.get("slide_no")
        if not isinstance(slide_no, int) or slide_no < 1:
            add_issue(issues, "blocker", "plan_slide_number_invalid", index=index)
        elif slide_no in slide_numbers:
            add_issue(issues, "blocker", "plan_slide_number_duplicate", slide_no=slide_no)
        else:
            slide_numbers.append(slide_no)
        for field in ("page_type", "title", "core_logic", "visual_framework", "visual_generation_prompt"):
            if not text_value(slide.get(field)):
                add_issue(issues, "blocker", "plan_slide_field_missing", slide_no=slide_no, field=field)
        framework = text_value(slide.get("visual_framework"))
        if framework:
            if framework in frameworks:
                add_issue(issues, "blocker", "visual_framework_duplicate", slide_no=slide_no, previous_slide=frameworks[framework], framework=framework)
            else:
                frameworks[framework] = slide_no
        content = slide.get("content_model")
        if not isinstance(content, dict):
            add_issue(issues, "blocker", "content_model_missing", slide_no=slide_no)
            content = {}
        modules, min_bullets, info_points, module_summaries = module_metrics(content)
        profile = slide.get("density_profile", density_profile)
        if profile not in DENSITY_PROFILES:
            add_issue(issues, "blocker", "slide_density_profile_invalid", slide_no=slide_no, observed=profile)
            profile = density_profile
        page_type = text_value(slide.get("page_type"))
        has_exception = page_type in EXEMPT_PAGE_TYPES or text_value(slide.get("density_exception_reason"))
        if profile != "dense" and not has_exception and not text_value(slide.get("density_exception_reason")):
            add_issue(issues, "blocker", "slide_density_exception_reason_missing", slide_no=slide_no)
        detailed_content = detailed_content_entries(slide)
        for paragraph_index, paragraph in enumerate(detailed_content, start=1):
            if PLACEHOLDER_RE.search(paragraph):
                add_issue(issues, "blocker", "detailed_content_placeholder", slide_no=slide_no, paragraph=paragraph_index)
        if mode == "image-slide" and profile == "dense" and not has_exception and len(detailed_content) < 3:
            add_issue(issues, "blocker", "detailed_content_reserve_low", slide_no=slide_no, minimum=3, observed=len(detailed_content))
        blueprint = slide.get("layout_blueprint")
        if mode == "image-slide" and profile == "dense" and not has_exception:
            if not isinstance(blueprint, dict):
                add_issue(issues, "blocker", "layout_blueprint_missing", slide_no=slide_no)
            else:
                for field in ("focal_point", "reading_path"):
                    if not text_value(blueprint.get(field)):
                        add_issue(issues, "blocker", "layout_blueprint_field_missing", slide_no=slide_no, field=field)
                zones = blueprint.get("zones")
                if not isinstance(zones, list) or len(zones) < 3:
                    add_issue(issues, "blocker", "layout_blueprint_zones_low", slide_no=slide_no, minimum=3, observed=len(zones) if isinstance(zones, list) else 0)
                else:
                    for zone_index, zone in enumerate(zones, start=1):
                        if isinstance(zone, dict):
                            if not text_value(zone.get("name")) or not text_value(zone.get("purpose")):
                                add_issue(issues, "blocker", "layout_blueprint_zone_invalid", slide_no=slide_no, zone=zone_index)
                        elif not text_value(zone):
                            add_issue(issues, "blocker", "layout_blueprint_zone_invalid", slide_no=slide_no, zone=zone_index)
                guards = blueprint.get("anti_template_rules")
                if not isinstance(guards, list) or not any(text_value(item) for item in guards):
                    add_issue(issues, "blocker", "layout_blueprint_guards_missing", slide_no=slide_no)
            emphasis = slide.get("keyword_emphasis")
            if not isinstance(emphasis, dict):
                add_issue(issues, "blocker", "keyword_emphasis_missing", slide_no=slide_no)
            else:
                rules = emphasis.get("rules")
                if not isinstance(rules, list) or not any(text_value(item) for item in rules):
                    add_issue(issues, "blocker", "keyword_emphasis_rules_missing", slide_no=slide_no)
                items = emphasis.get("items")
                if not isinstance(items, list) or not items:
                    add_issue(issues, "blocker", "keyword_emphasis_items_missing", slide_no=slide_no)
                else:
                    visible_copy = copy_values(slide)
                    for item_index, item in enumerate(items, start=1):
                        if not isinstance(item, dict):
                            add_issue(issues, "blocker", "keyword_emphasis_item_invalid", slide_no=slide_no, item=item_index)
                            continue
                        token = text_value(item.get("text"))
                        color = text_value(item.get("color"))
                        scope = text_value(item.get("scope"))
                        if not token or not color or not scope:
                            add_issue(issues, "blocker", "keyword_emphasis_item_invalid", slide_no=slide_no, item=item_index)
                        elif not HEX_RE.fullmatch(color):
                            add_issue(issues, "blocker", "keyword_emphasis_color_invalid", slide_no=slide_no, item=item_index, observed=color)
                        elif not any(token in value for value in visible_copy):
                            add_issue(issues, "blocker", "keyword_emphasis_text_not_in_copy", slide_no=slide_no, item=item_index, text=token)
            annotations = diagram_annotation_entries(slide)
            for annotation in annotations:
                if not annotation["text"] or not annotation["purpose"] or not annotation["scope"]:
                    add_issue(issues, "blocker", "diagram_annotation_invalid", slide_no=slide_no, item=annotation["index"])
                elif PLACEHOLDER_RE.search(annotation["text"]):
                    add_issue(issues, "blocker", "diagram_annotation_placeholder", slide_no=slide_no, item=annotation["index"])
        min_modules, min_bullets_required, min_info = density_threshold(profile)
        if not has_exception:
            if profile == "dense" and not text_value(content.get("intro")):
                add_issue(issues, "blocker", "content_intro_missing", slide_no=slide_no)
            if profile == "dense" and not text_value(content.get("footer_banner")):
                add_issue(issues, "blocker", "content_footer_missing", slide_no=slide_no)
            if modules < min_modules:
                add_issue(issues, "blocker", "content_module_count_low", slide_no=slide_no, profile=profile, minimum=min_modules, observed=modules)
            if min_bullets < min_bullets_required:
                add_issue(issues, "blocker", "content_bullet_count_low", slide_no=slide_no, profile=profile, minimum=min_bullets_required, observed=min_bullets)
            if info_points < min_info:
                add_issue(issues, "blocker", "content_info_point_count_low", slide_no=slide_no, profile=profile, minimum=min_info, observed=info_points)
            for module_index, module in enumerate(content.get("modules") or [], start=1):
                if isinstance(module, dict):
                    source_refs = module.get("source_refs")
                    if not isinstance(source_refs, list) or not any(text_value(item) for item in source_refs):
                        add_issue(issues, "blocker", "content_module_source_reference_missing", slide_no=slide_no, module=module_index)
                    if profile == "dense":
                        if not text_value(module.get("title")):
                            add_issue(issues, "blocker", "content_module_title_missing", slide_no=slide_no, module=module_index)
                        raw_bullets = module.get("bullets", module.get("points", []))
                        if isinstance(raw_bullets, str):
                            raw_bullets = [raw_bullets]
                        bullet_count = len([text_value(item) for item in raw_bullets if text_value(item)]) if isinstance(raw_bullets, list) else 0
                        if bullet_count < 2:
                            add_issue(issues, "blocker", "content_module_bullets_low", slide_no=slide_no, module=module_index, minimum=2, observed=bullet_count)
                        if not text_value(module.get("kpi")):
                            add_issue(issues, "blocker", "content_module_kpi_missing", slide_no=slide_no, module=module_index)
                        if not text_value(module.get("tag")):
                            add_issue(issues, "blocker", "content_module_tag_missing", slide_no=slide_no, module=module_index)
        formal_entries = formal_text_entries(slide)
        production_prompt = text_value(slide.get("production_prompt"))
        visual_prompt = text_value(slide.get("visual_generation_prompt"))
        if mode == "image-slide":
            if not production_prompt:
                add_issue(issues, "blocker", "production_prompt_missing", slide_no=slide_no)
            if not formal_entries:
                add_issue(issues, "blocker", "formal_text_missing_for_image_slide", slide_no=slide_no)
            if production_prompt and visual_prompt and production_prompt == visual_prompt:
                add_issue(issues, "blocker", "production_prompt_not_materialized", slide_no=slide_no)
            prompt_lower = production_prompt.lower()
            for context_field in ("audience", "language", "presentation_context"):
                context_value = text_value(generation_context.get(context_field))
                if context_value and context_value not in production_prompt:
                    add_issue(issues, "blocker", "production_prompt_generation_context_missing", slide_no=slide_no, field=context_field)
            if retry and "有界恢复策略" not in production_prompt and "retry" not in prompt_lower:
                add_issue(issues, "blocker", "production_prompt_retry_policy_missing", slide_no=slide_no)
            if ratio and ratio not in production_prompt:
                add_issue(issues, "blocker", "production_prompt_ratio_missing", slide_no=slide_no, ratio=ratio)
            for color in palette_hexes:
                if color not in prompt_lower:
                    add_issue(issues, "blocker", "production_prompt_palette_missing", slide_no=slide_no, color=color)
            if not re.search(r"逐字|verbatim|exact", production_prompt, re.IGNORECASE):
                add_issue(issues, "blocker", "production_prompt_verbatim_policy_missing", slide_no=slide_no)
            if not re.search(r"不得编造|不可编造|do not invent|no invented", production_prompt, re.IGNORECASE):
                add_issue(issues, "blocker", "production_prompt_no_fabrication_policy_missing", slide_no=slide_no)
            if not re.search(r"不要用代码|不得.*(补字|盖字)|禁止.*补字|禁止.*盖字|no code.*(text|overlay)|do not.*(patch|overlay).*text", production_prompt, re.IGNORECASE):
                add_issue(issues, "blocker", "production_prompt_no_code_overlay_policy_missing", slide_no=slide_no)
            for entry in formal_entries:
                if not entry["text"]:
                    add_issue(issues, "blocker", "formal_text_empty", slide_no=slide_no, text_id=entry["id"])
                elif PLACEHOLDER_RE.search(entry["text"]):
                    add_issue(issues, "blocker", "formal_text_placeholder", slide_no=slide_no, text_id=entry["id"])
                elif entry["text"] not in production_prompt:
                    add_issue(issues, "blocker", "production_prompt_copy_mismatch", slide_no=slide_no, text_id=entry["id"])
                if not text_value(entry.get("source_ref")):
                    add_issue(issues, "blocker", "formal_text_source_reference_missing", slide_no=slide_no, text_id=entry["id"])
            for content_text in content_text_entries(slide):
                if content_text not in production_prompt:
                    add_issue(issues, "blocker", "production_prompt_content_copy_mismatch", slide_no=slide_no, text=content_text)
            for annotation in diagram_annotation_entries(slide):
                if annotation["text"] and annotation["text"] not in production_prompt:
                    add_issue(issues, "blocker", "production_prompt_diagram_annotation_mismatch", slide_no=slide_no, text=annotation["text"])
            if framework and framework not in production_prompt:
                add_issue(issues, "blocker", "production_prompt_framework_missing", slide_no=slide_no, framework=framework)
            core_logic = text_value(slide.get("core_logic"))
            if core_logic and core_logic not in production_prompt:
                add_issue(issues, "blocker", "production_prompt_core_logic_missing", slide_no=slide_no)
        prompt_file = resolve_path(plan_path.parent, slide.get("prompt_file"))
        if slide.get("prompt_file") is not None and (prompt_file is None or not prompt_file.is_file()):
            add_issue(issues, "blocker", "plan_prompt_file_missing", slide_no=slide_no, path=str(prompt_file) if prompt_file else None)
        references = slide.get("reference_images") or []
        if not isinstance(references, list):
            add_issue(issues, "blocker", "reference_images_invalid", slide_no=slide_no)
            references = []
        for reference_index, reference in enumerate(references, start=1):
            if not reference_path(reference):
                add_issue(issues, "blocker", "reference_image_path_missing", slide_no=slide_no, reference=reference_index)
        if references and mode == "image-slide" and production_prompt:
            reference_text = production_prompt.lower()
            treatment = slide.get("reference_treatment")
            if not isinstance(treatment, dict):
                add_issue(issues, "blocker", "reference_treatment_missing", slide_no=slide_no)
                treatment = {}
            treatment_mode = text_value(treatment.get("mode"))
            if treatment_mode not in {"layout-only", "layout-and-style"}:
                add_issue(issues, "blocker", "reference_treatment_mode_invalid", slide_no=slide_no, observed=treatment_mode)
            if not text_value(treatment.get("source_role")):
                add_issue(issues, "blocker", "reference_treatment_source_role_missing", slide_no=slide_no)
            preserve = treatment.get("preserve")
            exclude = treatment.get("exclude")
            if not isinstance(preserve, list) or not any(text_value(item) for item in preserve):
                add_issue(issues, "blocker", "reference_treatment_preserve_missing", slide_no=slide_no)
            if not isinstance(exclude, list) or not any(text_value(item) for item in exclude):
                add_issue(issues, "blocker", "reference_treatment_exclude_missing", slide_no=slide_no)
            if treatment_mode == "layout-and-style" and not any("palette" in text_value(item).lower() or "配色" in text_value(item) for item in (preserve or [])):
                add_issue(issues, "blocker", "reference_style_treatment_palette_missing", slide_no=slide_no)
            if treatment_mode == "layout-only":
                if not ("只学布局" in production_prompt or "只参考排版" in production_prompt or "layout only" in reference_text):
                    add_issue(issues, "blocker", "reference_layout_only_policy_missing", slide_no=slide_no)
                if not ("不使用其配色" in production_prompt or "do not use its colors" in reference_text or "do not use its palette" in reference_text):
                    add_issue(issues, "blocker", "reference_color_isolation_policy_missing", slide_no=slide_no)
            else:
                if not ("布局+风格" in production_prompt or "layout-and-style" in reference_text or "layout and style" in reference_text):
                    add_issue(issues, "blocker", "reference_layout_style_policy_missing", slide_no=slide_no)
                if not ("保留" in production_prompt and ("配色" in production_prompt or "palette" in reference_text)):
                    add_issue(issues, "blocker", "reference_palette_preservation_policy_missing", slide_no=slide_no)
            if not ("不使用其文字" in production_prompt or "do not use its text" in reference_text):
                add_issue(issues, "blocker", "reference_text_isolation_policy_missing", slide_no=slide_no)
            if not ("不使用其品牌" in production_prompt or "do not use its branding" in reference_text or "do not use its brand" in reference_text):
                add_issue(issues, "blocker", "reference_brand_isolation_policy_missing", slide_no=slide_no)
        slide_summaries.append({
            "slide_no": slide_no,
            "page_type": page_type,
            "visual_framework": framework,
            "density_profile": profile,
            "modules": modules,
            "minimum_bullets": min_bullets,
            "info_points": info_points,
            "formal_text_count": len(formal_entries),
            "prompt_file": str(prompt_file) if prompt_file else None,
            "layout_blueprint_zones": len(blueprint.get("zones") or []) if isinstance(blueprint, dict) and isinstance(blueprint.get("zones"), list) else 0,
            "keyword_emphasis_items": len((slide.get("keyword_emphasis") or {}).get("items") or []) if isinstance(slide.get("keyword_emphasis"), dict) else 0,
            "diagram_annotation_count": len(diagram_annotation_entries(slide)),
            "detailed_content_paragraph_count": len(detailed_content),
            "reference_image_count": len(references),
            "reference_treatment_mode": text_value((slide.get("reference_treatment") or {}).get("mode")) if isinstance(slide.get("reference_treatment"), dict) else None,
            "module_details": module_summaries,
        })
    if slide_numbers and sorted(slide_numbers) != list(range(1, max(slide_numbers) + 1)):
        add_issue(issues, "blocker", "plan_slide_numbers_not_contiguous", observed=sorted(slide_numbers))
    manifest_value = args.manifest or (plan.get("evidence_manifest") if args.require_evidence else None)
    manifest_path = resolve_path(plan_path.parent, manifest_value)
    evidence = None
    if args.require_evidence or manifest_value:
        if manifest_path is None or not manifest_path.is_file():
            add_issue(issues, "blocker", "generation_manifest_missing", path=str(manifest_path) if manifest_path else None)
        else:
            evidence = validate_evidence(plan_path, plan, manifest_path, issues, args.require_evidence)
    blockers = [item for item in issues if item.get("severity") == "blocker"]
    result = {
        "schema": "ai-ppt-plus/visual-generation-validation/v1",
        "valid": not blockers,
        "technical_valid": not blockers,
        "status": "passed" if not blockers else "blocked",
        "plan_path": str(plan_path),
        "plan_sha256": sha256(plan_path),
        "project_id": plan.get("project_id"),
        "route": plan.get("route"),
        "mode": mode,
        "canvas": canvas,
        "density_profile": density_profile,
        "generation_context": generation_context,
        "retry_policy": retry,
        "page_count": page_count,
        "framework_count": len(frameworks),
        "slides": slide_summaries,
        "evidence": evidence,
        "issues": issues,
        "human_visual_review_required": True,
        "release_eligible": False,
    }
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
