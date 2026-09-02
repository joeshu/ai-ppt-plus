#!/usr/bin/env python3
"""Validate the mutually exclusive visual-authority route decision.

Route-decision/v1 remains readable for existing projects. Route-decision/v2
adds the explicit ``native-authoring`` route used when the approved design
system and structured content are already available.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from atomic_output import atomic_write_json
from validate_engine_route import validate_engine_route_data


ROUTES = {"visual-creation", "reference-reconstruction", "native-authoring"}
ROUTE_SCHEMAS = {"ai-ppt-plus/route-decision/v1", "ai-ppt-plus/route-decision/v2"}
STATUSES = {"decided", "needs_user", "blocked"}
AUTHORITIES = {"approved_outline", "user_transcription", "transcription_pending_confirmation"}
VISUAL_GENERATION_MODES = {"image-slide", "layout-reference"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route_json")
    parser.add_argument("--require-files", action="store_true", help="require visual manifest/reference files and verify hashes")
    parser.add_argument("--expected-pages", type=int, help="require the roster to cover exactly this many pages")
    reference_group = parser.add_mutually_exclusive_group()
    reference_group.add_argument("--reference", help="compare the route roster with one external reference file")
    reference_group.add_argument("--reference-dir", help="compare the route roster with slide-N files in a reference directory")
    parser.add_argument("--require-confirmation", action="store_true", help="require confirmer identity/time for a decided route")
    parser.add_argument("--require-formal-content", action="store_true", help="block transcription-pending formal content")
    parser.add_argument("--require-engine-route", action="store_true", help="require the editable-first engine/fallback contract")
    parser.add_argument("--report")
    args = parser.parse_args()
    route_path = Path(args.route_json).resolve()
    try:
        data = json.loads(route_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = {"schema": "ai-ppt-plus/route-validation/v1", "valid": False, "issues": [{"severity": "blocker", "code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}
        print(json.dumps(result, ensure_ascii=False))
        return 3
    issues = []
    if not isinstance(data, dict):
        issues.append({"severity": "blocker", "code": "route_not_object"})
        data = {}
    engine_evidence = {}
    if args.require_engine_route:
        engine_issues, engine_evidence = validate_engine_route_data(data, strict=True)
        issues.extend(engine_issues)
    schema = data.get("schema")
    if schema not in ROUTE_SCHEMAS:
        issues.append({"severity": "blocker", "code": "route_schema_invalid", "value": data.get("schema")})
    route = data.get("route")
    status = data.get("status")
    authority = data.get("visual_authority")
    formal_authority = data.get("formal_content_authority")
    visual_generation_mode = data.get("visual_generation_mode")
    if route not in ROUTES:
        issues.append({"severity": "blocker", "code": "route_invalid", "value": route})
    if status not in STATUSES:
        issues.append({"severity": "blocker", "code": "route_status_invalid", "value": status})
    if formal_authority not in AUTHORITIES:
        issues.append({"severity": "blocker", "code": "formal_content_authority_invalid", "value": formal_authority})
    expected_authority = {
        "visual-creation": "generated_visual_intermediate",
        "reference-reconstruction": "approved_reference_image",
        "native-authoring": "approved_design_system",
    }.get(route)
    if expected_authority and authority != expected_authority:
        issues.append({"severity": "blocker", "code": "visual_authority_route_conflict", "expected": expected_authority, "observed": authority})
    if route == "visual-creation" and visual_generation_mode is None:
        visual_generation_mode = "layout-reference"
    if route == "visual-creation" and visual_generation_mode not in VISUAL_GENERATION_MODES:
        issues.append({"severity": "blocker", "code": "visual_generation_mode_invalid", "observed": visual_generation_mode})
    if route in {"reference-reconstruction", "native-authoring"} and "visual_generation_mode" in data:
        issues.append({"severity": "blocker", "code": "reference_route_visual_generation_mode_conflict", "observed": visual_generation_mode})
    if route == "native-authoring" and schema != "ai-ppt-plus/route-decision/v2":
        issues.append({"severity": "blocker", "code": "native_route_requires_v2", "observed": schema})
    expected_generation = route == "visual-creation"
    if not isinstance(data.get("requires_image_generation"), bool) or data.get("requires_image_generation") is not expected_generation:
        issues.append({"severity": "blocker", "code": "image_generation_requirement_conflict", "expected": expected_generation, "observed": data.get("requires_image_generation")})
    base = route_path.parent
    evidence = {"route_file": str(route_path), "reference_files": [], "external_reference_files": [], "visual_intermediate_manifest": None, "visual_generation_plan": None, "visual_generation_manifest": None}
    formal_content_ready = formal_authority in {"approved_outline", "user_transcription"}
    if status in {"needs_user", "blocked"}:
        issues.append({"severity": "blocker", "code": "route_not_ready", "status": status, "reason": data.get("reason")})
    if status in {"needs_user", "blocked"} and (not isinstance(data.get("reason"), str) or not data.get("reason", "").strip()):
        issues.append({"severity": "blocker", "code": "route_reason_missing"})
    if status == "decided":
        if not isinstance(data.get("project_id"), str) or not data.get("project_id", "").strip():
            issues.append({"severity": "blocker", "code": "project_id_missing"})
        if args.require_confirmation or status == "decided":
            for field in ("confirmed_by", "confirmed_at"):
                if not isinstance(data.get(field), str) or not data.get(field, "").strip():
                    issues.append({"severity": "blocker", "code": "route_confirmation_missing", "field": field})
        if not formal_content_ready:
            evidence["formal_content_ready"] = False
            if args.require_formal_content:
                issues.append({"severity": "blocker", "code": "formal_content_confirmation_pending", "authority": formal_authority})
        else:
            evidence["formal_content_ready"] = True
    if route == "visual-creation" and status == "decided":
        if data.get("reference_roster") not in (None, []):
            issues.append({"severity": "blocker", "code": "visual_route_reference_roster_conflict"})
        manifest = data.get("visual_intermediate_manifest")
        if not isinstance(manifest, str) or not manifest.strip():
            issues.append({"severity": "blocker", "code": "visual_intermediate_manifest_missing"})
        else:
            manifest_path = (base / manifest).resolve()
            evidence["visual_intermediate_manifest"] = str(manifest_path)
            if args.require_files and not manifest_path.is_file():
                issues.append({"severity": "blocker", "code": "visual_intermediate_manifest_missing_file", "path": str(manifest_path)})
            elif args.require_files:
                try:
                    visual_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    visual_manifest = {}
                    issues.append({"severity": "blocker", "code": "visual_intermediate_manifest_invalid", "message": f"{type(exc).__name__}: {exc}"})
                required = ("image_path", "generator_skill", "model_or_tool", "prompt_or_recipe", "review_status")
                for field in required:
                    if not isinstance(visual_manifest.get(field), str) or not visual_manifest.get(field).strip():
                        issues.append({"severity": "blocker", "code": "visual_generation_evidence_missing", "field": field})
                if visual_manifest.get("text_authority") not in {None, "none"}:
                    issues.append({"severity": "blocker", "code": "visual_text_authority_invalid", "observed": visual_manifest.get("text_authority")})
                image_path = visual_manifest.get("image_path")
                if isinstance(image_path, str) and image_path.strip() and not (manifest_path.parent / image_path).resolve().is_file():
                    issues.append({"severity": "blocker", "code": "visual_intermediate_image_missing", "path": str((manifest_path.parent / image_path).resolve())})
        if visual_generation_mode == "image-slide":
            plan_ref = data.get("visual_generation_plan")
            manifest_ref = data.get("visual_generation_manifest")
            if not isinstance(plan_ref, str) or not plan_ref.strip():
                issues.append({"severity": "blocker", "code": "visual_generation_plan_missing"})
            else:
                plan_path = (base / plan_ref).resolve()
                evidence["visual_generation_plan"] = str(plan_path)
                if args.require_files and not plan_path.is_file():
                    issues.append({"severity": "blocker", "code": "visual_generation_plan_missing_file", "path": str(plan_path)})
            if not isinstance(manifest_ref, str) or not manifest_ref.strip():
                issues.append({"severity": "blocker", "code": "visual_generation_manifest_missing"})
            else:
                generation_manifest_path = (base / manifest_ref).resolve()
                evidence["visual_generation_manifest"] = str(generation_manifest_path)
                if args.require_files and not generation_manifest_path.is_file():
                    issues.append({"severity": "blocker", "code": "visual_generation_manifest_missing_file", "path": str(generation_manifest_path)})
    if route == "native-authoring" and status == "decided":
        if data.get("reference_roster") not in (None, []):
            issues.append({"severity": "blocker", "code": "native_route_reference_roster_conflict"})
        forbidden_fields = ("visual_generation_plan", "visual_generation_manifest", "visual_intermediate_manifest")
        for field in forbidden_fields:
            if data.get(field) not in (None, "", []):
                issues.append({"severity": "blocker", "code": "native_route_visual_artifact_conflict", "field": field})
        native_manifest = data.get("native_content_manifest")
        if not isinstance(native_manifest, str) or not native_manifest.strip():
            issues.append({"severity": "blocker", "code": "native_content_manifest_missing"})
        else:
            native_manifest_path = (base / native_manifest).resolve()
            evidence["native_content_manifest"] = str(native_manifest_path)
            if args.require_files and not native_manifest_path.is_file():
                issues.append({"severity": "blocker", "code": "native_content_manifest_missing_file", "path": str(native_manifest_path)})
    if route == "reference-reconstruction" and status == "decided":
        roster = data.get("reference_roster")
        if not isinstance(roster, list) or not roster:
            issues.append({"severity": "blocker", "code": "reference_roster_missing"})
            roster = []
        slide_numbers = []
        for index, item in enumerate(roster):
            if not isinstance(item, dict):
                issues.append({"severity": "blocker", "code": "reference_roster_item_invalid", "index": index})
                continue
            slide_no = item.get("slide_no")
            if not isinstance(slide_no, int) or slide_no < 1:
                issues.append({"severity": "blocker", "code": "reference_slide_number_invalid", "index": index})
            elif slide_no in slide_numbers:
                issues.append({"severity": "blocker", "code": "reference_slide_number_duplicate", "slide_no": slide_no})
            else:
                slide_numbers.append(slide_no)
            ref = item.get("path")
            if not isinstance(ref, str) or not ref.strip():
                issues.append({"severity": "blocker", "code": "reference_path_missing", "index": index})
                continue
            ref_path = (base / ref).resolve()
            record = {
                "slide_no": slide_no,
                "path": str(ref_path),
                "sha256": item.get("sha256"),
                "comparison_path": None,
                "comparison_sha256": None,
                "derived_from_sha256": item.get("derived_from_sha256"),
                "comparison_transform": item.get("comparison_transform"),
            }
            evidence["reference_files"].append(record)
            if not isinstance(item.get("sha256"), str) or not SHA256_RE.fullmatch(item.get("sha256", "")):
                issues.append({"severity": "blocker", "code": "reference_hash_missing", "slide_no": slide_no})
            if args.require_files:
                if not ref_path.is_file():
                    issues.append({"severity": "blocker", "code": "reference_file_missing", "slide_no": slide_no, "path": str(ref_path)})
                elif item.get("sha256") and sha256(ref_path) != item.get("sha256"):
                    issues.append({"severity": "blocker", "code": "reference_hash_mismatch", "slide_no": slide_no})
            comparison_ref = item.get("comparison_path")
            if comparison_ref not in (None, ""):
                if not isinstance(comparison_ref, str):
                    issues.append({"severity": "blocker", "code": "comparison_reference_path_invalid", "slide_no": slide_no})
                    continue
                comparison_path = (base / comparison_ref).resolve()
                record["comparison_path"] = str(comparison_path)
                record["comparison_sha256"] = item.get("comparison_sha256")
                if not isinstance(item.get("comparison_sha256"), str) or not SHA256_RE.fullmatch(item.get("comparison_sha256", "")):
                    issues.append({"severity": "blocker", "code": "comparison_reference_hash_missing", "slide_no": slide_no})
                if item.get("derived_from_sha256") != item.get("sha256"):
                    issues.append({"severity": "blocker", "code": "comparison_reference_origin_mismatch", "slide_no": slide_no, "expected": item.get("sha256"), "observed": item.get("derived_from_sha256")})
                if not isinstance(item.get("comparison_transform"), str) or not item.get("comparison_transform", "").strip():
                    issues.append({"severity": "blocker", "code": "comparison_reference_transform_missing", "slide_no": slide_no})
                if args.require_files:
                    if not comparison_path.is_file():
                        issues.append({"severity": "blocker", "code": "comparison_reference_missing", "slide_no": slide_no, "path": str(comparison_path)})
                    elif item.get("comparison_sha256") and sha256(comparison_path) != item.get("comparison_sha256"):
                        issues.append({"severity": "blocker", "code": "comparison_reference_hash_mismatch", "slide_no": slide_no})
        if slide_numbers and sorted(slide_numbers) != list(range(1, max(slide_numbers) + 1)):
            issues.append({"severity": "blocker", "code": "reference_slide_numbers_not_contiguous", "observed": sorted(slide_numbers)})
        if args.expected_pages is not None and len(roster) != args.expected_pages:
            issues.append({"severity": "blocker", "code": "reference_page_count_mismatch", "expected": args.expected_pages, "observed": len(roster)})
        external_paths: list[tuple[int, Path]] = []
        if args.reference:
            external_paths = [(1, Path(args.reference).resolve())]
        elif args.reference_dir:
            root = Path(args.reference_dir).resolve()
            count = args.expected_pages or len(roster)
            external_paths = [(index, root / f"slide-{index}.png") for index in range(1, count + 1)]
        roster_by_slide = {item.get("slide_no"): item for item in roster if isinstance(item, dict)}
        for external_slide, external_path in external_paths:
            external_record = {"slide_no": external_slide, "path": str(external_path), "exists": external_path.is_file(), "sha256": sha256(external_path) if external_path.is_file() else None}
            evidence["external_reference_files"].append(external_record)
            item = roster_by_slide.get(external_slide)
            if item is None:
                issues.append({"severity": "blocker", "code": "external_reference_not_rostered", "slide_no": external_slide, "path": str(external_path)})
                continue
            roster_path = (base / str(item.get("path"))).resolve()
            if not external_path.is_file():
                issues.append({"severity": "blocker", "code": "external_reference_missing", "slide_no": external_slide, "path": str(external_path)})
            elif not roster_path.is_file():
                issues.append({"severity": "blocker", "code": "rostered_reference_missing", "slide_no": external_slide, "path": str(roster_path)})
            else:
                external_hash = sha256(external_path)
                accepted_hashes = {sha256(roster_path)}
                comparison_path = item.get("comparison_path")
                if isinstance(comparison_path, str) and comparison_path:
                    comparison_file = (base / comparison_path).resolve()
                    if comparison_file.is_file():
                        accepted_hashes.add(sha256(comparison_file))
                external_record["matches_rostered_source"] = external_hash == sha256(roster_path)
                external_record["matches_declared_comparison"] = external_hash in accepted_hashes - {sha256(roster_path)}
                if external_hash not in accepted_hashes:
                    issues.append({"severity": "blocker", "code": "external_reference_hash_mismatch", "slide_no": external_slide, "roster_path": str(roster_path), "external_path": str(external_path), "accepted_hashes": sorted(accepted_hashes)})
    valid = not any(issue.get("severity") == "blocker" for issue in issues)
    result = {"schema": "ai-ppt-plus/route-validation/v2" if schema == "ai-ppt-plus/route-decision/v2" else "ai-ppt-plus/route-validation/v1", "valid": valid, "ready_for_delivery": valid and formal_content_ready and status == "decided", "route_file": str(route_path), "route_sha256": sha256(route_path), "route": route, "status": status, "visual_authority": authority, "formal_content_authority": formal_authority, "visual_generation_mode": visual_generation_mode, "formal_content_ready": formal_content_ready, "requires_image_generation": data.get("requires_image_generation"), "engine_route": engine_evidence, "issues": issues, "evidence": evidence}
    if args.report:
        atomic_write_json(Path(args.report).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
