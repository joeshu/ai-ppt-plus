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
       [--visual-generation-plan PLAN.json] [--visual-generation-manifest MANIFEST.json]
       [--require-visual-generation]
       [--dpi N] [--strict-layout]
       [--execution-mode dag|linear] [--cache-dir DIR] [--no-cache]
       [--parallel-workers N] [--affected-pages 1,3-4]
       [--page-cache-dir DIR] [--preview-dir DIR]
       [--affected-region name=x,y,w,h]
       [--chart-manifest CHARTS.json] [--require-chart-manifest]
       [--output-dir RUN_DIR]
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from atomic_output import atomic_write_json, atomic_write_text
from pipeline_engine import PipelineExecutor, PipelineTask
from report_envelope import normalize_child
from render_review_html import write_review


SCRIPT_DIR = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


STEP_TIMEOUT_SECONDS = 600


def parse_page_selection(expression: str | None, expected_pages: int) -> list[int] | None:
    """Parse and bounds-check a comma/range page selection."""
    if not expression:
        return None
    selected: set[int] = set()
    try:
        for part in expression.split(","):
            token = part.strip()
            if not token:
                raise ValueError
            if "-" in token:
                lo, hi = (int(value.strip()) for value in token.split("-", 1))
                if lo > hi:
                    raise ValueError
                selected.update(range(lo, hi + 1))
            else:
                selected.add(int(token))
    except (TypeError, ValueError):
        raise ValueError("pages must be a comma-separated list of positive integers/ranges")
    if not selected or min(selected) < 1 or max(selected) > expected_pages:
        raise ValueError(f"pages must be between 1 and {expected_pages}")
    return sorted(selected)


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
    atomic_write_text(stdout_path, stdout)
    atomic_write_text(stderr_path, stderr)
    result = {"name": name, "command": command, "exit_code": exit_code, "ok": exit_code == 0, "stdout": str(stdout_path.resolve()), "stderr": str(stderr_path.resolve()), "timeout_seconds": timeout, "cache_key": None, "cache_hit": False, "deps": [], "duration_ms": None}
    if failure:
        result["failure"] = failure
    return result


def load_report(path: Path):
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return {"valid": False, "status": "invalid", "issues": [{"code": "report_not_object"}]}
        return value
    except Exception as exc:
        return {"valid": False, "status": "invalid", "issues": [{"code": "invalid_json", "message": f"{type(exc).__name__}: {exc}"}]}


def project_gate_requirements(project: Path) -> dict:
    """Read explicit per-project gate requirements and report their origin."""
    manifest = project / "slide-manifest.json"
    if not manifest.is_file():
        return {"declared": False, "issues": ["slide_manifest_missing"]}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"declared": False, "issues": ["slide_manifest_unreadable"]}
    if not isinstance(data, dict):
        return {"declared": False, "issues": ["slide_manifest_not_object"]}
    slides = [slide for slide in (data.get("slides") or []) if isinstance(slide, dict)]
    raw = data.get("gate_requirements")
    if not isinstance(raw, dict):
        legacy_icon = data.get("requires_icon_assets") is True or any(slide.get("requires_icon_assets") is True for slide in slides)
        legacy_imagegen = data.get("requires_imagegen_assets") is True or any(slide.get("requires_imagegen_assets") is True for slide in slides)
        return {
            "declared": False,
            "issues": ["gate_requirements_missing"],
            "requirements": {"icon_assets": legacy_icon, "imagegen_assets": legacy_imagegen},
            "manifest": data,
        }
    names = (
        "object_manifest", "semantic_object_audit", "manifest_registry", "text_model",
        "text_style_map", "icon_assets", "imagegen_assets", "panel_assets",
        "panel_approval", "gradient_visual", "source_image_validation", "reference_audit",
        "content_inventory",
    )
    optional_names = ("asset_hashes",)
    requirements = {}
    issues = []
    for name in names:
        value = raw.get(name)
        if not isinstance(value, bool):
            issues.append(f"gate_requirements.{name}_must_be_boolean")
        else:
            requirements[name] = value
    for name in optional_names:
        value = raw.get(name, False)
        if not isinstance(value, bool):
            issues.append(f"gate_requirements.{name}_must_be_boolean")
        else:
            requirements[name] = value
    return {"declared": not issues, "issues": issues, "requirements": requirements, "manifest": data}


def project_asset_requirements(project: Path) -> tuple[bool, bool]:
    """Compatibility helper for callers that only need icon/imagegen flags."""
    gates = project_gate_requirements(project)
    requirements = gates.get("requirements", {})
    return bool(requirements.get("icon_assets")), bool(requirements.get("imagegen_assets"))


