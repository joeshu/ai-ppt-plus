#!/usr/bin/env python3
"""Run the deterministic AI PPT Plus verification pipeline.

The runner orchestrates existing gates around an already-authored PPTX. It
does not author slides, change formal text, update handoff state, or claim
human approval. All run outputs are isolated under `pipeline-runs/` unless an
explicit output directory is provided.

Usage: run_pipeline.py PROJECT_DIR --deck DECK.pptx --expected-pages N
       [--expected-ratio 1.7777778] [--font-dir DIR]
       [--region name=x,y,w,h ...] [--reference IMAGE | --reference-dir DIR]
       [--visual-threshold N]
       [--ocr-lang LANG] [--require-ocr] [--revision-label R4] [--require-cjk]
       [--route-decision ROUTE.json] [--require-route] [--require-editability]
       [--dpi N]
       [--strict-layout]
       [--output-dir RUN_DIR]
"""
import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


STEP_TIMEOUT_SECONDS = 600


def run_step(run_dir: Path, name: str, args, timeout: int = STEP_TIMEOUT_SECONDS):
    stdout_path = run_dir / f"{name}.stdout.txt"
    stderr_path = run_dir / f"{name}.stderr.txt"
    command = [sys.executable, *args]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = completed.returncode
        failure = None
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nstep timed out after {timeout}s"
        exit_code = 124
        failure = "timeout"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    result = {"name": name, "command": command, "exit_code": exit_code, "ok": exit_code == 0, "stdout": str(stdout_path.resolve()), "stderr": str(stderr_path.resolve()), "timeout_seconds": timeout}
    if failure:
        result["failure"] = failure
    return result


