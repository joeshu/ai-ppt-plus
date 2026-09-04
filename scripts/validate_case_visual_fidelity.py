#!/usr/bin/env python3
"""Validate the visual-fidelity contract for a reference reconstruction.

Native object counts are necessary but not sufficient.  This gate binds the
candidate to the approved reference, checks declared render thresholds, and
requires independent imagegen assets plus source-bound typography evidence.
Synthetic native controls are useful diagnostics, but they are never valid
reconstruction candidates.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "ai-ppt-plus/case-visual-fidelity/v1"
DEFAULT_VISUAL_THRESHOLDS = {
    "min_global_ssim": 0.40,
    "min_blurred_layout_ssim": 0.60,
    "min_pixel_fidelity_score": 0.82,
}
DEFAULT_REQUIRED_ORIGIN = "reference-reconstruction"


def _issue(issues: list[dict[str, Any]], code: str, message: str, **detail: Any) -> None:
    item: dict[str, Any] = {"severity": "blocker", "code": code, "message": message}
    item.update(detail)
    issues.append(item)


def _flatten_tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for child in value.values():
            result.extend(_flatten_tokens(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_flatten_tokens(child))
        return result
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (str, int, float)):
        token = str(value).strip()
        return [token] if token else []
    return []


def _valid_bbox(value: Any) -> bool:
    """Validate the repository's [x, y, width, height] bbox convention."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    try:
        x, y, width, height = [float(item) for item in value]
    except (TypeError, ValueError):
        return False
    return x >= 0 and y >= 0 and width > 0 and height > 0


def _font_family(spec: dict[str, Any]) -> str:
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    value = style.get("font_family") or style.get("font") or spec.get("font_family") or spec.get("font")
    return str(value).strip() if value is not None else ""


def _font_size(spec: dict[str, Any]) -> Any:
    style = spec.get("style") if isinstance(spec.get("style"), dict) else {}
    for key in ("size_pt", "size", "size_px", "size_ratio", "size_pct"):
        value = style.get(key) if style.get(key) is not None else spec.get(key)
        if value is not None:
            return value
    return None


def _text_specs(text_manifest: Any) -> list[dict[str, Any]]:
    if not isinstance(text_manifest, dict):
        return []
    specs: list[dict[str, Any]] = []
    for slide in text_manifest.get("slides", []):
        if not isinstance(slide, dict):
            continue
        for item in slide.get("text_specs", []):
            if isinstance(item, dict):
                specs.append(item)
    return specs


def _thresholds(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, float]:
    case_policy = case.get("quality_gates") if isinstance(case.get("quality_gates"), dict) else {}
    case_visual = case_policy.get("visual") if isinstance(case_policy.get("visual"), dict) else {}
    policy_visual = policy.get("visual") if isinstance(policy.get("visual"), dict) else {}
    source = dict(DEFAULT_VISUAL_THRESHOLDS)
    source.update({key: value for key, value in policy_visual.items() if isinstance(value, (int, float))})
    source.update({key: value for key, value in case_visual.items() if isinstance(value, (int, float))})
    return source


