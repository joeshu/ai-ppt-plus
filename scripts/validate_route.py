#!/usr/bin/env python3
"""Validate the mutually exclusive visual-creation/reference-reconstruction route."""

import argparse
import hashlib
import json
from pathlib import Path


ROUTES = {"visual-creation", "reference-reconstruction"}
STATUSES = {"decided", "needs_user", "blocked"}
AUTHORITIES = {"approved_outline", "user_transcription", "transcription_pending_confirmation"}


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
    if data.get("schema") not in {None, "ai-ppt-plus/route-decision/v1"}:
        issues.append({"severity": "blocker", "code": "route_schema_invalid", "value": data.get("schema")})
    route = data.get("route")
    status = data.get("status")
    authority = data.get("visual_authority")
    formal_authority = data.get("formal_content_authority")
    if route not in ROUTES:
        issues.append({"severity": "blocker", "code": "route_invalid", "value": route})
    if status not in STATUSES:
        issues.append({"severity": "blocker", "code": "route_status_invalid", "value": status})
    if formal_authority not in AUTHORITIES:
        issues.append({"severity": "blocker", "code": "formal_content_authority_invalid", "value": formal_authority})
    expected_authority = {"visual-creation": "generated_visual_intermediate", "reference-reconstruction": "approved_reference_image"}.get(route)
    if expected_authority and authority != expected_authority:
        issues.append({"severity": "blocker", "code": "visual_authority_route_conflict", "expected": expected_authority, "observed": authority})
    expected_generation = route == "visual-creation"
    if data.get("requires_image_generation") is not expected_generation:
        issues.append({"severity": "blocker", "code": "image_generation_requirement_conflict", "expected": expected_generation, "observed": data.get("requires_image_generation")})
    base = route_path.parent
    evidence = {"route_file": str(route_path), "reference_files": [], "visual_intermediate_manifest": None}
    if status in {"needs_user", "blocked"} and (not isinstance(data.get("reason"), str) or not data.get("reason", "").strip()):
        issues.append({"severity": "blocker", "code": "route_reason_missing"})
    if route == "visual-creation" and status == "decided":
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
            record = {"slide_no": slide_no, "path": str(ref_path), "sha256": item.get("sha256")}
            evidence["reference_files"].append(record)
            if not isinstance(item.get("sha256"), str) or not item.get("sha256"):
                issues.append({"severity": "blocker", "code": "reference_hash_missing", "slide_no": slide_no})
            if args.require_files:
                if not ref_path.is_file():
                    issues.append({"severity": "blocker", "code": "reference_file_missing", "slide_no": slide_no, "path": str(ref_path)})
                elif item.get("sha256") and sha256(ref_path) != item.get("sha256"):
                    issues.append({"severity": "blocker", "code": "reference_hash_mismatch", "slide_no": slide_no})
        if slide_numbers and sorted(slide_numbers) != list(range(1, max(slide_numbers) + 1)):
            issues.append({"severity": "blocker", "code": "reference_slide_numbers_not_contiguous", "observed": sorted(slide_numbers)})
    valid = not any(issue.get("severity") == "blocker" for issue in issues)
    result = {"schema": "ai-ppt-plus/route-validation/v1", "valid": valid, "route_file": str(route_path), "route_sha256": sha256(route_path), "route": route, "status": status, "visual_authority": authority, "formal_content_authority": formal_authority, "requires_image_generation": data.get("requires_image_generation"), "issues": issues, "evidence": evidence}
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