def load_report(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "status": "invalid", "issues": [{"code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}


def project_asset_requirements(project: Path) -> tuple[bool, bool]:
    """Read explicit icon/imagegen requirements without substring heuristics."""
    manifest = project / "slide-manifest.json"
    if not manifest.is_file():
        return False, False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, False
    if not isinstance(data, dict):
        return False, False
    slides = [slide for slide in data.get("slides", []) if isinstance(slide, dict)]
    requires_icon = data.get("requires_icon_assets") is True or any(slide.get("requires_icon_assets") is True for slide in slides)
    requires_imagegen = data.get("requires_imagegen_assets") is True or any(slide.get("requires_imagegen_assets") is True for slide in slides)
    return requires_icon, requires_imagegen


def summarize_report(name: str, path: Path, report: dict):
    summary = {
        "report": str(path.resolve()),
        "valid": report.get("valid"),
        "status": report.get("status"),
        "issues": report.get("issues", []),
    }
    if name == "render_visual_gate":
        summary.update({"expected_pages": report.get("expected_pages"), "observed_pages": len(report.get("pages", []))})
    elif name == "visual_comparison":
        summary.update({"reference": report.get("reference"), "reference_dir": report.get("reference_dir"), "metrics": report.get("metrics", {}), "aggregate": report.get("aggregate", {}), "compared_pages": len(report.get("pages", [])), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "ocr_text_check":
        summary.update({"language": report.get("language"), "slide_count": len(report.get("slides", [])), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "route_validation":
        summary.update({"route": report.get("route"), "visual_authority": report.get("visual_authority"), "formal_content_authority": report.get("formal_content_authority")})
    elif name == "manifest_validation":
        summary.update({"warnings": report.get("warnings", []), "editability_protocol": report.get("editability_protocol"), "editability": report.get("editability", [])})
    elif name == "visual_compare_qa":
        summary.update({"status": report.get("status", "diagnostic"), "ok": report.get("ok"), "resized_for_comparison": report.get("resized_for_comparison"), "preview_size": report.get("preview_size")})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--deck", required=True)
    parser.add_argument("--expected-pages", type=int, required=True)
    parser.add_argument("--expected-ratio", type=float)
    parser.add_argument("--font-dir")
    parser.add_argument("--region", action="append", default=[])
    reference_group = parser.add_mutually_exclusive_group()
    reference_group.add_argument("--reference", help="single approved reference image; only valid for one-page decks")
    reference_group.add_argument("--reference-dir", help="directory containing slide-1.png, slide-2.png, ... for multi-page decks")
    parser.add_argument("--visual-threshold", type=float)
    parser.add_argument("--ocr-lang")
    parser.add_argument("--require-ocr", action="store_true")
    parser.add_argument("--revision-label")
    parser.add_argument("--require-cjk", action="store_true", help="block when the font report cannot support CJK delivery")
    parser.add_argument("--route-decision", help="route-decision.json declaring visual authority")
    parser.add_argument("--require-route", action="store_true", help="require and validate a route decision before downstream gates")
    parser.add_argument("--require-editability", action="store_true", help="require typed L0-L5 object records in the slide manifest")
    parser.add_argument("--require-icon-assets", action="store_true", help="require B4/B5 icon asset and layer audits")
    parser.add_argument("--require-imagegen-assets", action="store_true", help="require per-page imagegen asset provenance")
    parser.add_argument("--object-manifest", help="canonical slide-object-manifest.json")
    parser.add_argument("--require-object-manifest", action="store_true", help="require and validate the canonical object inventory")
    parser.add_argument("--require-independent-panels", action="store_true", help="reverse-audit independently movable semantic panels")
    parser.add_argument("--expected-panel-count", type=int, help="expected semantic panel count")
    parser.add_argument("--require-panel-approval", action="store_true", help="require explicit human approval metadata for panel assets")
    parser.add_argument("--require-text-style-map", action="store_true", help="validate rich text/style records when present")
    parser.add_argument("--manifest-registry", help="canonical cross-manifest registry.json")
    parser.add_argument("--require-manifest-registry", action="store_true", help="require and validate the cross-manifest registry")
    parser.add_argument("--release", action="store_true", help="run the strict release gate after technical validation")
    parser.add_argument("--handoff", help="handoff.json; required by --release")
    parser.add_argument("--human-signoff", help="human-closeout.json; required by --release")
    parser.add_argument("--issue-log", help="issue-log.json passed to the release gate")
    parser.add_argument("--quality-score", type=float, help="human/automated quality score for --release")
    parser.add_argument("--quality-threshold", type=float, default=80, help="minimum quality score for --release")
    parser.add_argument("--require-embedded-fonts", action="store_true", help="require verified OOXML embedded fonts in strict release delivery")
    parser.add_argument("--target-review", help="WPS target-device review JSON; required by --release")
    parser.add_argument("--dpi", type=int, default=96, help="render DPI; same-ratio reference comparisons are normalized when pixel sizes differ")
    parser.add_argument("--strict-layout", action="store_true", help="treat layout-audit warnings (such as missing source_bbox) as blockers")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    deck = Path(args.deck).resolve()
    if args.release:
        # A release is a stronger profile than technical validation.  Make
        # the required evidence explicit instead of allowing a green run to
        # be mistaken for a delivered deck.
        args.require_route = True
        args.require_editability = True
        args.require_embedded_fonts = True
        args.require_cjk = True
        missing = []
        if not args.font_dir:
            missing.append("--font-dir")
        if not args.route_decision:
            missing.append("--route-decision")
        if not args.handoff:
            missing.append("--handoff")
        if not args.human_signoff:
            missing.append("--human-signoff")
        if not args.target_review:
            missing.append("--target-review")
        if args.quality_score is None:
            missing.append("--quality-score")
        if missing:
            result = {"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "technical_valid": False, "release_eligible": False, "code": "release_evidence_missing", "missing": missing}
            print(json.dumps(result, ensure_ascii=False))
            return 2
    if not project.is_dir() or not deck.is_file():
        print(json.dumps({"valid": False, "code": "project_or_deck_missing"}, ensure_ascii=False))
        return 3
    if args.release and not (project / "slide-manifest.json").is_file():
        result = {"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "technical_valid": False, "release_eligible": False, "code": "slide_manifest_missing", "message": "--release requires project/slide-manifest.json"}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if args.reference and args.expected_pages != 1:
        result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": False, "code": "single_reference_for_multipage", "message": "Use --reference-dir with slide-N.png files for multi-page decks"}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if args.require_route and not args.route_decision:
        result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": False, "code": "route_decision_missing", "message": "--require-route needs --route-decision"}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    route_data = None
    if args.route_decision:
        try:
            route_data = json.loads(Path(args.route_decision).read_text(encoding="utf-8"))
        except Exception:
            route_data = None
    if args.require_route and isinstance(route_data, dict) and route_data.get("route") == "reference-reconstruction":
        if not (args.reference or args.reference_dir):
            result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": False, "code": "reference_route_without_reference", "message": "reference-reconstruction requires --reference or --reference-dir for visual comparison"}
            print(json.dumps(result, ensure_ascii=False))
            return 2
        roster = route_data.get("reference_roster") or []
        if roster and len(roster) != args.expected_pages:
            result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": False, "code": "route_reference_page_count_mismatch", "expected_pages": args.expected_pages, "route_reference_pages": len(roster)}
            print(json.dumps(result, ensure_ascii=False))
            return 2
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = Path(args.output_dir).resolve() if args.output_dir else project / "pipeline-runs" / run_id
    if run_dir.exists():
        print(json.dumps({"valid": False, "code": "run_dir_exists", "path": str(run_dir)}, ensure_ascii=False))
        return 2
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir()
    render_dir = run_dir / "rendered"
    steps = []
    manifest_icon_required, manifest_imagegen_required = project_asset_requirements(project)
    icon_required = args.require_icon_assets or manifest_icon_required or (project / "icon-asset-manifest.json").is_file()
    imagegen_required = args.require_imagegen_assets or manifest_imagegen_required or (project / "imagegen-assets-manifest.json").is_file()
    if args.route_decision:
        route_args = [str(SCRIPT_DIR / "validate_route.py"), str(Path(args.route_decision).resolve()), "--require-files", "--report", str(run_dir / "route-validation.json")]
        steps.append(run_step(run_dir, "route", route_args))
    if args.handoff:
        steps.append(run_step(run_dir, "handoff", [str(SCRIPT_DIR / "validate_handoff.py"), str(Path(args.handoff).resolve()), "--report", str(run_dir / "handoff-validation.json")]))
    if args.revision_label:
        steps.append(run_step(run_dir, "revision-prepare", [str(SCRIPT_DIR / "revision_guard.py"), "prepare", str(project), "--deck", str(deck), "--label", args.revision_label]))
    steps.append(run_step(run_dir, "environment", [str(SCRIPT_DIR / "probe_environment.py"), "--output", str(run_dir / "environment-report.json")]))
    if args.font_dir or args.require_cjk:
        font_args = [str(SCRIPT_DIR / "probe_fonts.py"), "--output", str(run_dir / "font-report.json")]
        if args.font_dir:
            font_args.extend(["--font-dir", str(Path(args.font_dir).resolve())])
        font_step = run_step(run_dir, "fonts", font_args)
        if args.require_cjk and font_step["ok"]:
            font_report = json.loads((run_dir / "font-report.json").read_text(encoding="utf-8"))
            if not font_report.get("cjk_delivery_supported"):
                font_step["ok"] = False
                font_step["failure"] = "cjk_delivery_unsupported"
        steps.append(font_step)
        font_manifest = Path(args.font_dir).resolve() / "font-manifest.json" if args.font_dir else None
        if args.font_dir and (font_manifest.is_file() or args.require_cjk):
            font_asset_args = [str(SCRIPT_DIR / "validate_font_asset.py"), "--font-dir", str(Path(args.font_dir).resolve()), "--report", str(run_dir / "font-asset-validation.json")]
            if args.require_cjk:
                font_asset_args.append("--require-cjk")
            steps.append(run_step(run_dir, "font-asset", font_asset_args))
    layout_path = project / "layout.json"
    object_manifest = Path(args.object_manifest).resolve() if args.object_manifest else project / "slide-object-manifest.json"
    if args.require_object_manifest or object_manifest.is_file():
        object_args = [str(SCRIPT_DIR / "validate_object_manifest.py"), str(object_manifest), "--report", str(run_dir / "object-manifest-validation.json")]
        if args.require_independent_panels:
            object_args.append("--require-panels")
        steps.append(run_step(run_dir, "object-manifest", object_args))
    registry_path = Path(args.manifest_registry).resolve() if args.manifest_registry else project / "manifest-registry.json"
    registry_enabled = bool(args.manifest_registry or registry_path.is_file())
    if args.require_manifest_registry and not registry_path.is_file():
        steps.append({"name": "manifest-registry", "command": [], "exit_code": 2, "ok": False, "failure": "manifest_registry_missing", "stdout": "", "stderr": ""})
    elif registry_enabled:
        registry_args = [str(SCRIPT_DIR / "manifest_registry.py"), "validate", str(registry_path), "--deck", str(deck), "--report", str(run_dir / "manifest-registry-validation.json")]
        if args.require_manifest_registry:
            registry_args.append("--require-gates")
        steps.append(run_step(run_dir, "manifest-registry", registry_args))
    if args.reference:
        if layout_path.is_file():
            layout_args = [str(SCRIPT_DIR / "layout_guard.py"), str(Path(args.reference).resolve()), str(layout_path)]
            if args.strict_layout:
                layout_args.append("--strict")
            layout_step = run_step(run_dir, "layout-guard", layout_args)
        else:
            layout_step = {"name": "layout-guard", "command": [], "exit_code": 2, "ok": False,
                           "failure": "layout_json_missing", "stdout": "", "stderr": ""}
        (run_dir / "layout-guard.json").write_text(json.dumps({
            "schema": "ai-ppt-plus/layout-guard-run/v1",
            "valid": layout_step["ok"],
            "status": "passed" if layout_step["ok"] else "blocked",
            "stdout": layout_step["stdout"],
            "stderr": layout_step["stderr"],
            "issues": [] if layout_step["ok"] else [{"code": "layout_guard_failed"}],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        steps.append(layout_step)
    if imagegen_required:
        steps.append(run_step(run_dir, "imagegen-assets", [str(SCRIPT_DIR / "validate_imagegen_assets_manifest.py"), str(project / "imagegen-assets-manifest.json"), "--report", str(run_dir / "imagegen-assets-validation.json")]))
    if icon_required:
        steps.append(run_step(run_dir, "icon-assets", [str(SCRIPT_DIR / "validate_icon_assets.py"), str(project / "icon-asset-manifest.json"), "--report", str(run_dir / "icon-assets-validation.json")]))
        steps.append(run_step(run_dir, "icon-layers", [str(SCRIPT_DIR / "audit_icon_layers.py"), str(project / "icon-asset-manifest.json"), "--report", str(run_dir / "icon-layer-audit.json")]))
    inspection_path = run_dir / "inspection.json"
    render_report_path = run_dir / "render-report.json"
    steps.append(run_step(run_dir, "inspection", [str(SCRIPT_DIR / "inspect_pptx.py"), str(deck), "--report", str(inspection_path)]))
    if args.require_object_manifest or object_manifest.is_file():
        audit_args = [str(SCRIPT_DIR / "inspect_editable_objects.py"), str(deck), "--object-manifest", str(object_manifest), "--report", str(run_dir / "editable-object-audit.json")]
        if args.require_independent_panels:
            audit_args.append("--require-independent-panels")
        steps.append(run_step(run_dir, "editable-object-audit", audit_args))
    render_args = [str(SCRIPT_DIR / "render_pptx.py"), str(deck), "--output-dir", str(render_dir), "--dpi", str(args.dpi), "--report", str(render_report_path)]
    if args.font_dir:
        render_args.extend(["--font-dir", str(Path(args.font_dir).resolve())])
    steps.append(run_step(run_dir, "render", render_args))
    visual_args = [str(SCRIPT_DIR / "validate_render.py"), str(render_dir), "--expected-pages", str(args.expected_pages), "--report", str(run_dir / "render-visual-gate.json")]
    for region in args.region:
        visual_args.extend(["--region", region])
    steps.append(run_step(run_dir, "render-visual-gate", visual_args))
    if args.font_dir or args.require_cjk:
        font_delivery_args = [str(SCRIPT_DIR / "validate_font_delivery.py"), "--font-report", str(run_dir / "font-report.json"), "--inspection", str(inspection_path), "--render-report", str(render_report_path), "--render-visual-gate", str(run_dir / "render-visual-gate.json"), "--profile", "wps", "--report", str(run_dir / "font-delivery-validation.json")]
        if (run_dir / "font-asset-validation.json").is_file():
            font_delivery_args.extend(["--font-asset-report", str(run_dir / "font-asset-validation.json")])
        if args.target_review:
            font_delivery_args.extend(["--target-review", str(Path(args.target_review).resolve())])
        if args.release:
            font_delivery_args.extend(["--require-embedded", "--require-target-review"])
        steps.append(run_step(run_dir, "font-delivery", font_delivery_args))
    if args.reference:
        comparison_args = [str(SCRIPT_DIR / "compare_visual.py"), str(render_dir / "slide-1.png"), str(Path(args.reference).resolve()), "--report", str(run_dir / "visual-comparison.json")]
        if args.visual_threshold is not None:
            comparison_args.extend(["--threshold", str(args.visual_threshold)])
        steps.append(run_step(run_dir, "visual-comparison", comparison_args))
    elif args.reference_dir:
        comparison_args = [str(SCRIPT_DIR / "compare_visual_deck.py"), str(render_dir), str(Path(args.reference_dir).resolve()), "--report", str(run_dir / "visual-comparison.json")]
        if args.visual_threshold is not None:
            comparison_args.extend(["--threshold", str(args.visual_threshold)])
        steps.append(run_step(run_dir, "visual-comparison", comparison_args))
    if args.reference and layout_path.is_file() and (render_dir / "slide-1.png").is_file():
        steps.append(run_step(run_dir, "visual-compare-qa", [str(SCRIPT_DIR / "visual_compare_qa.py"), str(Path(args.reference).resolve()), str(render_dir / "slide-1.png"), "--out-dir", str(run_dir / "visual-qa")]))
    if args.ocr_lang or args.require_ocr:
        ocr_args = [str(SCRIPT_DIR / "ocr_text_check.py"), str(deck), str(render_dir), "--lang", args.ocr_lang or "eng", "--report", str(run_dir / "ocr-text-check.json")]
        if args.require_ocr:
            ocr_args.append("--require-ocr")
        steps.append(run_step(run_dir, "ocr-text-check", ocr_args))
    panel_manifest = project / "panel-asset-manifest.json"
    panel_gate_required = panel_manifest.is_file() or args.require_independent_panels or args.require_panel_approval
    if panel_gate_required:
        panel_args = [str(SCRIPT_DIR / "validate_panel_assets.py"), str(panel_manifest), "--assets-dir", str(project), "--report", str(run_dir / "panel-assets-validation.json"), "--strict"]
        panel_args.append("--require-approved")
        if args.require_independent_panels:
            panel_args.append("--require-independent")
        if args.expected_panel_count is not None:
            panel_args.extend(["--expected-count", str(args.expected_panel_count)])
        steps.append(run_step(run_dir, "panel-assets", panel_args))
    if args.require_text_style_map and layout_path.is_file():
        text_style_args = [str(SCRIPT_DIR / "validate_text_style_map.py"), str(layout_path), "--report", str(run_dir / "text-style-map-validation.json")]
        if args.strict_layout or args.release:
            text_style_args.extend(["--strict", "--require-source-bbox"])
        steps.append(run_step(run_dir, "text-style-map", text_style_args))
    manifest_args = [str(SCRIPT_DIR / "validate_manifest.py"), str(project / "slide-manifest.json"), "--kind", "slide", "--report", str(run_dir / "manifest-validation.json")]
    if args.require_editability:
        manifest_args.append("--require-editability")
    asset_manifest = project / "asset-manifest.json"
    if asset_manifest.is_file():
        manifest_args.extend(["--asset-manifest", str(asset_manifest)])
    steps.append(run_step(run_dir, "manifest", manifest_args))
    project_args = [str(SCRIPT_DIR / "validate_project.py"), str(project), "--deck", str(deck), "--inspection", str(inspection_path), "--render-report", str(render_report_path), "--render-visual-gate", str(run_dir / "render-visual-gate.json"), "--manifest-validation", str(run_dir / "manifest-validation.json"), "--report", str(run_dir / "project-validation.json")]
    if args.require_editability:
        project_args.append("--require-editability")
    if args.route_decision:
        project_args.extend(["--route-validation", str(run_dir / "route-validation.json")])
    if args.require_route:
        project_args.append("--require-route")
    if args.expected_ratio is not None:
        project_args.extend(["--expected-ratio", str(args.expected_ratio)])
    if args.reference or args.reference_dir:
        project_args.extend(["--visual-comparison", str(run_dir / "visual-comparison.json")])
    if args.ocr_lang or args.require_ocr:
        project_args.extend(["--ocr-report", str(run_dir / "ocr-text-check.json")])
    steps.append(run_step(run_dir, "project", project_args))
    report_entries = [
        {"report_type": "environment", "path": "environment-report.json", "required": True, "stage": "intake"},
        {"report_type": "inspection", "path": "inspection.json", "required": True, "stage": "validated"},
        {"report_type": "render", "path": "render-report.json", "required": True, "stage": "rendered"},
        {"report_type": "render-visual-gate", "path": "render-visual-gate.json", "required": True, "stage": "validated"},
        {"report_type": "manifest-validation", "path": "manifest-validation.json", "required": True, "stage": "validated"},
        {"report_type": "project-validation", "path": "project-validation.json", "required": True, "stage": "validated"},
    ]
    if registry_enabled or args.require_manifest_registry:
        report_entries.append({"report_type": "manifest-registry-validation", "path": "manifest-registry-validation.json", "required": args.require_manifest_registry, "stage": "validated"})
    if args.require_object_manifest or object_manifest.is_file():
        report_entries.extend([
            {"report_type": "object-manifest-validation", "path": "object-manifest-validation.json", "required": True, "stage": "validated"},
            {"report_type": "editable-object-audit", "path": "editable-object-audit.json", "required": True, "stage": "validated"},
        ])
    if panel_gate_required:
        report_entries.append({"report_type": "panel-assets-validation", "path": "panel-assets-validation.json", "required": True, "stage": "validated"})
    if args.require_text_style_map and layout_path.is_file():
        report_entries.append({"report_type": "text-style-map-validation", "path": "text-style-map-validation.json", "required": True, "stage": "validated"})
    if imagegen_required:
        report_entries.append({"report_type": "imagegen-assets-validation", "path": "imagegen-assets-validation.json", "required": True, "stage": "validated"})
    if icon_required:
        report_entries.extend([
            {"report_type": "icon-assets-validation", "path": "icon-assets-validation.json", "required": True, "stage": "validated"},
            {"report_type": "icon-layer-audit", "path": "icon-layer-audit.json", "required": True, "stage": "validated"},
        ])
    if args.reference and layout_path.is_file():
        report_entries.append({"report_type": "layout-guard", "path": "layout-guard.json", "required": True, "stage": "validated"})
        if (render_dir / "slide-1.png").is_file():
            report_entries.append({"report_type": "visual-compare-qa", "path": "visual-qa/report.json", "required": True, "stage": "validated"})
    if args.font_dir or args.require_cjk:
        report_entries.append({"report_type": "font", "path": "font-report.json", "required": True, "stage": "intake"})
    if (run_dir / "font-asset-validation.json").is_file():
        report_entries.append({"report_type": "font-asset-validation", "path": "font-asset-validation.json", "required": True, "stage": "intake"})
    if (run_dir / "font-delivery-validation.json").is_file():
        report_entries.append({"report_type": "font-delivery-validation", "path": "font-delivery-validation.json", "required": True, "stage": "validated"})
    if args.route_decision:
        report_entries.append({"report_type": "route-validation", "path": "route-validation.json", "required": args.require_route, "stage": "design-system-ready"})
    if args.handoff:
        report_entries.append({"report_type": "handoff-validation", "path": "handoff-validation.json", "required": True, "stage": "validated"})
    if args.reference or args.reference_dir:
        report_entries.append({"report_type": "visual-comparison", "path": "visual-comparison.json", "required": True, "stage": "validated"})
    if args.ocr_lang or args.require_ocr:
        report_entries.append({"report_type": "ocr-text-check", "path": "ocr-text-check.json", "required": args.require_ocr, "stage": "validated"})
    step_status = {step["name"]: step["ok"] for step in steps}
    for entry in report_entries:
        step_name = {"render-visual-gate": "render-visual-gate", "manifest-validation": "manifest", "manifest-registry-validation": "manifest-registry", "project-validation": "project", "project-report-aggregate": "project-report-aggregate", "visual-comparison": "visual-comparison", "visual-compare-qa": "visual-compare-qa", "layout-guard": "layout-guard", "imagegen-assets-validation": "imagegen-assets", "icon-assets-validation": "icon-assets", "icon-layer-audit": "icon-layers", "ocr-text-check": "ocr-text-check", "route-validation": "route", "handoff-validation": "handoff", "font": "fonts", "font-asset-validation": "font-asset", "font-delivery-validation": "font-delivery", "environment": "environment", "inspection": "inspection", "render": "render", "object-manifest-validation": "object-manifest", "editable-object-audit": "editable-object-audit", "panel-assets-validation": "panel-assets", "text-style-map-validation": "text-style-map"}.get(entry["report_type"])
        if step_name in step_status:
            entry["step_ok"] = step_status[step_name]
    report_index = {"schema": "ai-ppt-plus/report-index/v1", "project_id": project.name, "revision": args.revision_label or "working", "stage": "validated", "deck_path": str(deck), "deck_sha256": sha256(deck), "reports": report_entries}
    (run_dir / "report-index.json").write_text(json.dumps(report_index, ensure_ascii=False, indent=2), encoding="utf-8")
    steps.append(run_step(run_dir, "project-report-aggregate", [str(SCRIPT_DIR / "aggregate_project_reports.py"), str(run_dir / "report-index.json"), "--report", str(run_dir / "project-report.json")]))
    if args.release:
        signoff_path = Path(args.human_signoff).resolve()
        steps.append(run_step(run_dir, "signoff-validation", [str(SCRIPT_DIR / "validate_signoff.py"), str(signoff_path), "--report", str(run_dir / "signoff-validation.json")]))
        release_args = [
            str(SCRIPT_DIR / "delivery_check.py"),
            str(deck),
            "--inspection", str(inspection_path),
            "--render-report", str(render_report_path),
            "--manifest", str(project / "slide-manifest.json"),
            "--handoff", str(Path(args.handoff).resolve()),
            "--human-signoff", str(signoff_path),
            "--signoff-report", str(run_dir / "signoff-validation.json"),
            "--route-validation", str(run_dir / "route-validation.json"),
            "--require-route",
            "--manifest-validation", str(run_dir / "manifest-validation.json"),
            "--require-editability",
            "--require-embedded-fonts",
            "--font-delivery-report", str(run_dir / "font-delivery-validation.json"),
            "--require-font-delivery",
            "--project-report", str(run_dir / "project-report.json"),
            "--require-project-report",
            "--render-visual-gate", str(run_dir / "render-visual-gate.json"),
            "--expected-slides", str(args.expected_pages),
            "--quality-score", str(args.quality_score),
            "--quality-threshold", str(args.quality_threshold),
            "--output", str(run_dir / "release-check.json"),
        ]
        if args.issue_log:
            release_args.extend(["--issue-log", str(Path(args.issue_log).resolve())])
        if args.expected_ratio is not None:
            release_args.extend(["--expected-ratio", str(args.expected_ratio)])
        if args.reference or args.reference_dir:
            release_args.extend(["--visual-comparison", str(run_dir / "visual-comparison.json")])
        if args.ocr_lang or args.require_ocr:
            release_args.extend(["--ocr-report", str(run_dir / "ocr-text-check.json")])
        steps.append(run_step(run_dir, "release-check", release_args))
    failed = [step["name"] for step in steps if not step["ok"]]
    technical_failed = [step["name"] for step in steps if not step["ok"] and step["name"] not in {"signoff-validation", "release-check"}]
    quality_evidence = {}
    for name, path in (
        ("render_visual_gate", run_dir / "render-visual-gate.json"),
        ("visual_comparison", run_dir / "visual-comparison.json"),
        ("ocr_text_check", run_dir / "ocr-text-check.json"),
        ("route_validation", run_dir / "route-validation.json"),
        ("manifest_validation", run_dir / "manifest-validation.json"),
        ("manifest_registry_validation", run_dir / "manifest-registry-validation.json"),
        ("imagegen_assets_validation", run_dir / "imagegen-assets-validation.json"),
        ("icon_assets_validation", run_dir / "icon-assets-validation.json"),
        ("icon_layer_audit", run_dir / "icon-layer-audit.json"),
        ("object_manifest_validation", run_dir / "object-manifest-validation.json"),
        ("editable_object_audit", run_dir / "editable-object-audit.json"),
        ("panel_assets_validation", run_dir / "panel-assets-validation.json"),
        ("text_style_map_validation", run_dir / "text-style-map-validation.json"),
        ("visual_compare_qa", run_dir / "visual-qa/report.json"),
        ("project_report_aggregate", run_dir / "project-report.json"),
        ("font_asset_validation", run_dir / "font-asset-validation.json"),
        ("font_delivery_validation", run_dir / "font-delivery-validation.json"),
        ("handoff_validation", run_dir / "handoff-validation.json"),
        ("signoff_validation", run_dir / "signoff-validation.json"),
        ("release_check", run_dir / "release-check.json"),
    ):
        report = load_report(path)
        if report is not None:
            quality_evidence[name] = summarize_report(name, path, report)
    quality_degradations = []
    ocr_report = quality_evidence.get("ocr_text_check")
    if ocr_report and ocr_report.get("status") == "unavailable":
        quality_degradations.append({"code": "ocr_unavailable", "language": ocr_report.get("language"), "requires_human_review": True})
    release_report = load_report(run_dir / "release-check.json")
    release_eligible = bool(args.release and release_report and release_report.get("status") == "passed")
    result = {"schema": "ai-ppt-plus/pipeline-run/v2", "valid": not failed, "technical_valid": not technical_failed, "release_profile": "strict" if args.release else "not_run", "release_eligible": release_eligible, "release_status": release_report.get("status") if release_report else "not_run", "run_id": run_id, "project": str(project), "deck": str(deck), "deck_sha256": sha256(deck), "run_dir": str(run_dir), "steps": steps, "failed_steps": failed, "technical_failed_steps": technical_failed, "next_state": "delivered" if release_eligible else "validated" if not failed else "revision-required", "human_visual_review_required": True, "human_signoff_required": True, "quality_evidence": quality_evidence, "quality_degradations": quality_degradations}
    (run_dir / "pipeline-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