def validate_case_visual_fidelity(
    case: dict[str, Any],
    *,
    visual: dict[str, Any],
    reference_sha256: str | None,
    candidate_origin: str | None,
    reference_binding: dict[str, Any] | None,
    asset_evidence: dict[str, Any] | None,
    typography_evidence: dict[str, Any] | None,
    text_manifest: dict[str, Any] | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a hard, machine-readable fidelity decision for one case."""
    policy = policy if isinstance(policy, dict) else {}
    reconstruction = policy.get("reconstruction") if isinstance(policy.get("reconstruction"), dict) else {}
    case_reconstruction = case.get("quality_gates", {}).get("reconstruction", {}) if isinstance(case.get("quality_gates"), dict) else {}
    if not isinstance(case_reconstruction, dict):
        case_reconstruction = {}

    required_origin = str(
        case_reconstruction.get("required_candidate_origin")
        or reconstruction.get("required_candidate_origin")
        or DEFAULT_REQUIRED_ORIGIN
    )
    require_binding = bool(
        case_reconstruction.get("require_reference_binding", reconstruction.get("require_reference_binding", True))
    )
    require_assets = bool(
        case_reconstruction.get("require_independent_visual_assets", reconstruction.get("require_independent_visual_assets", True))
    )
    require_source_bbox = bool(
        case_reconstruction.get("require_source_bbox", reconstruction.get("require_source_bbox", True))
    )
    require_font_manifest = bool(
        case_reconstruction.get("require_font_manifest", reconstruction.get("require_font_manifest", True))
    )
    exact_once = bool(case_reconstruction.get("formal_text_exact_once", reconstruction.get("formal_text_exact_once", True)))

    thresholds = _thresholds(case, policy)
    metrics = visual.get("metrics") if isinstance(visual.get("metrics"), dict) else {}
    issues: list[dict[str, Any]] = []

    if visual.get("valid") is not True:
        _issue(issues, "visual_compare_invalid", "the raw reference comparison did not pass", compare_issues=visual.get("issues", []))
    for key, minimum in thresholds.items():
        if not key.startswith("min_"):
            continue
        metric = key[4:]
        observed = metrics.get(metric)
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            _issue(issues, "visual_metric_missing", f"missing required visual metric: {metric}", metric=metric, minimum=minimum)
        elif observed < minimum:
            _issue(issues, "visual_metric_below_threshold", f"{metric} is below the approved minimum", metric=metric, observed=observed, minimum=minimum)

    if candidate_origin != required_origin:
        _issue(issues, "candidate_origin_not_reference_reconstruction", "the candidate is not declared as a reference reconstruction", expected=required_origin, observed=candidate_origin)

    binding = reference_binding if isinstance(reference_binding, dict) else {}
    declared_hash = binding.get("reference_sha256")
    if require_binding and binding.get("bound") is not True:
        _issue(issues, "reference_binding_missing", "candidate evidence is not bound to the approved reference")
    if require_binding and reference_sha256 and declared_hash != reference_sha256:
        _issue(issues, "reference_hash_mismatch", "candidate evidence points at a different reference", expected=reference_sha256, observed=declared_hash)

    assets = asset_evidence if isinstance(asset_evidence, dict) else {}
    if require_assets:
        if not assets.get("imagegen_assets_manifest"):
            _issue(issues, "imagegen_assets_manifest_missing", "icon/illustration/gradient evidence must name the final imagegen asset manifest")
        count = assets.get("independent_asset_count")
        valid_count = isinstance(count, (int, float)) and not isinstance(count, bool) and count >= 1
        if not valid_count:
            _issue(issues, "independent_visual_assets_missing", "the candidate contains no independently movable visual asset")
        asset_ids = assets.get("asset_ids")
        required_ids = int(count) if valid_count else 0
        observed_ids = len([item for item in asset_ids if str(item).strip()]) if isinstance(asset_ids, list) else 0
        if not isinstance(asset_ids, list) or observed_ids < required_ids:
            _issue(issues, "independent_asset_ids_missing", "every independent visual asset needs a stable asset ID", required=required_ids, observed=observed_ids)
        if assets.get("all_assets_text_free") is not True:
            _issue(issues, "asset_text_boundary_missing", "visual assets must be text-free and formal text must remain native")

    text_evidence = typography_evidence if isinstance(typography_evidence, dict) else {}
    specs = _text_specs(text_manifest)
    contents = [str(item.get("content", "")).strip() for item in specs if str(item.get("content", "")).strip()]
    counts = Counter(contents)
    formal = [str(item).strip() for item in case.get("formal_text", []) if str(item).strip()]
    if not specs:
        _issue(issues, "text_manifest_missing", "formal text geometry and style evidence is missing")

    actual_source_bbox_count = sum(1 for item in specs if _valid_bbox(item.get("source_bbox")))
    if require_source_bbox:
        if actual_source_bbox_count < len(formal):
            _issue(issues, "text_source_bbox_incomplete", "every formal text item needs a source bounding box", required=len(formal), observed=actual_source_bbox_count)
        missing_boxes = [item.get("object_id") for item in specs if not _valid_bbox(item.get("source_bbox"))]
        if missing_boxes:
            _issue(issues, "text_source_bbox_missing", "some text objects are not source-bound", object_ids=missing_boxes[:20], omitted=max(0, len(missing_boxes) - 20))

    if require_font_manifest and not text_evidence.get("font_manifest"):
        _issue(issues, "font_manifest_missing", "font family and size claims need a resolved font manifest")

    missing_fonts = [item.get("object_id") for item in specs if str(item.get("content", "")).strip() and not _font_family(item)]
    if missing_fonts:
        _issue(issues, "text_font_missing", "every formal text object needs a resolved font family", object_ids=missing_fonts[:20], omitted=max(0, len(missing_fonts) - 20))
    invalid_sizes = []
    for item in specs:
        if not str(item.get("content", "")).strip():
            continue
        value = _font_size(item)
        try:
            valid_size = value is not None and not isinstance(value, bool) and float(value) > 0
        except (TypeError, ValueError):
            valid_size = False
        if not valid_size:
            invalid_sizes.append(item.get("object_id"))
    if invalid_sizes:
        _issue(issues, "text_font_size_missing", "every formal text object needs a positive resolved font size", object_ids=invalid_sizes[:20], omitted=max(0, len(invalid_sizes) - 20))

    for value in formal:
        count = counts.get(value, 0)
        if count == 0:
            _issue(issues, "formal_text_missing", "approved formal text is absent from the candidate", text=value)
        elif exact_once and count != 1:
            _issue(issues, "formal_text_not_exact_once", "approved formal text is duplicated", text=value, observed=count)

    allowed = set(formal)
    allowed.update(_flatten_tokens(case.get("data", {})))
    quality_gates = case.get("quality_gates") if isinstance(case.get("quality_gates"), dict) else {}
    allowed.update(str(item).strip() for item in quality_gates.get("approved_text", []) if str(item).strip())
    unapproved = sorted({item for item in contents if item not in allowed})
    if unapproved:
        _issue(issues, "unapproved_formal_text", "candidate contains text outside the case copy/data authority", text=unapproved[:30], omitted=max(0, len(unapproved) - 30))

    return {
        "schema": SCHEMA,
        "valid": not issues,
        "case_id": case.get("case_id"),
        "candidate_origin": candidate_origin,
        "reference_binding": binding,
        "thresholds": thresholds,
        "metrics": metrics,
        "evidence": {
            "asset": assets,
            "typography": text_evidence,
            "formal_text_count": len(formal),
            "observed_text_count": len(contents),
            "source_bbox_count": actual_source_bbox_count,
            "font_manifest": text_evidence.get("font_manifest"),
        },
        "issues": issues,
        "human_visual_review_required": True,
        "acceptance": "accept-for-human-review" if not issues else "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="case-suite case JSON")
    parser.add_argument("evidence", help="candidate evidence JSON")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    result = validate_case_visual_fidelity(
        case,
        visual=evidence.get("visual", {}),
        reference_sha256=evidence.get("reference_sha256"),
        candidate_origin=evidence.get("candidate_origin"),
        reference_binding=evidence.get("reference_binding"),
        asset_evidence=evidence.get("asset_evidence"),
        typography_evidence=evidence.get("typography_evidence"),
        text_manifest=evidence.get("text_manifest"),
        policy=evidence.get("policy"),
    )
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": result["valid"], "issues": len(result["issues"])}, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