def inferred_gate_requirements(project: Path, object_manifest: Path, route_data: dict | None) -> dict[str, bool]:
    """Infer gates from declared content so a manifest cannot under-declare QA.

    These values are policy checks, not a replacement for the explicit
    ``slide-manifest.json`` declaration.  Release mode requires the explicit
    declaration to cover every inferred requirement; this closes the old gap
    where a project could contain icons, panels or gradients while advertising
    only the core object-count checks.
    """
    objects: list[dict] = []
    if object_manifest.is_file():
        try:
            data = json.loads(object_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        for slide in (data.get("slides") or []) if isinstance(data, dict) else []:
            if isinstance(slide, dict) and isinstance(slide.get("objects"), list):
                objects.extend(item for item in slide["objects"] if isinstance(item, dict))

    icon_types = {"extracted_icon", "editable_vector"}
    visual_asset_types = {"extracted_icon", "editable_vector", "independent_image", "decorative_art", "traceable_static_graphic"}
    icon_roles = {"icon", "logo", "brand_lockup", "brand-logo", "decorative-art", "illustration", "product-visual", "decoration"}
    icon_objects = [item for item in objects if item.get("object_type") in icon_types or item.get("role") in icon_roles]
    visual_objects = [item for item in objects if item.get("object_type") in visual_asset_types or item.get("role") in icon_roles]
    panel_objects = [item for item in objects if item.get("role") in {"semantic-panel", "panel", "frame-panel"} or item.get("independent") is True]
    has_text = any(item.get("object_type") == "editable_text" for item in objects)
    reference_route = isinstance(route_data, dict) and route_data.get("route") == "reference-reconstruction"

    has_gradient = False
    layout_path = project / "layout.json"
    if layout_path.is_file():
        try:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            layout = {}

        def contains_gradient(value) -> bool:
            if isinstance(value, dict):
                if isinstance(value.get("gradient"), dict):
                    return True
                return any(contains_gradient(child) for child in value.values())
            if isinstance(value, list):
                return any(contains_gradient(child) for child in value)
            return False

        has_gradient = contains_gradient(layout)

    return {
        "object_manifest": True,
        "semantic_object_audit": True,
        "manifest_registry": True,
        "text_model": has_text,
        "text_style_map": reference_route and has_text,
        "icon_assets": bool(icon_objects),
        "imagegen_assets": reference_route and bool(visual_objects),
        "panel_assets": bool(panel_objects),
        "panel_approval": bool(panel_objects),
        "gradient_visual": has_gradient,
        "source_image_validation": reference_route,
        "reference_audit": reference_route,
        "content_inventory": reference_route and has_text,
        "asset_hashes": bool(visual_objects) or any(
            (project / name).is_file()
            for name in ("asset-manifest.json", "panel-asset-manifest.json", "icon-asset-manifest.json", "imagegen-assets-manifest.json")
        ),
    }


def project_has_charts(project: Path) -> bool:
    """Detect declared chart content without requiring a particular layout."""
    def contains_charts(value: object) -> bool:
        if isinstance(value, dict):
            charts = value.get("charts")
            if isinstance(charts, list) and charts:
                return True
            return any(contains_charts(child) for child in value.values())
        if isinstance(value, list):
            return any(contains_charts(child) for child in value)
        return False

    for name in ("content-inventory.json", "layout.json", "slide-manifest.json"):
        path = project / name
        if not path.is_file():
            continue
        try:
            if contains_charts(json.loads(path.read_text(encoding="utf-8"))):
                return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


def summarize_report(name: str, path: Path, report: dict):
    summary = normalize_child(name, path, report, required=True, stage=None, deck_sha256=report.get("deck_sha256"))
    summary["report"] = str(path.resolve())
    if name == "render_visual_gate":
        summary.update({"expected_pages": report.get("expected_pages"), "observed_pages": len(report.get("pages", []))})
    elif name == "visual_comparison":
        summary.update({"reference": report.get("reference"), "reference_dir": report.get("reference_dir"), "metrics": report.get("metrics", {}), "aggregate": report.get("aggregate", {}), "compared_pages": len(report.get("pages", [])), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "ocr_text_check":
        summary.update({"language": report.get("language"), "slide_count": len(report.get("slides", [])), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "route_validation":
        summary.update({"route": report.get("route"), "visual_authority": report.get("visual_authority"), "formal_content_authority": report.get("formal_content_authority"), "visual_generation_mode": report.get("visual_generation_mode")})
    elif name == "visual_generation_validation":
        summary.update({"mode": report.get("mode"), "page_count": report.get("page_count"), "framework_count": report.get("framework_count"), "density_profile": report.get("density_profile"), "evidence": report.get("evidence"), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "manifest_validation":
        summary.update({"warnings": report.get("warnings", []), "editability_protocol": report.get("editability_protocol"), "editability": report.get("editability", [])})
    elif name == "visual_compare_qa":
        summary.update({"native_status": report.get("status", "diagnostic"), "ok": report.get("ok"), "resized_for_comparison": report.get("resized_for_comparison"), "preview_size": report.get("preview_size")})
    elif name == "render":
        summary.update({"renderer": report.get("renderer"), "dpi": report.get("dpi"), "conversion": report.get("conversion", {}), "page_cache": report.get("page_cache", {}), "page_fingerprints": report.get("page_fingerprints", [])})
    elif name == "multipage_layout_guard":
        summary.update({"expected_pages": report.get("expected_pages"), "selected_pages": report.get("selected_pages"), "pages": len(report.get("pages", [])), "strict": report.get("strict"), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "preview_consistency":
        summary.update({"expected_pages": report.get("expected_pages"), "aggregate": report.get("aggregate", {}), "threshold": report.get("threshold"), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "typography_calibration":
        summary.update({"sample_count": report.get("sample_count"), "max_drift": report.get("max_drift"), "samples": report.get("samples", []), "warnings": report.get("warnings", []), "human_visual_review_required": report.get("human_visual_review_required", True)})
    elif name == "chart_manifest_validation":
        summary.update({"chart_count": report.get("chart_count"), "charts": report.get("charts", []), "warnings": report.get("warnings", []), "human_visual_review_required": report.get("human_visual_review_required", True)})
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
    parser.add_argument("--visual-generation-plan", help="ai-ppt-visual-gen A1-A5 visual-generation-plan.json")
    parser.add_argument("--visual-generation-manifest", help="per-page raster generation evidence manifest")
    parser.add_argument("--require-visual-generation", action="store_true", help="require the visual-generation plan, self-contained prompts and retained image evidence")
    parser.add_argument("--routing-contract", help="skill-routing contract; defaults to the checked-in contract")
    parser.add_argument("--require-formal-content", action="store_true", help="require approved formal text authority in the route decision")
    parser.add_argument("--content-inventory", help="independent visible-content inventory for text and chart annotations")
    parser.add_argument("--require-content-inventory", action="store_true", help="require and validate the independent visible-content inventory")
    parser.add_argument("--chart-manifest", help="traceable chart data and representation manifest; defaults to project/chart-reconstruction.json")
    parser.add_argument("--require-chart-manifest", action="store_true", help="require and validate the chart data/representation manifest")
    parser.add_argument("--require-editability", action="store_true", help="require typed L0-L5 object records in the slide manifest")
    parser.add_argument("--require-icon-assets", action="store_true", help="require B4/B5 icon asset and layer audits")
    parser.add_argument("--require-imagegen-assets", action="store_true", help="require per-page imagegen asset provenance")
    parser.add_argument("--object-manifest", help="canonical slide-object-manifest.json")
    parser.add_argument("--require-object-manifest", action="store_true", help="require and validate the canonical object inventory")
    parser.add_argument("--require-independent-panels", action="store_true", help="reverse-audit independently movable semantic panels")
    parser.add_argument("--expected-panel-count", type=int, help="expected semantic panel count")
    parser.add_argument("--require-panel-approval", action="store_true", help="require explicit human approval metadata for panel assets")
    parser.add_argument("--require-text-style-map", action="store_true", help="validate rich text/style records when present")
    parser.add_argument("--text-manifest", help="canonical text-layout-manifest.json")
    parser.add_argument("--require-text-model", action="store_true", help="require and validate the canonical text layout manifest")
    parser.add_argument("--asset-manifest", action="append", default=[], help="asset manifest used for semantic object provenance checks")
    parser.add_argument("--manifest-registry", help="canonical cross-manifest registry.json")
    parser.add_argument("--require-manifest-registry", action="store_true", help="require and validate the cross-manifest registry")
    parser.add_argument("--require-source-hashes", action="store_true", help="require declared source hashes for raster/data assets")
    parser.add_argument("--require-asset-hashes", action="store_true", help="require current SHA-256 declarations for all file-backed asset manifests")
    parser.add_argument("--require-gradient-visual", action="store_true", help="require and validate the gradient visual manifest")
    parser.add_argument("--release", action="store_true", help="run the strict release gate after technical validation")
    parser.add_argument("--handoff", help="handoff.json; required by --release")
    parser.add_argument("--human-signoff", help="human-closeout.json; required by --release")
    parser.add_argument("--issue-log", help="issue-log.json passed to the release gate")
    parser.add_argument("--quality-score", type=float, help="human/automated quality score for --release")
    parser.add_argument("--quality-threshold", type=float, default=80, help="minimum quality score for --release")
    parser.add_argument("--require-embedded-fonts", action="store_true", help="require verified OOXML embedded fonts in strict release delivery")
    parser.add_argument("--dpi", type=int, default=96, help="render DPI; same-ratio reference comparisons are normalized when pixel sizes differ")
    parser.add_argument("--strict-layout", action="store_true", help="treat layout-audit warnings (such as missing source_bbox) as blockers")
    parser.add_argument("--require-multipage-layout", action="store_true", help="require per-page layout/bbox validation when --reference-dir is used")
    parser.add_argument("--preview-dir", help="Pillow authoring previews to compare with final rendered PNGs")
    parser.add_argument("--preview-threshold", type=float, help="minimum blurred SSIM for preview/final-render consistency")
    parser.add_argument("--require-preview-consistency", action="store_true", help="require an exact preview page set and valid preview/final-render comparison")
    parser.add_argument("--typography-calibration", help="prominent-text calibration manifest; defaults to project/typography-calibration.json")
    parser.add_argument("--require-typography-calibration", action="store_true", help="require a valid prominent-text calibration manifest")
    parser.add_argument("--execution-mode", choices=["dag", "linear"], default="dag", help="DAG execution with caching, or the compatibility linear runner")
    parser.add_argument("--cache-dir", help="content-addressed pipeline cache directory; defaults to PROJECT_DIR/.pipeline-cache in DAG mode")
    parser.add_argument("--no-cache", action="store_true", help="disable successful-task cache restores/writes")
    parser.add_argument("--parallel-workers", type=int, default=4, help="maximum independent DAG checks to run concurrently")
    parser.add_argument("--affected-pages", help="only render and compare selected pages, e.g. 1,3-4")
    parser.add_argument("--page-cache-dir", help="content-addressed validated page PNG cache; defaults to .pipeline-cache/render-pages in DAG mode")
    parser.add_argument("--affected-region", action="append", default=[], help="critical region affected by the change: name=x,y,w,h; checked by the render QA gate")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    deck = Path(args.deck).resolve()
    if args.expected_pages < 1:
        print(json.dumps({"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "code": "expected_pages_invalid", "message": "--expected-pages must be positive"}, ensure_ascii=False))
        return 2
    if args.release:
        # A release is a stronger profile than technical validation.  Make
        # the required evidence explicit instead of allowing a green run to
        # be mistaken for a delivered deck.
        args.require_route = True
        args.require_editability = True
        args.require_embedded_fonts = True
        args.require_cjk = True
        args.require_object_manifest = True
        args.require_manifest_registry = True
        args.require_text_model = True
        args.require_source_hashes = True
        args.require_asset_hashes = True
        args.require_formal_content = True
        if args.reference_dir:
            args.require_multipage_layout = True
        missing = []
        if not args.font_dir:
            missing.append("--font-dir")
        if not args.route_decision:
            missing.append("--route-decision")
        if not args.handoff:
            missing.append("--handoff")
        if not args.human_signoff:
            missing.append("--human-signoff")
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
    try:
        affected_pages = parse_page_selection(args.affected_pages, args.expected_pages)
    except ValueError as exc:
        print(json.dumps({"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "code": "affected_pages_invalid", "message": str(exc)}, ensure_ascii=False))
        return 2
    if args.parallel_workers < 1:
        print(json.dumps({"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "code": "parallel_workers_invalid"}, ensure_ascii=False))
        return 2
    if args.release and affected_pages:
        print(json.dumps({"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "technical_valid": False, "release_eligible": False, "code": "release_requires_full_deck", "message": "--release requires a full-deck render; omit --affected-pages"}, ensure_ascii=False))
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
    if args.require_route and (not isinstance(route_data, dict) or route_data.get("status") != "decided"):
        result = {
            "schema": "ai-ppt-plus/pipeline-run/v2",
            "valid": False,
            "technical_valid": False,
            "release_eligible": False,
            "code": "route_not_ready",
            "message": "route status must be decided before downstream pipeline execution",
            "observed_status": route_data.get("status") if isinstance(route_data, dict) else None,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 2
    reference_route = isinstance(route_data, dict) and route_data.get("route") == "reference-reconstruction"
    visual_creation_route = isinstance(route_data, dict) and route_data.get("route") == "visual-creation"
    visual_generation_mode = route_data.get("visual_generation_mode", "layout-reference") if visual_creation_route else None
    if visual_creation_route and visual_generation_mode == "image-slide":
        args.require_visual_generation = True
    # Reference reconstruction is the route where a technically valid deck
    # can still fail visibly because the chosen font has different metrics.
    # Make the lightweight calibration evidence non-optional here, and also
    # for strict releases that compare against an approved reference. This
    # prevents a green pixel score from silently accepting a shrunk title.
    if reference_route or (args.release and (args.reference or args.reference_dir)):
        args.require_typography_calibration = True
    typography_calibration = Path(args.typography_calibration).resolve() if args.typography_calibration else project / "typography-calibration.json"
    if args.require_typography_calibration and not typography_calibration.is_file():
        result = {
            "schema": "ai-ppt-plus/pipeline-run/v2",
            "valid": False,
            "technical_valid": False,
            "release_eligible": False,
            "code": "typography_calibration_missing",
            "path": str(typography_calibration),
            "message": "reference reconstruction/release requires measured typography-calibration.json before render",
        }
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if args.release and reference_route:
        # A fixed reference contains visible information that cannot be
        # inferred from object counts alone.  Release therefore requires an
        # independent inventory of all visible text and chart annotations.
        args.require_content_inventory = True
    # A release containing declared charts must carry independent chart
    # data/representation evidence. Infer this from project content so an
    # omitted CLI flag cannot bypass the data-authority gate.
    if args.release and project_has_charts(project):
        args.require_chart_manifest = True
    gate_info = project_gate_requirements(project)
    gate_requirements = gate_info.get("requirements", {})
    if args.release:
        core_required = ("object_manifest", "semantic_object_audit", "manifest_registry", "text_model")
        missing_gate_declarations = [name for name in core_required if gate_info.get("requirements", {}).get(name) is not True]
        policy_object_manifest = Path(args.object_manifest).resolve() if args.object_manifest else project / "slide-object-manifest.json"
        inferred_requirements = inferred_gate_requirements(project, policy_object_manifest, route_data)
        underdeclared_gates = [name for name, required in inferred_requirements.items() if required and gate_requirements.get(name) is not True]
        if gate_info.get("issues") or missing_gate_declarations or underdeclared_gates:
            result = {
                "schema": "ai-ppt-plus/pipeline-run/v2",
                "valid": False,
                "technical_valid": False,
                "release_eligible": False,
                "code": "release_gate_requirements_missing",
                "issues": gate_info.get("issues", []),
                "missing_required_gates": missing_gate_declarations,
                "underdeclared_gates": underdeclared_gates,
            }
            print(json.dumps(result, ensure_ascii=False))
            return 2
        args.require_panel_approval = args.require_panel_approval or gate_requirements.get("panel_approval", False)
        args.require_independent_panels = args.require_independent_panels or gate_requirements.get("panel_assets", False)
        args.require_icon_assets = args.require_icon_assets or gate_requirements.get("icon_assets", False)
        args.require_imagegen_assets = args.require_imagegen_assets or gate_requirements.get("imagegen_assets", False)
        args.require_text_style_map = args.require_text_style_map or gate_requirements.get("text_style_map", False)
        args.require_gradient_visual = args.require_gradient_visual or gate_requirements.get("gradient_visual", False)
        args.require_asset_hashes = args.require_asset_hashes or gate_requirements.get("asset_hashes", False)
    if args.require_route and reference_route:
        if not (args.reference or args.reference_dir):
            result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": False, "code": "reference_route_without_reference", "message": "reference-reconstruction requires --reference or --reference-dir for visual comparison"}
            print(json.dumps(result, ensure_ascii=False))
            return 2
        roster = route_data.get("reference_roster") or []
        if roster and len(roster) != args.expected_pages:
            result = {"schema": "ai-ppt-plus/pipeline-run/v1", "valid": False, "code": "route_reference_page_count_mismatch", "expected_pages": args.expected_pages, "route_reference_pages": len(roster)}
            print(json.dumps(result, ensure_ascii=False))
            return 2
        if args.release and not gate_requirements.get("source_image_validation"):
            print(json.dumps({"schema": "ai-ppt-plus/pipeline-run/v2", "valid": False, "technical_valid": False, "release_eligible": False, "code": "reference_source_gate_not_declared"}, ensure_ascii=False))
            return 2
        if args.release:
            args.require_text_style_map = True
            args.require_gradient_visual = args.require_gradient_visual or gate_requirements.get("gradient_visual", False)
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = Path(args.output_dir).resolve() if args.output_dir else project / "pipeline-runs" / run_id
    if run_dir.exists():
        print(json.dumps({"valid": False, "code": "run_dir_exists", "path": str(run_dir)}, ensure_ascii=False))
        return 2
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir()
    render_dir = run_dir / "rendered"
    cache_dir = None
    if args.execution_mode == "dag" and not args.no_cache:
        cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else project / ".pipeline-cache"
    page_cache_dir = None
    if not args.no_cache and (args.execution_mode == "dag" or args.page_cache_dir):
        page_cache_dir = Path(args.page_cache_dir).resolve() if args.page_cache_dir else (cache_dir / "render-pages" if cache_dir else project / ".pipeline-cache" / "render-pages")
    executor = PipelineExecutor(run_dir, mode=args.execution_mode, cache_dir=cache_dir, max_workers=args.parallel_workers)

    def add_step(name, command=None, *, deps=(), outputs=(), inputs=(), metadata=None, cacheable=True, static_result=None):
        return executor.add(PipelineTask(
            name=name,
            args=list(command or []),
            deps=tuple(deps),
            outputs=tuple(Path(path).resolve() for path in outputs),
            inputs=tuple(Path(path).resolve() for path in inputs),
            metadata=dict(metadata or {}),
            timeout=STEP_TIMEOUT_SECONDS,
            cacheable=cacheable,
            static_result=static_result,
        ))

    routing_contract = Path(args.routing_contract).resolve() if args.routing_contract else SCRIPT_DIR.parent / "assets" / "skill-routing.template.json"
    package_args = [str(SCRIPT_DIR / "validate_skill_package.py"), "--skill-dir", str(SCRIPT_DIR.parent), "--report", str(run_dir / "skill-package-validation.json")]
    runtime_skill_dir = os.environ.get("AI_PPT_PLUS_RUNTIME_SKILL_DIR")
    if runtime_skill_dir:
        package_args.extend(["--runtime-skill-dir", str(Path(runtime_skill_dir).resolve())])
    package_inputs = [SCRIPT_DIR.parent / "assets" / "skill-package.json"]
    try:
        package_data = json.loads((SCRIPT_DIR.parent / "assets" / "skill-package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        package_data = {}
    for relative in package_data.get("required_files", []) if isinstance(package_data, dict) else []:
        if isinstance(relative, str):
            package_inputs.append(SCRIPT_DIR.parent / relative)
    for pattern in package_data.get("managed_globs", []) if isinstance(package_data, dict) else []:
        if isinstance(pattern, str):
            package_inputs.extend(path for path in SCRIPT_DIR.parent.glob(pattern) if path.is_file())
    if runtime_skill_dir:
        package_inputs.append(Path(runtime_skill_dir).resolve())
    add_step("skill-package", package_args, outputs=[run_dir / "skill-package-validation.json"], inputs=list(dict.fromkeys(package_inputs)))
    add_step("routing-contract", [str(SCRIPT_DIR / "validate_routing_contract.py"), str(routing_contract), "--report", str(run_dir / "routing-contract-validation.json")], outputs=[run_dir / "routing-contract-validation.json"], inputs=[routing_contract], deps=["skill-package"])
    if args.route_decision:
        route_args = [str(SCRIPT_DIR / "validate_route.py"), str(Path(args.route_decision).resolve()), "--require-files", "--expected-pages", str(args.expected_pages), "--require-confirmation", "--report", str(run_dir / "route-validation.json")]
        if args.require_formal_content:
            route_args.append("--require-formal-content")
        if args.reference:
            route_args.extend(["--reference", str(Path(args.reference).resolve())])
        elif args.reference_dir:
            route_args.extend(["--reference-dir", str(Path(args.reference_dir).resolve())])
        route_inputs = [Path(args.route_decision).resolve()]
        if isinstance(route_data, dict) and route_data.get("route") == "reference-reconstruction":
            route_base = Path(args.route_decision).resolve().parent
            route_inputs.extend(
                (route_base / item["path"]).resolve()
                for item in (route_data.get("reference_roster") or [])
                if isinstance(item, dict) and isinstance(item.get("path"), str) and item.get("path")
            )
        if isinstance(route_data, dict) and route_data.get("route") == "visual-creation" and route_data.get("visual_generation_mode", "layout-reference") == "image-slide":
            route_base = Path(args.route_decision).resolve().parent
            for field in ("visual_generation_plan", "visual_generation_manifest"):
                value = route_data.get(field)
                if isinstance(value, str) and value.strip():
                    candidate = Path(value)
                    route_inputs.append((candidate if candidate.is_absolute() else route_base / candidate).resolve())
        if args.reference:
            route_inputs.append(Path(args.reference).resolve())
        elif args.reference_dir:
            route_inputs.extend(Path(args.reference_dir).resolve() / f"slide-{index}.png" for index in range(1, args.expected_pages + 1))
        add_step("route", route_args, deps=["routing-contract"], outputs=[run_dir / "route-validation.json"], inputs=list(dict.fromkeys(route_inputs)))

    manifest_icon_required, manifest_imagegen_required = project_asset_requirements(project)
    icon_required = args.require_icon_assets or manifest_icon_required or (project / "icon-asset-manifest.json").is_file()
    imagegen_required = args.require_imagegen_assets or manifest_imagegen_required or (project / "imagegen-assets-manifest.json").is_file()
    route_deps = ["route"] if args.route_decision else []
    visual_generation_plan = None
    visual_generation_manifest = None
    visual_generation_enabled = False
    if visual_creation_route:
        visual_generation_base = Path(args.route_decision).resolve().parent if args.route_decision else project

        def declared_visual_path(cli_value, route_key, default_name):
            if cli_value:
                return Path(cli_value).resolve()
            value = None
            if not value and isinstance(route_data, dict):
                value = route_data.get(route_key)
            if not value:
                value = default_name
            path = Path(value)
            return path.resolve() if path.is_absolute() else (visual_generation_base / path).resolve()

        visual_generation_plan = declared_visual_path(
            args.visual_generation_plan,
            "visual_generation_plan",
            "visual-generation-plan.json",
        )
        visual_generation_manifest = declared_visual_path(
            args.visual_generation_manifest,
            "visual_generation_manifest",
            "visual-generation-manifest.json",
        )
        visual_generation_enabled = bool(
            args.require_visual_generation
            or args.visual_generation_plan
            or args.visual_generation_manifest
            or visual_generation_mode == "image-slide"
            or visual_generation_plan.is_file()
            or visual_generation_manifest.is_file()
        )
        if visual_generation_enabled:
            visual_generation_inputs = []
            visual_generation_args = [
                str(SCRIPT_DIR / "validate_visual_generation_plan.py"),
                str(visual_generation_plan),
                "--expected-pages", str(args.expected_pages),
                "--report", str(run_dir / "visual-generation-validation.json"),
            ]
            manifest_declared = bool(
                args.visual_generation_manifest
                or (isinstance(route_data, dict) and route_data.get("visual_generation_manifest"))
                or visual_generation_manifest.is_file()
                or visual_generation_mode == "image-slide"
            )
            if manifest_declared:
                visual_generation_args.extend(["--manifest", str(visual_generation_manifest)])
            if args.require_visual_generation:
                visual_generation_args.append("--require-evidence")

            if not visual_generation_plan.is_file():
                add_step(
                    "visual-generation",
                    static_result={
                        "name": "visual-generation",
                        "command": [],
                        "exit_code": 2,
                        "ok": False,
                        "failure": "visual_generation_plan_missing",
                        "stdout": "",
                        "stderr": "",
                    },
                    cacheable=False,
                    deps=route_deps,
                    outputs=[run_dir / "visual-generation-validation.json"],
                )
            elif args.require_visual_generation and not visual_generation_manifest.is_file():
                add_step(
                    "visual-generation",
                    static_result={
                        "name": "visual-generation",
                        "command": [],
                        "exit_code": 2,
                        "ok": False,
                        "failure": "visual_generation_manifest_missing",
                        "stdout": "",
                        "stderr": "",
                    },
                    cacheable=False,
                    deps=route_deps,
                    outputs=[run_dir / "visual-generation-validation.json"],
                )
            else:
                visual_generation_inputs.append(visual_generation_plan)
                if visual_generation_manifest.is_file():
                    visual_generation_inputs.append(visual_generation_manifest)
                # Include referenced prompt/source/copy files in the task
                # fingerprint so changing a prompt or selected raster cannot
                # silently reuse a stale validation result.
                for manifest_path in (visual_generation_plan, visual_generation_manifest):
                    if not manifest_path.is_file():
                        continue
                    try:
                        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        manifest_data = {}
                    records = manifest_data.get("slides", []) if isinstance(manifest_data, dict) else []
                    if isinstance(records, list):
                        for record in records:
                            if not isinstance(record, dict):
                                continue
                            for field in ("prompt_file", "generated_source", "copied_to"):
                                value = record.get(field)
                                if not isinstance(value, str) or not value.strip():
                                    continue
                                candidate = Path(value)
                                candidate = candidate.resolve() if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()
                                if candidate.is_file():
                                    visual_generation_inputs.append(candidate)
                add_step(
                    "visual-generation",
                    visual_generation_args,
                    deps=route_deps,
                    outputs=[run_dir / "visual-generation-validation.json"],
                    inputs=list(dict.fromkeys(visual_generation_inputs)),
                    metadata={
                        "mode": visual_generation_mode,
                        "required": args.require_visual_generation,
                        "plan": str(visual_generation_plan),
                        "manifest": str(visual_generation_manifest) if manifest_declared else None,
                    },
                )
    reference_sources: list[Path] = []
    if isinstance(route_data, dict) and route_data.get("route") == "reference-reconstruction":
        route_base = Path(args.route_decision).resolve().parent if args.route_decision else project
        for item in (route_data.get("reference_roster") or []):
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item.get("path"):
                reference_sources.append((route_base / item["path"]).resolve())
    if args.reference:
        reference_sources.append(Path(args.reference).resolve())
    elif args.reference_dir:
        reference_sources.extend((Path(args.reference_dir).resolve() / f"slide-{index}.png") for index in range(1, args.expected_pages + 1))
    unique_reference_sources = list(dict.fromkeys(reference_sources))
    if unique_reference_sources:
        source_args = [str(SCRIPT_DIR / "validate_source_images.py"), *[str(path) for path in unique_reference_sources], "--report", str(run_dir / "source-image-validation.json")]
        add_step("source-images", source_args, deps=route_deps, outputs=[run_dir / "source-image-validation.json"], inputs=unique_reference_sources)
    gradient_manifest = project / "gradient-visual-manifest.json"
    gradient_required = args.require_gradient_visual or gradient_manifest.is_file()
    if args.require_gradient_visual and not gradient_manifest.is_file():
        add_step("gradient-visual", static_result={"name": "gradient-visual", "command": [], "exit_code": 2, "ok": False, "failure": "gradient_manifest_missing", "stdout": "", "stderr": ""}, cacheable=False, deps=route_deps, outputs=[run_dir / "gradient-visual-validation.json"])
    elif gradient_required:
        gradient_args = [str(SCRIPT_DIR / "validate_gradient_visual.py"), str(gradient_manifest), "--report", str(run_dir / "gradient-visual-validation.json")]
        if args.release:
            gradient_args.append("--require-verified")
        add_step("gradient-visual", gradient_args, deps=route_deps, outputs=[run_dir / "gradient-visual-validation.json"], inputs=[gradient_manifest])
    if args.handoff:
        add_step("handoff", [str(SCRIPT_DIR / "validate_handoff.py"), str(Path(args.handoff).resolve()), "--report", str(run_dir / "handoff-validation.json")], outputs=[run_dir / "handoff-validation.json"], inputs=[Path(args.handoff).resolve(), deck])
    if args.revision_label:
        add_step("revision-prepare", [str(SCRIPT_DIR / "revision_guard.py"), "prepare", str(project), "--deck", str(deck), "--label", args.revision_label], inputs=[project, deck], metadata={"revision_label": args.revision_label}, cacheable=False)
    add_step("environment", [str(SCRIPT_DIR / "probe_environment.py"), "--output", str(run_dir / "environment-report.json")], outputs=[run_dir / "environment-report.json"])
    add_step(
        "backend-binding",
        [
            str(SCRIPT_DIR / "validate_backend_binding.py"),
            str(run_dir / "environment-report.json"),
            str(routing_contract),
            "--skill-dir", str(SCRIPT_DIR.parent),
            "--report", str(run_dir / "backend-binding-validation.json"),
        ],
        deps=["environment", "routing-contract"],
        outputs=[run_dir / "backend-binding-validation.json"],
        inputs=[run_dir / "environment-report.json", routing_contract, SCRIPT_DIR / "authoring_backend.py", SCRIPT_DIR / "embed_fonts.py"],
    )
    if args.font_dir or args.require_cjk:
        font_args = [str(SCRIPT_DIR / "probe_fonts.py"), "--output", str(run_dir / "font-report.json")]
        if args.font_dir:
            font_args.extend(["--font-dir", str(Path(args.font_dir).resolve())])
        if args.require_cjk:
            font_args.append("--require-cjk")
        add_step("fonts", font_args, outputs=[run_dir / "font-report.json"], inputs=[Path(args.font_dir).resolve()] if args.font_dir else [], metadata={"require_cjk": args.require_cjk})
        font_manifest = Path(args.font_dir).resolve() / "font-manifest.json" if args.font_dir else None
        if args.font_dir and (font_manifest.is_file() or args.require_cjk):
            font_asset_args = [str(SCRIPT_DIR / "validate_font_asset.py"), "--font-dir", str(Path(args.font_dir).resolve()), "--report", str(run_dir / "font-asset-validation.json")]
            if args.require_cjk:
                font_asset_args.append("--require-cjk")
            add_step("font-asset", font_asset_args, deps=["fonts"], outputs=[run_dir / "font-asset-validation.json"], inputs=[Path(args.font_dir).resolve()])
    layout_path = project / "layout.json"
    typography_enabled = args.require_typography_calibration or typography_calibration.is_file()
    object_manifest = Path(args.object_manifest).resolve() if args.object_manifest else project / "slide-object-manifest.json"
    content_inventory = Path(args.content_inventory).resolve() if args.content_inventory else project / "content-inventory.json"
    content_inventory_required = bool(args.require_content_inventory)
    content_inventory_enabled = content_inventory_required or content_inventory.is_file()
    if content_inventory_required and not content_inventory.is_file():
        add_step(
            "content-inventory",
            static_result={"name": "content-inventory", "command": [], "exit_code": 2, "ok": False, "failure": "content_inventory_missing", "stdout": "", "stderr": ""},
            cacheable=False,
            deps=route_deps,
            outputs=[run_dir / "content-inventory-validation.json"],
        )
    elif content_inventory_enabled:
        content_args = [
            str(SCRIPT_DIR / "validate_content_inventory.py"),
            str(content_inventory),
            "--expected-pages", str(args.expected_pages),
            "--deck", str(deck),
            "--report", str(run_dir / "content-inventory-validation.json"),
        ]
        if object_manifest.is_file() or args.require_object_manifest:
            content_args.extend(["--object-manifest", str(object_manifest)])
        text_manifest_for_content = Path(args.text_manifest).resolve() if args.text_manifest else project / "text-layout-manifest.json"
        if text_manifest_for_content.is_file() or args.require_text_model:
            content_args.extend(["--text-manifest", str(text_manifest_for_content)])
        content_inputs = [content_inventory, deck]
        if object_manifest.is_file() or args.require_object_manifest:
            content_inputs.append(object_manifest)
        if text_manifest_for_content.is_file() or args.require_text_model:
            content_inputs.append(text_manifest_for_content)
        add_step("content-inventory", content_args, deps=route_deps, outputs=[run_dir / "content-inventory-validation.json"], inputs=content_inputs)
    chart_manifest = Path(args.chart_manifest).resolve() if args.chart_manifest else project / "chart-reconstruction.json"
    chart_manifest_required = bool(args.require_chart_manifest)
    chart_manifest_enabled = chart_manifest_required or chart_manifest.is_file()
    if chart_manifest_required and not chart_manifest.is_file():
        add_step(
            "chart-manifest",
            static_result={"name": "chart-manifest", "command": [], "exit_code": 2, "ok": False, "failure": "chart_manifest_missing", "stdout": "", "stderr": ""},
            cacheable=False,
            deps=route_deps,
            outputs=[run_dir / "chart-manifest-validation.json"],
        )
    elif chart_manifest_enabled:
        chart_args = [str(SCRIPT_DIR / "validate_chart_manifest.py"), str(chart_manifest), "--report", str(run_dir / "chart-manifest-validation.json")]
        if args.release:
            chart_args.append("--require-source")
        chart_inputs = [chart_manifest]
        chart_deps = list(route_deps)
        if content_inventory_enabled:
            chart_deps.append("content-inventory")
            if content_inventory.is_file():
                chart_args.extend(["--content-inventory", str(content_inventory)])
                chart_inputs.append(content_inventory)
        try:
            chart_data = json.loads(chart_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            chart_data = {}
        source_reference = chart_data.get("source_reference") if isinstance(chart_data, dict) else None
        if isinstance(source_reference, str) and source_reference:
            source_path = (chart_manifest.parent / source_reference).resolve()
            if source_path.is_file():
                chart_inputs.append(source_path)
        add_step("chart-manifest", chart_args, deps=chart_deps, outputs=[run_dir / "chart-manifest-validation.json"], inputs=list(dict.fromkeys(chart_inputs)))
    if args.require_object_manifest or object_manifest.is_file():
        object_args = [str(SCRIPT_DIR / "validate_object_manifest.py"), str(object_manifest), "--expected-pages", str(args.expected_pages), "--report", str(run_dir / "object-manifest-validation.json")]
        if args.require_independent_panels:
            object_args.append("--require-panels")
        add_step("object-manifest", object_args, outputs=[run_dir / "object-manifest-validation.json"], inputs=[object_manifest, deck])
    hash_manifests: list[Path] = []
    for candidate in [*(Path(path).resolve() for path in args.asset_manifest), *(project / name for name in ("asset-manifest.json", "panel-asset-manifest.json", "icon-asset-manifest.json", "imagegen-assets-manifest.json"))]:
        candidate = candidate.resolve()
        if candidate.is_file() and candidate not in hash_manifests:
            hash_manifests.append(candidate)
    asset_hashes_enabled = bool(hash_manifests) or args.require_asset_hashes
    if args.require_asset_hashes and not hash_manifests:
        add_step(
            "asset-hashes",
            static_result={"name": "asset-hashes", "command": [], "exit_code": 2, "ok": False, "failure": "asset_manifests_missing", "stdout": "", "stderr": ""},
            cacheable=False,
            deps=route_deps,
            outputs=[run_dir / "asset-hash-validation.json"],
        )
    elif hash_manifests:
        hash_args = [str(SCRIPT_DIR / "validate_asset_hashes.py"), *[str(path) for path in hash_manifests], "--base", str(project), "--report", str(run_dir / "asset-hash-validation.json")]
        if args.require_asset_hashes:
            hash_args.append("--require")
        add_step("asset-hashes", hash_args, deps=route_deps, outputs=[run_dir / "asset-hash-validation.json"], inputs=hash_manifests)
    registry_path = Path(args.manifest_registry).resolve() if args.manifest_registry else project / "manifest-registry.json"
    registry_enabled = bool(args.manifest_registry or registry_path.is_file())
    if args.require_manifest_registry and not registry_path.is_file():
        add_step("manifest-registry", static_result={"name": "manifest-registry", "command": [], "exit_code": 2, "ok": False, "failure": "manifest_registry_missing", "stdout": "", "stderr": ""}, cacheable=False, outputs=[run_dir / "manifest-registry-validation.json"])
    elif registry_enabled:
        registry_args = [str(SCRIPT_DIR / "manifest_registry.py"), "validate", str(registry_path), "--deck", str(deck), "--report", str(run_dir / "manifest-registry-validation.json")]
        if args.require_manifest_registry:
            registry_args.append("--require-gates")
        if args.require_asset_hashes:
            registry_args.append("--require-asset-hashes")
        add_step("manifest-registry", registry_args, outputs=[run_dir / "manifest-registry-validation.json"], inputs=[registry_path, deck, project / "slide-manifest.json"] + ([object_manifest] if object_manifest.is_file() else []))
    if args.reference:
        if layout_path.is_file():
            layout_args = [str(SCRIPT_DIR / "layout_guard.py"), str(Path(args.reference).resolve()), str(layout_path)]
            if args.strict_layout:
                layout_args.append("--strict")
            layout_args.extend(["--report", str(run_dir / "layout-guard.json")])
            add_step("layout-guard", layout_args, outputs=[run_dir / "layout-guard.json"], inputs=[Path(args.reference).resolve(), layout_path])
        else:
            add_step("layout-guard", static_result={"name": "layout-guard", "command": [], "exit_code": 2, "ok": False, "failure": "layout_json_missing", "stdout": "", "stderr": ""}, outputs=[run_dir / "layout-guard.json"], cacheable=False)
    if args.reference_dir:
        reference_dir = Path(args.reference_dir).resolve()
        if layout_path.is_file():
            multi_layout_args = [
                str(SCRIPT_DIR / "validate_multipage_layout.py"),
                str(reference_dir),
                str(layout_path),
                "--expected-pages", str(args.expected_pages),
                "--expected-ratio", str(args.expected_ratio or (16 / 9)),
                "--report", str(run_dir / "multipage-layout-guard.json"),
            ]
            if args.strict_layout or args.require_multipage_layout or args.release:
                multi_layout_args.append("--strict")
            if affected_pages:
                multi_layout_args.extend(["--pages", ",".join(str(page) for page in affected_pages)])
            add_step(
                "multipage-layout-guard",
                multi_layout_args,
                deps=route_deps,
                outputs=[run_dir / "multipage-layout-guard.json"],
                inputs=[reference_dir, layout_path],
                metadata={"affected_pages": affected_pages or "all", "strict": bool(args.strict_layout or args.require_multipage_layout or args.release)},
            )
        elif args.require_multipage_layout:
            add_step(
                "multipage-layout-guard",
                static_result={"name": "multipage-layout-guard", "command": [], "exit_code": 2, "ok": False, "failure": "layout_json_missing", "stdout": "", "stderr": ""},
                cacheable=False,
                deps=route_deps,
                outputs=[run_dir / "multipage-layout-guard.json"],
            )
    if imagegen_required:
        imagegen_args = [str(SCRIPT_DIR / "validate_imagegen_assets_manifest.py"), str(project / "imagegen-assets-manifest.json"), "--report", str(run_dir / "imagegen-assets-validation.json")]
        if args.require_asset_hashes:
            imagegen_args.append("--require-hashes")
        add_step("imagegen-assets", imagegen_args, outputs=[run_dir / "imagegen-assets-validation.json"], inputs=[project / "imagegen-assets-manifest.json"])
    if icon_required:
        icon_args = [str(SCRIPT_DIR / "validate_icon_assets.py"), str(project / "icon-asset-manifest.json"), "--report", str(run_dir / "icon-assets-validation.json")]
        if args.require_asset_hashes:
            icon_args.append("--require-hashes")
        add_step("icon-assets", icon_args, outputs=[run_dir / "icon-assets-validation.json"], inputs=[project / "icon-asset-manifest.json"])
        add_step("icon-layers", [str(SCRIPT_DIR / "audit_icon_layers.py"), str(project / "icon-asset-manifest.json"), "--report", str(run_dir / "icon-layer-audit.json")], outputs=[run_dir / "icon-layer-audit.json"], inputs=[project / "icon-asset-manifest.json"])
    inspection_path = run_dir / "inspection.json"
    render_report_path = run_dir / "render-report.json"
    add_step("inspection", [str(SCRIPT_DIR / "inspect_pptx.py"), str(deck), "--report", str(inspection_path)], outputs=[inspection_path], inputs=[deck])
    if args.require_object_manifest or object_manifest.is_file():
        audit_args = [str(SCRIPT_DIR / "inspect_editable_objects.py"), str(deck), "--object-manifest", str(object_manifest), "--report", str(run_dir / "editable-object-audit.json")]
        if args.require_independent_panels:
            audit_args.append("--require-independent-panels")
        add_step("editable-object-audit", audit_args, outputs=[run_dir / "editable-object-audit.json"], inputs=[deck, object_manifest])
        semantic_text_manifest = Path(args.text_manifest).resolve() if args.text_manifest else project / "text-layout-manifest.json"
        semantic_asset_manifests = [Path(path).resolve() for path in args.asset_manifest]
        for candidate in (
            project / "asset-manifest.json",
            project / "panel-asset-manifest.json",
            project / "icon-asset-manifest.json",
            project / "imagegen-assets-manifest.json",
        ):
            if candidate.is_file() and candidate not in semantic_asset_manifests:
                semantic_asset_manifests.append(candidate)
        semantic_args = [
            str(SCRIPT_DIR / "semantic_object_audit.py"), str(deck),
            "--object-manifest", str(object_manifest),
            "--report", str(run_dir / "semantic-object-audit.json"),
        ]
        semantic_inputs = [deck, object_manifest]
        if semantic_text_manifest.is_file() or args.text_manifest:
            semantic_args.extend(["--text-manifest", str(semantic_text_manifest)])
            semantic_inputs.append(semantic_text_manifest)
        for asset_manifest in semantic_asset_manifests:
            semantic_args.extend(["--asset-manifest", str(asset_manifest)])
            semantic_inputs.append(asset_manifest)
        if args.require_source_hashes:
            semantic_args.append("--require-source-hashes")
        if args.release:
            semantic_args.append("--require-independent-text-manifest")
        add_step("semantic-object-audit", semantic_args, deps=["editable-object-audit"], outputs=[run_dir / "semantic-object-audit.json"], inputs=semantic_inputs)
    render_args = [str(SCRIPT_DIR / "render_pptx.py"), str(deck), "--output-dir", str(render_dir), "--dpi", str(args.dpi), "--report", str(render_report_path)]
    if args.font_dir:
        render_args.extend(["--font-dir", str(Path(args.font_dir).resolve())])
    if page_cache_dir:
        render_args.extend(["--page-cache-dir", str(page_cache_dir)])
    if affected_pages:
        render_args.extend(["--pages", ",".join(str(page) for page in affected_pages)])
    add_step("render", render_args, deps=["environment"], outputs=[render_dir, render_report_path], inputs=[deck] + ([Path(args.font_dir).resolve()] if args.font_dir else []), metadata={"affected_pages": affected_pages or "all", "dpi": args.dpi, "page_cache_enabled": bool(page_cache_dir), "page_cache_dir": str(page_cache_dir) if page_cache_dir else None})
    if args.require_typography_calibration and not typography_calibration.is_file():
        add_step(
            "typography-calibration",
            static_result={"name": "typography-calibration", "command": [], "exit_code": 2, "ok": False, "failure": "typography_calibration_missing", "stdout": "", "stderr": ""},
            cacheable=False,
            outputs=[run_dir / "typography-calibration-validation.json"],
        )
    elif typography_calibration.is_file():
        add_step(
            "typography-calibration",
            [str(SCRIPT_DIR / "validate_typography_calibration.py"), str(typography_calibration), "--report", str(run_dir / "typography-calibration-validation.json")],
            deps=["render"],
            outputs=[run_dir / "typography-calibration-validation.json"],
            inputs=[typography_calibration, render_dir],
        )
    selected_count = len(affected_pages) if affected_pages else args.expected_pages
    visual_args = [str(SCRIPT_DIR / "validate_render.py"), str(render_dir), "--expected-pages", str(selected_count), "--report", str(run_dir / "render-visual-gate.json")]
    if affected_pages:
        visual_args.extend(["--pages", ",".join(str(page) for page in affected_pages)])
    for region in list(args.region) + list(args.affected_region):
        visual_args.extend(["--region", region])
    add_step("render-visual-gate", visual_args, deps=["render"], outputs=[run_dir / "render-visual-gate.json"], inputs=[render_dir], metadata={"affected_pages": affected_pages or "all", "affected_regions": list(args.affected_region)})
    if args.font_dir or args.require_cjk:
        font_delivery_args = [str(SCRIPT_DIR / "validate_font_delivery.py"), "--font-report", str(run_dir / "font-report.json"), "--inspection", str(inspection_path), "--render-report", str(render_report_path), "--render-visual-gate", str(run_dir / "render-visual-gate.json"), "--profile", "portable", "--report", str(run_dir / "font-delivery-validation.json")]
        if args.font_dir and (font_manifest.is_file() or args.require_cjk):
            font_delivery_args.extend(["--font-asset-report", str(run_dir / "font-asset-validation.json")])
        if args.release:
            font_delivery_args.append("--require-embedded")
        font_deps = ["fonts", "inspection", "render", "render-visual-gate"]
        if args.font_dir and (font_manifest.is_file() or args.require_cjk):
            font_deps.append("font-asset")
        add_step("font-delivery", font_delivery_args, deps=font_deps, outputs=[run_dir / "font-delivery-validation.json"], inputs=[run_dir / "font-report.json", inspection_path, render_report_path, run_dir / "render-visual-gate.json"] + ([run_dir / "font-asset-validation.json"] if args.font_dir and (font_manifest.is_file() or args.require_cjk) else []), metadata={"require_embedded": args.release})
    if args.reference:
        comparison_args = [str(SCRIPT_DIR / "compare_visual.py"), str(render_dir / "slide-1.png"), str(Path(args.reference).resolve()), "--report", str(run_dir / "visual-comparison.json")]
        if args.expected_ratio is not None:
            comparison_args.extend(["--expected-ratio", str(args.expected_ratio)])
        if args.visual_threshold is not None:
            comparison_args.extend(["--threshold", str(args.visual_threshold)])
        add_step("visual-comparison", comparison_args, deps=["render"], outputs=[run_dir / "visual-comparison.json"], inputs=[render_dir / "slide-1.png", Path(args.reference).resolve()], metadata={"affected_pages": affected_pages or "all"})
    elif args.reference_dir:
        comparison_args = [str(SCRIPT_DIR / "compare_visual_deck.py"), str(render_dir), str(Path(args.reference_dir).resolve()), "--expected-pages", str(args.expected_pages), "--report", str(run_dir / "visual-comparison.json")]
        if args.expected_ratio is not None:
            comparison_args.extend(["--expected-ratio", str(args.expected_ratio)])
        if args.visual_threshold is not None:
            comparison_args.extend(["--threshold", str(args.visual_threshold)])
        if affected_pages:
            comparison_args.extend(["--pages", ",".join(str(page) for page in affected_pages)])
        add_step("visual-comparison", comparison_args, deps=["render"], outputs=[run_dir / "visual-comparison.json"], inputs=[render_dir, Path(args.reference_dir).resolve()], metadata={"affected_pages": affected_pages or "all"})
    if args.preview_dir:
        preview_dir = Path(args.preview_dir).resolve()
        preview_args = [
            str(SCRIPT_DIR / "validate_preview_consistency.py"),
            str(render_dir),
            str(preview_dir),
            "--expected-pages", str(args.expected_pages),
            "--report", str(run_dir / "preview-consistency-validation.json"),
        ]
        if args.preview_threshold is not None:
            preview_args.extend(["--threshold", str(args.preview_threshold)])
        if args.require_preview_consistency or args.release:
            preview_args.append("--require")
        add_step(
            "preview-consistency",
            preview_args,
            deps=["render"],
            outputs=[run_dir / "preview-consistency-validation.json"],
            inputs=[render_dir, preview_dir],
            metadata={"expected_pages": args.expected_pages, "threshold": args.preview_threshold, "required": bool(args.require_preview_consistency or args.release)},
        )
    if args.reference:
        reference_audit_args = [str(SCRIPT_DIR / "reference_audit.py"), str(Path(args.reference).resolve()), str(render_dir / "slide-1.png"), "--report", str(run_dir / "reference-audit.json")]
        if args.expected_ratio is not None:
            reference_audit_args.extend(["--expected-ratio", str(args.expected_ratio)])
        add_step("reference-audit", reference_audit_args, deps=["render"] + (["source-images"] if "source-images" in {task.name for task in executor.tasks} else []), outputs=[run_dir / "reference-audit.json"], inputs=[Path(args.reference).resolve(), render_dir / "slide-1.png"])
    elif args.reference_dir:
        reference_audit_args = [str(SCRIPT_DIR / "reference_audit_deck.py"), str(Path(args.reference_dir).resolve()), str(render_dir), "--expected-pages", str(args.expected_pages), "--report", str(run_dir / "reference-audit.json")]
        if args.expected_ratio is not None:
            reference_audit_args.extend(["--expected-ratio", str(args.expected_ratio)])
        if affected_pages:
            reference_audit_args.extend(["--pages", ",".join(str(page) for page in affected_pages)])
        add_step("reference-audit", reference_audit_args, deps=["render"] + (["source-images"] if "source-images" in {task.name for task in executor.tasks} else []), outputs=[run_dir / "reference-audit.json"], inputs=[Path(args.reference_dir).resolve(), render_dir])
    if args.reference and layout_path.is_file():
        visual_qa_args = [str(SCRIPT_DIR / "visual_compare_qa.py"), str(Path(args.reference).resolve()), str(render_dir / "slide-1.png"), "--out-dir", str(run_dir / "visual-qa")]
        if args.expected_ratio is not None:
            visual_qa_args.extend(["--expected-ratio", str(args.expected_ratio)])
        add_step("visual-compare-qa", visual_qa_args, deps=["render"], outputs=[run_dir / "visual-qa"], inputs=[Path(args.reference).resolve(), render_dir / "slide-1.png"])
    if args.ocr_lang or args.require_ocr:
        ocr_args = [str(SCRIPT_DIR / "ocr_text_check.py"), str(deck), str(render_dir), "--lang", args.ocr_lang or "eng", "--report", str(run_dir / "ocr-text-check.json")]
        if args.require_ocr:
            ocr_args.append("--require-ocr")
        add_step("ocr-text-check", ocr_args, deps=["render"], outputs=[run_dir / "ocr-text-check.json"], inputs=[deck, render_dir], metadata={"language": args.ocr_lang or "eng", "affected_pages": affected_pages or "all"})
    panel_manifest = project / "panel-asset-manifest.json"
    panel_gate_required = panel_manifest.is_file() or args.require_independent_panels or args.require_panel_approval
    if panel_gate_required:
        panel_args = [str(SCRIPT_DIR / "validate_panel_assets.py"), str(panel_manifest), "--assets-dir", str(project), "--report", str(run_dir / "panel-assets-validation.json"), "--strict"]
        # Draft/technical runs need independent-panel evidence but do not
        # possess a human approval record yet. Approval is a release/closeout
        # gate and is added only when explicitly requested (or promoted by
        # the strict release profile).
        if args.require_panel_approval:
            panel_args.append("--require-approved")
        if args.require_asset_hashes:
            panel_args.append("--require-hashes")
        if args.require_independent_panels:
            panel_args.append("--require-independent")
        if args.expected_panel_count is not None:
            panel_args.extend(["--expected-count", str(args.expected_panel_count)])
        add_step("panel-assets", panel_args, outputs=[run_dir / "panel-assets-validation.json"], inputs=[panel_manifest])
    if args.require_text_style_map and not layout_path.is_file():
        add_step("text-style-map", static_result={"name": "text-style-map", "command": [], "exit_code": 2, "ok": False, "failure": "layout_json_missing", "stdout": "", "stderr": ""}, cacheable=False, deps=route_deps, outputs=[run_dir / "text-style-map-validation.json"])
    elif args.require_text_style_map and layout_path.is_file():
        text_style_args = [str(SCRIPT_DIR / "validate_text_style_map.py"), str(layout_path), "--report", str(run_dir / "text-style-map-validation.json")]
        if args.strict_layout or args.release:
            text_style_args.extend(["--strict", "--require-source-bbox"])
        add_step("text-style-map", text_style_args, deps=route_deps, outputs=[run_dir / "text-style-map-validation.json"], inputs=[layout_path])
    text_manifest = Path(args.text_manifest).resolve() if args.text_manifest else project / "text-layout-manifest.json"
    text_model_enabled = bool(args.text_manifest or text_manifest.is_file())
    if args.require_text_model and not text_manifest.is_file():
        add_step("text-model", static_result={"name": "text-model", "command": [], "exit_code": 2, "ok": False, "failure": "text_manifest_missing", "stdout": "", "stderr": ""}, cacheable=False, outputs=[run_dir / "text-layout-validation.json"])
    elif text_model_enabled:
        text_model_args = [str(SCRIPT_DIR / "text_model.py"), "validate", str(text_manifest), "--report", str(run_dir / "text-layout-validation.json")]
        if args.require_text_model:
            text_model_args.append("--strict")
            # source_bbox is reference-image evidence. Visual-creation
            # layouts have no source viewport, so requiring it creates false
            # blockers; reference reconstruction still enforces it.
            if reference_route:
                text_model_args.append("--require-source-bbox")
        add_step("text-model", text_model_args, outputs=[run_dir / "text-layout-validation.json"], inputs=[text_manifest])
    manifest_args = [str(SCRIPT_DIR / "validate_manifest.py"), str(project / "slide-manifest.json"), "--kind", "slide", "--report", str(run_dir / "manifest-validation.json")]
    if args.require_editability:
        manifest_args.append("--require-editability")
    asset_manifest = project / "asset-manifest.json"
    if asset_manifest.is_file():
        manifest_args.extend(["--asset-manifest", str(asset_manifest)])
    add_step("manifest", manifest_args, outputs=[run_dir / "manifest-validation.json"], inputs=[project / "slide-manifest.json"] + ([asset_manifest] if asset_manifest.is_file() else []))
    project_args = [str(SCRIPT_DIR / "validate_project.py"), str(project), "--deck", str(deck), "--inspection", str(inspection_path), "--render-report", str(render_report_path), "--render-visual-gate", str(run_dir / "render-visual-gate.json"), "--manifest-validation", str(run_dir / "manifest-validation.json"), "--report", str(run_dir / "project-validation.json")]
    if args.require_editability:
        project_args.append("--require-editability")
    if args.require_object_manifest or object_manifest.is_file():
        project_args.extend(["--semantic-object-audit", str(run_dir / "semantic-object-audit.json"), "--object-manifest", str(object_manifest)])
        if args.require_object_manifest:
            project_args.append("--require-semantic-object-audit")
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
    if content_inventory_enabled:
        project_args.extend(["--content-inventory-validation", str(run_dir / "content-inventory-validation.json")])
        if content_inventory_required:
            project_args.append("--require-content-inventory")
    if chart_manifest_enabled:
        project_args.extend(["--chart-manifest-validation", str(run_dir / "chart-manifest-validation.json")])
        if chart_manifest_required:
            project_args.append("--require-chart-manifest")
    if asset_hashes_enabled:
        project_args.extend(["--asset-hash-validation", str(run_dir / "asset-hash-validation.json")])
        if args.require_asset_hashes:
            project_args.append("--require-asset-hashes")
    if any(task.name == "multipage-layout-guard" for task in executor.tasks):
        project_args.extend(["--multipage-layout-validation", str(run_dir / "multipage-layout-guard.json")])
        if args.require_multipage_layout:
            project_args.append("--require-multipage-layout")
    if args.preview_dir:
        project_args.extend(["--preview-consistency-validation", str(run_dir / "preview-consistency-validation.json")])
        if args.require_preview_consistency or args.release:
            project_args.append("--require-preview-consistency")
    project_deps = ["inspection", "render", "render-visual-gate", "manifest", "backend-binding"]
    if args.require_object_manifest or object_manifest.is_file():
        project_deps.append("semantic-object-audit")
    for candidate in ("route", "visual-generation", "visual-comparison", "ocr-text-check", "multipage-layout-guard", "preview-consistency", "typography-calibration", "chart-manifest"):
        if any(task.name == candidate for task in executor.tasks):
            project_deps.append(candidate)
    if content_inventory_enabled:
        project_deps.append("content-inventory")
    if chart_manifest_enabled:
        project_deps.append("chart-manifest")
    if asset_hashes_enabled:
        project_deps.append("asset-hashes")
    project_inputs = [
        deck,
        project / "slide-manifest.json",
        inspection_path,
        render_report_path,
        run_dir / "render-visual-gate.json",
        run_dir / "manifest-validation.json",
    ]
    for candidate in (
        "asset-manifest.json",
        "layout.json",
        "slide-object-manifest.json",
        "manifest-registry.json",
        "panel-asset-manifest.json",
        "icon-asset-manifest.json",
        "imagegen-assets-manifest.json",
        "text-layout-manifest.json",
        "handoff.json",
        "validation-report.json",
        "issue-log.json",
        "typography-calibration.json",
        "chart-reconstruction.json",
        "visual-generation-plan.json",
        "visual-generation-manifest.json",
    ):
        path = project / candidate
        if path.is_file():
            project_inputs.append(path)
    for candidate in (args.handoff, args.issue_log, args.route_decision):
        if candidate:
            path = Path(candidate).resolve()
            if path.is_file():
                project_inputs.append(path)
    project_inputs.extend(
        [run_dir / "route-validation.json"] if args.route_decision else []
    )
    project_inputs.extend(
        [run_dir / "visual-generation-validation.json"] if visual_generation_enabled else []
    )
    project_inputs.extend(
        [run_dir / "visual-comparison.json"] if args.reference or args.reference_dir else []
    )
    project_inputs.extend(
        [run_dir / "ocr-text-check.json"] if args.ocr_lang or args.require_ocr else []
    )
    project_inputs.extend(
        [run_dir / "content-inventory-validation.json"] if content_inventory_enabled else []
    )
    project_inputs.extend(
        [run_dir / "chart-manifest-validation.json"] if chart_manifest_enabled else []
    )
    project_inputs.extend(
        [run_dir / "asset-hash-validation.json"] if asset_hashes_enabled else []
    )
    project_inputs.extend(
        [run_dir / "multipage-layout-guard.json"] if any(task.name == "multipage-layout-guard" for task in executor.tasks) else []
    )
    project_inputs.extend(
        [run_dir / "preview-consistency-validation.json"] if args.preview_dir else []
    )
    project_inputs.extend(
        [run_dir / "semantic-object-audit.json"] if args.require_object_manifest or object_manifest.is_file() else []
    )
    project_inputs.extend(
        [run_dir / "typography-calibration-validation.json"] if typography_enabled else []
    )
    add_step("project", project_args, deps=project_deps, outputs=[run_dir / "project-validation.json"], inputs=project_inputs, metadata={"affected_pages": affected_pages or "all", "affected_regions": list(args.affected_region)})
    def collect_quality_evidence(bundle_path=None, bundle_key="report_bundle_preflight"):
        evidence = {}
        bundle_path = Path(bundle_path) if bundle_path else run_dir / "report-bundle-validation.json"
        for name, path in (
            ("skill_package_validation", run_dir / "skill-package-validation.json"),
            ("routing_contract_validation", run_dir / "routing-contract-validation.json"),
            ("backend_binding_validation", run_dir / "backend-binding-validation.json"),
            ("asset_hash_validation", run_dir / "asset-hash-validation.json"),
            ("multipage_layout_guard", run_dir / "multipage-layout-guard.json"),
            ("preview_consistency", run_dir / "preview-consistency-validation.json"),
            ("typography_calibration", run_dir / "typography-calibration-validation.json"),
            ("render", run_dir / "render-report.json"),
            ("render_visual_gate", run_dir / "render-visual-gate.json"),
            ("visual_comparison", run_dir / "visual-comparison.json"),
            ("ocr_text_check", run_dir / "ocr-text-check.json"),
            ("route_validation", run_dir / "route-validation.json"),
            ("visual_generation_validation", run_dir / "visual-generation-validation.json"),
            ("manifest_validation", run_dir / "manifest-validation.json"),
            ("manifest_registry_validation", run_dir / "manifest-registry-validation.json"),
            ("text_layout_validation", run_dir / "text-layout-validation.json"),
            ("imagegen_assets_validation", run_dir / "imagegen-assets-validation.json"),
            ("icon_assets_validation", run_dir / "icon-assets-validation.json"),
            ("icon_layer_audit", run_dir / "icon-layer-audit.json"),
            ("object_manifest_validation", run_dir / "object-manifest-validation.json"),
            ("editable_object_audit", run_dir / "editable-object-audit.json"),
            ("semantic_object_audit", run_dir / "semantic-object-audit.json"),
            ("panel_assets_validation", run_dir / "panel-assets-validation.json"),
            ("text_style_map_validation", run_dir / "text-style-map-validation.json"),
            ("source_image_validation", run_dir / "source-image-validation.json"),
            ("gradient_visual_validation", run_dir / "gradient-visual-validation.json"),
            ("reference_audit", run_dir / "reference-audit.json"),
            ("content_inventory_validation", run_dir / "content-inventory-validation.json"),
            ("chart_manifest_validation", run_dir / "chart-manifest-validation.json"),
            ("visual_compare_qa", run_dir / "visual-qa/report.json"),
            ("project_report_aggregate", run_dir / "project-report.json"),
            (bundle_key, bundle_path),
            ("font_asset_validation", run_dir / "font-asset-validation.json"),
            ("font_delivery_validation", run_dir / "font-delivery-validation.json"),
            ("handoff_validation", run_dir / "handoff-validation.json"),
            ("signoff_validation", run_dir / "signoff-validation.json"),
            ("release_check", run_dir / "release-check.json"),
        ):
            report = load_report(path)
            if report is not None:
                evidence[name] = summarize_report(name, path, report)
        degradations = []
        ocr_report = evidence.get("ocr_text_check")
        if ocr_report and (ocr_report.get("native_status") or ocr_report.get("status")) == "unavailable":
            degradations.append({"code": "ocr_unavailable", "language": ocr_report.get("language"), "requires_human_review": True})
        return evidence, degradations

    def build_pipeline_result(current_steps, evidence, degradations, release_report=None, bundle_report=None, signoff_report=None):
        failed = [step["name"] for step in current_steps if not step["ok"]]
        technical_failed = [step["name"] for step in current_steps if not step["ok"] and step["name"] not in {"signoff-validation", "release-check"}]
        technical_valid = not technical_failed
        release_check_passed = bool(release_report and release_report.get("status") == "passed")
        bundle_passed = bool(bundle_report and bundle_report.get("valid") is True)
        signoff_passed = bool(signoff_report and signoff_report.get("valid") is True)
        release_eligible = bool(args.release and technical_valid and bundle_passed and signoff_passed and release_check_passed)
        render_evidence = evidence.get("render", {})
        page_cache_evidence = render_evidence.get("page_cache", {}) if isinstance(render_evidence, dict) else {}
        conversion_evidence = render_evidence.get("conversion", {}) if isinstance(render_evidence, dict) else {}
        deck_hash = sha256(deck)
        source_references = [{"source_id": "deck", "path": str(deck), "sha256": deck_hash}]
        for item in evidence.values():
            source = item.get("source") if isinstance(item, dict) else None
            if isinstance(source, dict) and source.get("path"):
                source_references.append(source)
        return {
            "schema": "ai-ppt-plus/pipeline-run/v2",
            "valid": technical_valid,
            "status": "passed" if technical_valid else "failed",
            "technical_valid": technical_valid,
            "technical_status": "passed" if technical_valid else "failed",
            "validation_scope": "incremental" if affected_pages else "full",
            "full_deck_validation_required": bool(affected_pages),
            "release_profile": "strict" if args.release else "not_run",
            "release_eligible": release_eligible,
            "release_status": release_report.get("status") if release_report else "not_run",
            "human_review_required": True,
            "human_review_status": "approved" if signoff_passed else "pending",
            "run_id": run_id,
            "project": str(project),
            "deck": str(deck),
            "deck_sha256": deck_hash,
            "source": {"deck": str(deck), "deck_sha256": deck_hash, "project": str(project)},
            "source_references": source_references,
            "run_dir": str(run_dir),
            "report_index": str(run_dir / "report-index.json"),
            "project_report": str(run_dir / "project-report.json"),
            "execution": {
                "mode": args.execution_mode,
                "cache_dir": str(cache_dir) if cache_dir else None,
                "parallel_workers": executor.max_workers,
                "tasks_total": len(current_steps),
                "cache_hits": sum(1 for step in current_steps if step.get("cache_hit") is True),
                "duration_ms": executor.last_wall_duration_ms,
                "task_duration_ms_sum": round(sum(float(step.get("duration_ms", 0) or 0) for step in current_steps), 3),
                "affected_pages": affected_pages or "all",
                "affected_regions": list(args.affected_region),
                "page_cache": {
                    "enabled": page_cache_evidence.get("enabled", False),
                    "hits": page_cache_evidence.get("hits", 0),
                    "misses": page_cache_evidence.get("misses", 0),
                    "stored": page_cache_evidence.get("stored", 0),
                },
                "render_conversion_skipped": conversion_evidence.get("skipped", False),
            },
            "steps": current_steps,
            "failed_steps": failed,
            "technical_failed_steps": technical_failed,
            "next_state": "delivered" if release_eligible else "validated" if technical_valid else "revision-required",
            "human_visual_review_required": True,
            "human_signoff_required": True,
            "quality_evidence": evidence,
            "quality_degradations": degradations,
            "release_evidence": {
                "technical_valid": technical_valid,
                "report_bundle_valid": bundle_passed if args.release else False,
                "human_signoff_valid": signoff_passed if args.release else False,
                "release_check_passed": release_check_passed if args.release else False,
            },
        }

    # The route and package contracts are true prerequisites, not just
    # informational reports.  A failed decision must block every downstream
    # gate so a parallel DAG cannot continue with an unapproved authority.
    prerequisite = "route" if args.route_decision else "routing-contract"
    for task in executor.tasks:
        if task.name in {"skill-package", "routing-contract", "route"}:
            continue
        task.deps = tuple(dict.fromkeys((*task.deps, prerequisite)))
    steps = executor.run()
    report_entries = [
        {"report_type": "skill-package-validation", "path": "skill-package-validation.json", "required": True, "stage": "intake"},
        {"report_type": "routing-contract-validation", "path": "routing-contract-validation.json", "required": True, "stage": "intake"},
        {"report_type": "backend-binding-validation", "path": "backend-binding-validation.json", "required": True, "stage": "intake"},
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
            {"report_type": "semantic-object-audit", "path": "semantic-object-audit.json", "required": True, "stage": "validated"},
        ])
    if panel_gate_required:
        report_entries.append({"report_type": "panel-assets-validation", "path": "panel-assets-validation.json", "required": True, "stage": "validated"})
    if args.require_text_style_map and layout_path.is_file():
        report_entries.append({"report_type": "text-style-map-validation", "path": "text-style-map-validation.json", "required": True, "stage": "validated"})
    if text_model_enabled or args.require_text_model:
        report_entries.append({"report_type": "text-layout-validation", "path": "text-layout-validation.json", "required": args.require_text_model, "stage": "validated"})
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
    if any(task.name == "multipage-layout-guard" for task in executor.tasks):
        report_entries.append({"report_type": "multipage-layout-guard", "path": "multipage-layout-guard.json", "required": True, "stage": "validated"})
    if args.preview_dir:
        report_entries.append({"report_type": "preview-consistency", "path": "preview-consistency-validation.json", "required": bool(args.require_preview_consistency or args.release), "stage": "validated"})
    if typography_enabled:
        report_entries.append({"report_type": "typography-calibration-validation", "path": "typography-calibration-validation.json", "required": True, "stage": "validated"})
    if unique_reference_sources:
        report_entries.append({"report_type": "source-image-validation", "path": "source-image-validation.json", "required": True, "stage": "source-analyzed"})
    if gradient_required:
        report_entries.append({"report_type": "gradient-visual-validation", "path": "gradient-visual-validation.json", "required": True, "stage": "validated"})
    if args.reference or args.reference_dir:
        report_entries.append({"report_type": "reference-audit", "path": "reference-audit.json", "required": True, "stage": "validated"})
    if content_inventory_enabled:
        report_entries.append({"report_type": "content-inventory-validation", "path": "content-inventory-validation.json", "required": content_inventory_required, "stage": "validated"})
    if chart_manifest_enabled:
        report_entries.append({"report_type": "chart-manifest-validation", "path": "chart-manifest-validation.json", "required": chart_manifest_required, "stage": "validated"})
    if asset_hashes_enabled:
        report_entries.append({"report_type": "asset-hash-validation", "path": "asset-hash-validation.json", "required": args.require_asset_hashes, "stage": "validated"})
    if args.font_dir or args.require_cjk:
        report_entries.append({"report_type": "font", "path": "font-report.json", "required": True, "stage": "intake"})
    if (run_dir / "font-asset-validation.json").is_file():
        report_entries.append({"report_type": "font-asset-validation", "path": "font-asset-validation.json", "required": True, "stage": "intake"})
    if (run_dir / "font-delivery-validation.json").is_file():
        report_entries.append({"report_type": "font-delivery-validation", "path": "font-delivery-validation.json", "required": True, "stage": "validated"})
    if args.route_decision:
        report_entries.append({"report_type": "route-validation", "path": "route-validation.json", "required": args.require_route, "stage": "design-system-ready"})
    if visual_generation_enabled:
        report_entries.append({"report_type": "visual-generation-validation", "path": "visual-generation-validation.json", "required": args.require_visual_generation, "stage": "visual-draft"})
    if args.handoff:
        report_entries.append({"report_type": "handoff-validation", "path": "handoff-validation.json", "required": True, "stage": "validated"})
    if args.reference or args.reference_dir:
        report_entries.append({"report_type": "visual-comparison", "path": "visual-comparison.json", "required": True, "stage": "validated"})
    if args.ocr_lang or args.require_ocr:
        report_entries.append({"report_type": "ocr-text-check", "path": "ocr-text-check.json", "required": args.require_ocr, "stage": "validated"})
    step_status = {step["name"]: step["ok"] for step in steps}
    for entry in report_entries:
        step_name = {"skill-package-validation": "skill-package", "routing-contract-validation": "routing-contract", "backend-binding-validation": "backend-binding", "asset-hash-validation": "asset-hashes", "render-visual-gate": "render-visual-gate", "manifest-validation": "manifest", "manifest-registry-validation": "manifest-registry", "text-layout-validation": "text-model", "project-validation": "project", "project-report-aggregate": "project-report-aggregate", "visual-comparison": "visual-comparison", "visual-compare-qa": "visual-compare-qa", "layout-guard": "layout-guard", "multipage-layout-guard": "multipage-layout-guard", "preview-consistency": "preview-consistency", "typography-calibration-validation": "typography-calibration", "imagegen-assets-validation": "imagegen-assets", "icon-assets-validation": "icon-assets", "icon-layer-audit": "icon-layers", "ocr-text-check": "ocr-text-check", "route-validation": "route", "visual-generation-validation": "visual-generation", "handoff-validation": "handoff", "font": "fonts", "font-asset-validation": "font-asset", "font-delivery-validation": "font-delivery", "environment": "environment", "inspection": "inspection", "render": "render", "object-manifest-validation": "object-manifest", "editable-object-audit": "editable-object-audit", "semantic-object-audit": "semantic-object-audit", "panel-assets-validation": "panel-assets", "text-style-map-validation": "text-style-map", "source-image-validation": "source-images", "gradient-visual-validation": "gradient-visual", "reference-audit": "reference-audit", "content-inventory-validation": "content-inventory", "chart-manifest-validation": "chart-manifest"}.get(entry["report_type"])
        if step_name in step_status:
            entry["step_ok"] = step_status[step_name]
    stage = "revision-required" if any(not step.get("ok") for step in steps) else "validated"
    report_index = {"schema": "ai-ppt-plus/report-index/v1", "project_id": project.name, "revision": args.revision_label or "working", "stage": stage, "validation_scope": "incremental" if affected_pages else "full", "deck_path": str(deck), "deck_sha256": sha256(deck), "source_references": [{"source_id": "deck", "path": str(deck), "sha256": sha256(deck)}], "reports": report_entries}
    atomic_write_json(run_dir / "report-index.json", report_index)
    steps.append(run_step(run_dir, "project-report-aggregate", [str(SCRIPT_DIR / "aggregate_project_reports.py"), str(run_dir / "report-index.json"), "--report", str(run_dir / "project-report.json")]))
    preflight_bundle_path = run_dir / "report-bundle-preflight.json"
    final_bundle_path = run_dir / "report-bundle-validation.json"
    preliminary_evidence, preliminary_degradations = collect_quality_evidence()
    preliminary_result = build_pipeline_result(steps, preliminary_evidence, preliminary_degradations)
    atomic_write_json(run_dir / "pipeline-result.json", preliminary_result)
    bundle_args = [
        str(SCRIPT_DIR / "validate_report_bundle.py"),
        str(run_dir / "pipeline-result.json"),
        "--report-index", str(run_dir / "report-index.json"),
        "--project-report", str(run_dir / "project-report.json"),
        "--deck", str(deck),
        "--report", str(preflight_bundle_path),
    ]
    if args.release:
        bundle_args.append("--require-full")
    bundle_step = run_step(run_dir, "report-bundle-preflight", bundle_args)
    bundle_step["deps"] = ["project-report-aggregate"]
    steps.append(bundle_step)
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
            "--object-manifest", str(object_manifest),
            "--semantic-object-audit", str(run_dir / "semantic-object-audit.json"),
            "--require-semantic-object-audit",
            "--manifest-registry-validation", str(run_dir / "manifest-registry-validation.json"),
            "--require-manifest-registry",
            "--text-layout-validation", str(run_dir / "text-layout-validation.json"),
            "--require-text-model",
            "--require-embedded-fonts",
            "--font-delivery-report", str(run_dir / "font-delivery-validation.json"),
            "--require-font-delivery",
            "--project-report", str(run_dir / "project-report.json"),
            "--require-project-report",
            "--report-bundle-validation", str(preflight_bundle_path),
            "--require-report-bundle",
            "--render-visual-gate", str(run_dir / "render-visual-gate.json"),
            "--expected-slides", str(args.expected_pages),
            "--quality-score", str(args.quality_score),
            "--quality-threshold", str(args.quality_threshold),
            "--output", str(run_dir / "release-check.json"),
        ]
        if content_inventory_required:
            release_args.extend(["--content-inventory-validation", str(run_dir / "content-inventory-validation.json"), "--require-content-inventory"])
        if chart_manifest_enabled:
            release_args.extend(["--chart-manifest-validation", str(run_dir / "chart-manifest-validation.json")])
            if chart_manifest_required:
                release_args.append("--require-chart-manifest")
        if asset_hashes_enabled:
            release_args.extend(["--asset-hash-validation", str(run_dir / "asset-hash-validation.json")])
            if args.require_asset_hashes:
                release_args.append("--require-asset-hashes")
        if any(task.name == "multipage-layout-guard" for task in executor.tasks):
            release_args.extend(["--multipage-layout-validation", str(run_dir / "multipage-layout-guard.json")])
            if args.require_multipage_layout:
                release_args.append("--require-multipage-layout")
        if args.preview_dir:
            release_args.extend(["--preview-consistency-validation", str(run_dir / "preview-consistency-validation.json")])
            if args.require_preview_consistency or args.release:
                release_args.append("--require-preview-consistency")
        if args.issue_log:
            release_args.extend(["--issue-log", str(Path(args.issue_log).resolve())])
        if args.expected_ratio is not None:
            release_args.extend(["--expected-ratio", str(args.expected_ratio)])
        if args.reference or args.reference_dir:
            release_args.extend(["--visual-comparison", str(run_dir / "visual-comparison.json")])
            release_args.extend(["--source-image-validation", str(run_dir / "source-image-validation.json"), "--require-source-image-validation", "--reference-audit", str(run_dir / "reference-audit.json"), "--require-reference-audit"])
        if args.ocr_lang or args.require_ocr:
            release_args.extend(["--ocr-report", str(run_dir / "ocr-text-check.json")])
        if args.require_text_style_map:
            release_args.extend(["--text-style-map-validation", str(run_dir / "text-style-map-validation.json"), "--require-text-style-map"])
        if gradient_required:
            release_args.extend(["--gradient-visual-validation", str(run_dir / "gradient-visual-validation.json"), "--require-gradient-visual"])
        if icon_required:
            release_args.extend(["--icon-assets-validation", str(run_dir / "icon-assets-validation.json"), "--require-icon-assets"])
        if imagegen_required:
            release_args.extend(["--imagegen-assets-validation", str(run_dir / "imagegen-assets-validation.json"), "--require-imagegen-assets"])
        if panel_gate_required:
            release_args.extend(["--panel-assets-validation", str(run_dir / "panel-assets-validation.json"), "--require-panel-assets"])
        steps.append(run_step(run_dir, "release-check", release_args))
    release_report = load_report(run_dir / "release-check.json")
    preflight_report = load_report(preflight_bundle_path)
    signoff_report = load_report(run_dir / "signoff-validation.json") if args.release else None
    quality_evidence, quality_degradations = collect_quality_evidence(preflight_bundle_path, "report_bundle_preflight")
    result = build_pipeline_result(steps, quality_evidence, quality_degradations, release_report, preflight_report, signoff_report)
    review_path = run_dir / "review.html"
    result["review_html"] = str(review_path)
    # validate_report_bundle.py requires a release candidate that claims
    # release eligibility to already declare its final bundle as sealed.  Set
    # the candidate seal before the first final validation; if validation
    # fails below, the result is downgraded and re-sealed as non-release.
    result["finalization"] = {
        "report_bundle": {
            "path": str(final_bundle_path),
            "status": "passed" if result.get("release_eligible") else "pending",
        }
    }
    atomic_write_json(run_dir / "pipeline-result.json", result)
    try:
        write_review(result, review_path)
    except Exception as exc:
        result["review_html"] = None
        result["quality_degradations"].append({"code": "review_html_generation_failed", "message": f"{type(exc).__name__}: {exc}", "requires_human_review": True})
        atomic_write_json(run_dir / "pipeline-result.json", result)

    def run_final_bundle() -> tuple[dict, dict | None]:
        final_bundle_args = [
            str(SCRIPT_DIR / "validate_report_bundle.py"),
            str(run_dir / "pipeline-result.json"),
            "--report-index", str(run_dir / "report-index.json"),
            "--project-report", str(run_dir / "project-report.json"),
            "--deck", str(deck),
            "--review-html", str(review_path),
            "--report", str(final_bundle_path),
        ]
        if args.release:
            final_bundle_args.append("--require-full")
        final_step = run_step(run_dir, "report-bundle-validation", final_bundle_args)
        return final_step, load_report(final_bundle_path)

    final_bundle_step, final_bundle_report = run_final_bundle()
    final_bundle_passed = bool(final_bundle_step.get("ok") and final_bundle_report and final_bundle_report.get("valid") is True)
    if final_bundle_passed:
        result["finalization"]["report_bundle"]["status"] = "passed"
    else:
        result["finalization"]["report_bundle"]["status"] = "failed"
        result["release_eligible"] = False
        result["release_status"] = "blocked-final-report-bundle"
        result["next_state"] = "validated" if result.get("technical_valid") else "revision-required"
    atomic_write_json(run_dir / "pipeline-result.json", result)
    if result.get("review_html"):
        try:
            write_review(result, review_path)
        except Exception as exc:
            result["review_html"] = None
            result["quality_degradations"].append({"code": "review_html_generation_failed", "message": f"{type(exc).__name__}: {exc}", "requires_human_review": True})
            atomic_write_json(run_dir / "pipeline-result.json", result)

    # The final bundle is checked again after the final result and review page
    # have been sealed. This keeps the bundle's source hashes authoritative.
    final_bundle_step, final_bundle_report = run_final_bundle()
    final_bundle_passed = bool(final_bundle_step.get("ok") and final_bundle_report and final_bundle_report.get("valid") is True)
    if not final_bundle_passed and result["finalization"]["report_bundle"]["status"] != "failed":
        result["finalization"]["report_bundle"]["status"] = "failed"
        result["release_eligible"] = False
        result["release_status"] = "blocked-final-report-bundle"
        result["next_state"] = "validated" if result.get("technical_valid") else "revision-required"
        atomic_write_json(run_dir / "pipeline-result.json", result)
        if result.get("review_html"):
            try:
                write_review(result, review_path)
            except Exception:
                result["review_html"] = None
                atomic_write_json(run_dir / "pipeline-result.json", result)
        final_bundle_step, final_bundle_report = run_final_bundle()
        final_bundle_passed = bool(final_bundle_step.get("ok") and final_bundle_report and final_bundle_report.get("valid") is True)
    print(json.dumps(result, ensure_ascii=False))
    release_blocked = args.release and not result["release_eligible"]
    return 0 if result["technical_valid"] and final_bundle_passed and not release_blocked else 2


if __name__ == "__main__":
    raise SystemExit(main())
