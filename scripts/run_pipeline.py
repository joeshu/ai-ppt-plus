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
       [--output-dir RUN_DIR]
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_step(run_dir: Path, name: str, args):
    stdout_path = run_dir / f"{name}.stdout.txt"
    stderr_path = run_dir / f"{name}.stderr.txt"
    completed = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return {"name": name, "command": [sys.executable, *args], "exit_code": completed.returncode, "ok": completed.returncode == 0, "stdout": str(stdout_path.resolve()), "stderr": str(stderr_path.resolve())}


def load_report(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "status": "invalid", "issues": [{"code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}


def project_mentions_icons(project: Path) -> bool:
    """Detect icon-bearing manifests so icon gates cannot be silently skipped."""
    manifest = project / "slide-manifest.json"
    if not manifest.is_file():
        return False
    try:
        raw = manifest.read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return any(token in raw for token in (
        "extracted_icon", "decorative_art", "decorative_word_art",
        "icon-asset-manifest", "imagegen-assets-manifest",
        "source_element_id", "source-icons",
    ))


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
    parser.add_argument("--require-text-style-map", action="store_true", help="validate rich text/style records when present")
    parser.add_argument("--dpi", type=int, default=96, help="render DPI; 96 matches common 1536x864 reference images")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    deck = Path(args.deck).resolve()
    if not project.is_dir() or not deck.is_file():
        print(json.dumps({"valid": False, "code": "project_or_deck_missing"}, ensure_ascii=False))
        return 3
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
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    run_dir = Path(args.output_dir).resolve() if args.output_dir else project / "pipeline-runs" / run_id
    if run_dir.exists():
        print(json.dumps({"valid": False, "code": "run_dir_exists", "path": str(run_dir)}, ensure_ascii=False))
        return 2
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir()
    render_dir = run_dir / "rendered"
    steps = []
    icon_required = args.require_icon_assets or project_mentions_icons(project) or (project / "icon-asset-manifest.json").is_file()
    imagegen_required = args.require_imagegen_assets or icon_required or (project / "imagegen-assets-manifest.json").is_file()
    if args.route_decision:
        route_args = [str(SCRIPT_DIR / "validate_route.py"), str(Path(args.route_decision).resolve()), "--require-files", "--report", str(run_dir / "route-validation.json")]
        steps.append(run_step(run_dir, "route", route_args))
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
    layout_path = project / "layout.json"
    object_manifest = Path(args.object_manifest).resolve() if args.object_manifest else project / "slide-object-manifest.json"
    if args.require_object_manifest or object_manifest.is_file():
        object_args = [str(SCRIPT_DIR / "validate_object_manifest.py"), str(object_manifest), "--report", str(run_dir / "object-manifest-validation.json")]
        if args.require_independent_panels:
            object_args.append("--require-panels")
        steps.append(run_step(run_dir, "object-manifest", object_args))
    if args.reference:
        if layout_path.is_file():
            layout_step = run_step(run_dir, "layout-guard", [str(SCRIPT_DIR / "layout_guard.py"), str(Path(args.reference).resolve()), str(layout_path), "--strict"])
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
    if panel_manifest.is_file() or args.require_independent_panels:
        panel_args = [str(SCRIPT_DIR / "validate_panel_assets.py"), str(panel_manifest), "--assets-dir", str(project), "--report", str(run_dir / "panel-assets-validation.json"), "--strict"]
        if args.require_independent_panels:
            panel_args.append("--require-independent")
        if args.expected_panel_count is not None:
            panel_args.extend(["--expected-count", str(args.expected_panel_count)])
        steps.append(run_step(run_dir, "panel-assets", panel_args))
    if args.require_text_style_map and layout_path.is_file():
        steps.append(run_step(run_dir, "text-style-map", [str(SCRIPT_DIR / "validate_text_style_map.py"), str(layout_path), "--report", str(run_dir / "text-style-map-validation.json")]))
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
    if args.require_object_manifest or object_manifest.is_file():
        report_entries.extend([
            {"report_type": "object-manifest-validation", "path": "object-manifest-validation.json", "required": True, "stage": "validated"},
            {"report_type": "editable-object-audit", "path": "editable-object-audit.json", "required": True, "stage": "validated"},
        ])
    if panel_manifest.is_file() or args.require_independent_panels:
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
    if args.route_decision:
        report_entries.append({"report_type": "route-validation", "path": "route-validation.json", "required": args.require_route, "stage": "design-system-ready"})
    if args.reference or args.reference_dir:
        report_entries.append({"report_type": "visual-comparison", "path": "visual-comparison.json", "required": True, "stage": "validated"})
    if args.ocr_lang or args.require_ocr:
        report_entries.append({"report_type": "ocr-text-check", "path": "ocr-text-check.json", "required": args.require_ocr, "stage": "validated"})
    step_status = {step["name"]: step["ok"] for step in steps}
    for entry in report_entries:
        step_name = {"render-visual-gate": "render-visual-gate", "manifest-validation": "manifest", "project-validation": "project", "project-report-aggregate": "project-report-aggregate", "visual-comparison": "visual-comparison", "visual-compare-qa": "visual-compare-qa", "layout-guard": "layout-guard", "imagegen-assets-validation": "imagegen-assets", "icon-assets-validation": "icon-assets", "icon-layer-audit": "icon-layers", "ocr-text-check": "ocr-text-check", "route-validation": "route", "font": "fonts", "environment": "environment", "inspection": "inspection", "render": "render", "object-manifest-validation": "object-manifest", "editable-object-audit": "editable-object-audit", "panel-assets-validation": "panel-assets", "text-style-map-validation": "text-style-map"}.get(entry["report_type"])
        if step_name in step_status:
            entry["step_ok"] = step_status[step_name]
    report_index = {"schema": "ai-ppt-plus/report-index/v1", "project_id": project.name, "revision": args.revision_label or "working", "stage": "validated", "deck_path": str(deck), "deck_sha256": sha256(deck), "reports": report_entries}
    (run_dir / "report-index.json").write_text(json.dumps(report_index, ensure_ascii=False, indent=2), encoding="utf-8")
    steps.append(run_step(run_dir, "project-report-aggregate", [str(SCRIPT_DIR / "aggregate_project_reports.py"), str(run_dir / "report-index.json"), "--report", str(run_dir / "project-report.json")]))
    failed = [step["name"] for step in steps if not step["ok"]]
    quality_evidence = {}
    for name, path in (
        ("render_visual_gate", run_dir / "render-visual-gate.json"),
        ("visual_comparison", run_dir / "visual-comparison.json"),
        ("ocr_text_check", run_dir / "ocr-text-check.json"),
        ("route_validation", run_dir / "route-validation.json"),
        ("manifest_validation", run_dir / "manifest-validation.json"),
        ("imagegen_assets_validation", run_dir / "imagegen-assets-validation.json"),
        ("icon_assets_validation", run_dir / "icon-assets-validation.json"),
        ("icon_layer_audit", run_dir / "icon-layer-audit.json"),
        ("object_manifest_validation", run_dir / "object-manifest-validation.json"),
        ("editable_object_audit", run_dir / "editable-object-audit.json"),
        ("panel_assets_validation", run_dir / "panel-assets-validation.json"),
        ("text_style_map_validation", run_dir / "text-style-map-validation.json"),
        ("visual_compare_qa", run_dir / "visual-qa/report.json"),
        ("project_report_aggregate", run_dir / "project-report.json"),
    ):
        report = load_report(path)
        if report is not None:
            quality_evidence[name] = summarize_report(name, path, report)
    quality_degradations = []
    ocr_report = quality_evidence.get("ocr_text_check")
    if ocr_report and ocr_report.get("status") == "unavailable":
        quality_degradations.append({"code": "ocr_unavailable", "language": ocr_report.get("language"), "requires_human_review": True})
    result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": not failed, "run_id": run_id, "project": str(project), "deck": str(deck), "deck_sha256": sha256(deck), "run_dir": str(run_dir), "steps": steps, "failed_steps": failed, "next_state": "validated" if not failed else "revision-required", "human_visual_review_required": True, "human_signoff_required": True, "quality_evidence": quality_evidence, "quality_degradations": quality_degradations}
    (run_dir / "pipeline-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
