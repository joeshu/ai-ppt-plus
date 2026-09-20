#!/usr/bin/env python3
"""Plan a smallest-responsible-object repair with protected neighbors.

This planner is intentionally independent of any authoring backend.  It turns
coordinate/visual mismatch evidence into an auditable patch plan, captures
local before/after crops when render directories are available and makes
accept/reject/rollback an explicit batch decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/protected-repair-plan/v1"

EDITABLE_BY_TYPE = {
    "imagegen_asset": ["slot_bbox", "translation_px", "scale_ratio", "crop", "z_order"],
    "native_text": ["bbox", "margins", "font_size", "line_spacing", "baseline_offset", "alignment"],
    "native_shape": ["bbox", "geometry_adjustments", "fill", "stroke", "z_order"],
    "native_table": ["bbox", "column_widths", "row_heights", "cell_margins", "z_order"],
    "native_chart": ["bbox", "plot_area", "axis_bounds", "label_offsets", "z_order"],
    "connector": ["anchors", "route", "stroke", "z_order"],
    "freeform": ["bbox", "geometry_points", "geometry_adjustments", "z_order"],
}
PROTECTED_PARAMETERS = ["bbox", "translation_px", "scale_ratio", "anchors", "z_order", "crop", "geometry"]


def _load(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "object")).strip("._") or "object"


def _rows(source: Any) -> list[dict]:
    if isinstance(source, list):
        return [row for row in source if isinstance(row, dict)]
    if not isinstance(source, dict):
        raise ValueError("repair source must be an object or list")
    for key in ("records", "mismatches", "actions", "regions"):
        value = source.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def _object_index(authoring_plan: dict) -> dict[str, dict]:
    objects = authoring_plan.get("objects")
    if not isinstance(objects, list):
        raise ValueError("authoring plan must contain objects[]")
    index: dict[str, dict] = {}
    for item in objects:
        if not isinstance(item, dict):
            continue
        object_id = item.get("object_id")
        if isinstance(object_id, str) and object_id:
            index[object_id] = item
    return index


def _bbox_norm(obj: dict) -> list[float] | None:
    value = obj.get("bbox")
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _render_path(directory: Path | None, page: int) -> Path | None:
    if directory is None:
        return None
    for name in (f"slide-{page}.png", f"page-{page}.png", f"slide_{page:02d}.png"):
        path = directory / name
        if path.is_file():
            return path.resolve()
    return None


def _crop(path: Path, bbox: list[float], output: Path, margin: int) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for repair evidence crops") from exc
    with Image.open(path) as image:
        image.load()
        x, y, w, h = bbox
        crop_box = (
            max(0, int(round(x * image.width - margin))),
            max(0, int(round(y * image.height - margin))),
            min(image.width, int(round((x + w) * image.width + margin))),
            min(image.height, int(round((y + h) * image.height + margin))),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            raise ValueError("object bbox produces an empty crop")
        output.parent.mkdir(parents=True, exist_ok=True)
        image.crop(crop_box).save(output)
    return {"path": str(output.resolve()), "sha256": _sha256(output), "bbox_px": list(crop_box)}


def _full_page(path: Path, output: Path) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, output)
    return {"path": str(output.resolve()), "sha256": _sha256(output)}


def _capture_evidence(
    *,
    action_id: str,
    page: int,
    owner: dict,
    protected: list[dict],
    before_dir: Path | None,
    after_dir: Path | None,
    evidence_dir: Path | None,
    margin: int,
) -> dict:
    evidence: dict[str, Any] = {"owner": {}, "protected_neighbors": {}, "full_page": {}}
    bbox = _bbox_norm(owner)
    if bbox is None:
        return evidence
    for label, render_dir in (("before", before_dir), ("after", after_dir)):
        page_path = _render_path(render_dir, page)
        if page_path is None:
            continue
        if evidence_dir is None:
            evidence["full_page"][label] = {"path": str(page_path), "sha256": _sha256(page_path)}
            evidence["owner"][label] = {"path": str(page_path), "sha256": _sha256(page_path), "bbox_norm": bbox}
            continue
        page_root = evidence_dir / label / f"slide-{page}"
        evidence["full_page"][label] = _full_page(page_path, page_root / "full-page.png")
        evidence["owner"][label] = _crop(page_path, bbox, page_root / f"owner-{_safe_id(action_id)}.png", margin)
        for neighbor in protected:
            neighbor_id = str(neighbor.get("object_id"))
            neighbor_bbox = _bbox_norm(neighbor)
            if neighbor_bbox is None:
                continue
            evidence["protected_neighbors"].setdefault(neighbor_id, {})[label] = _crop(
                page_path, neighbor_bbox, page_root / f"protected-{_safe_id(neighbor_id)}.png", margin
            )
    return evidence


def _mean_pixel_delta(before: Path, after: Path) -> float:
    try:
        import numpy as np
        from PIL import Image, ImageChops
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow and numpy are required for protected crop comparison") from exc
    with Image.open(before) as before_image, Image.open(after) as after_image:
        left = before_image.convert("RGB")
        right = after_image.convert("RGB").resize(left.size)
        diff = ImageChops.difference(left, right)
        values = np.asarray(diff, dtype=float)
    return float(values.mean() / 255.0)


def _responsible_parameters(obj: dict, row: dict) -> list[str]:
    declared = obj.get("editable_parameters")
    if isinstance(declared, list) and all(isinstance(item, str) for item in declared):
        allowed = list(dict.fromkeys(declared))
    else:
        allowed = list(EDITABLE_BY_TYPE.get(obj.get("implementation_type"), ["bbox", "anchors", "z_order"]))
    repair = row.get("repair") if isinstance(row.get("repair"), dict) else {}
    selected: list[str] = []
    if "translate_px" in repair and "translation_px" in allowed:
        selected.append("translation_px")
    if "scale_ratio" in repair and "scale_ratio" in allowed:
        selected.append("scale_ratio")
    if row.get("visible_bbox_delta_px") is not None and "slot_bbox" in allowed:
        selected.append("slot_bbox")
    if not selected:
        selected = [allowed[0]] if allowed else []
    return list(dict.fromkeys(selected))


def _parameter_delta(row: dict) -> dict:
    repair = row.get("repair") if isinstance(row.get("repair"), dict) else {}
    delta: dict[str, Any] = {}
    if "translate_px" in repair:
        delta["translation_px"] = repair["translate_px"]
    if "scale_ratio" in repair:
        delta["scale_ratio"] = repair["scale_ratio"]
    if row.get("visible_bbox_delta_px") is not None:
        delta["visible_bbox_delta_px"] = row.get("visible_bbox_delta_px")
    if isinstance(row.get("proposed_patch"), dict):
        for key, value in row["proposed_patch"].items():
            if key not in {"neighbor", "protected_neighbors", "regenerate_asset"}:
                delta[key] = value
    return delta


def _source_evidence(row: dict) -> dict:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    if not evidence and isinstance(row.get("render_evidence"), dict):
        evidence = {"after": {"owner": row["render_evidence"]}}
    if not evidence and isinstance(row.get("crop_evidence"), (dict, str)):
        evidence = {"after": {"owner": row["crop_evidence"]}}
    return evidence


def build_plan(
    authoring_plan: dict,
    repair_source: Any,
    *,
    decision: str = "pending",
    decision_reason: str | None = None,
    previous_plan: Path | None = None,
    before_render_dir: Path | None = None,
    after_render_dir: Path | None = None,
    evidence_dir: Path | None = None,
    crop_margin_px: int = 12,
    protected_delta_tolerance: float = 0.02,
    human_override: bool = False,
) -> dict:
    issues: list[dict] = []
    if decision not in {"pending", "accept", "reject", "rollback"}:
        issues.append({"code": "repair_decision_invalid", "observed": decision})
    if crop_margin_px < 0 or protected_delta_tolerance < 0:
        issues.append({"code": "repair_evidence_parameter_invalid"})
    try:
        objects = _object_index(authoring_plan)
    except Exception as exc:
        objects = {}
        issues.append({"code": "authoring_plan_invalid", "detail": str(exc)})
    rows = _rows(repair_source)
    actions: list[dict] = []
    for index, row in enumerate(rows, 1):
        # A B5 report is a complete coordinate inventory, not a mismatch
        # list.  Keep aligned records out of B6 so the protected-repair
        # planner only creates actions for a real repair candidate.
        if row.get("repair_required") is False and not row.get("issues"):
            continue
        object_id = row.get("object_id")
        if not object_id and isinstance(row.get("region_id"), str):
            object_id = row["region_id"].split(":")[-1]
        object_id = str(object_id or "")
        owner = objects.get(object_id)
        if owner is None:
            issues.append({"code": "repair_owner_unknown", "object_id": object_id, "index": index})
            continue
        protected_ids: list[str] = []
        for value in [*(owner.get("protected_neighbors") or []), *((row.get("protected_neighbors") or []) if isinstance(row.get("protected_neighbors"), list) else [])]:
            if isinstance(value, str) and value != object_id and value not in protected_ids:
                protected_ids.append(value)
        protected_objects = []
        for neighbor_id in protected_ids:
            neighbor = objects.get(neighbor_id)
            if neighbor is None:
                issues.append({"code": "repair_protected_neighbor_unknown", "object_id": object_id, "neighbor": neighbor_id})
                continue
            protected_objects.append(neighbor)
        classification = str((row.get("repair") or {}).get("classification") or row.get("classification") or "visual_mismatch")
        regenerate_asset = bool((row.get("repair") or {}).get("regenerate_asset") is True)
        if classification in {"placement_only", "clipping_or_slot"}:
            regenerate_asset = False
        action_id = f"repair-{int(owner.get('page') or row.get('page') or 1):02d}-{_safe_id(object_id)}"
        captured = _capture_evidence(
            action_id=action_id,
            page=int(owner.get("page") or row.get("page") or 1),
            owner=owner,
            protected=protected_objects,
            before_dir=before_render_dir,
            after_dir=after_render_dir,
            evidence_dir=evidence_dir,
            margin=crop_margin_px,
        )
        supplied = _source_evidence(row)
        if supplied:
            captured = {**supplied, **captured}
        actions.append({
            "action_id": action_id,
            "owner": {
                "object_id": object_id,
                "page": owner.get("page") or row.get("page"),
                "semantic_role": owner.get("semantic_role"),
                "implementation_type": owner.get("implementation_type"),
            },
            "mismatch": {
                "classification": classification,
                "metrics": row.get("metrics") or {},
                "issues": row.get("issues") or [],
                "centroid_delta_px": row.get("centroid_delta_px"),
                "visible_bbox_delta_px": row.get("visible_bbox_delta_px"),
            },
            "responsible_parameters": _responsible_parameters(owner, row),
            "parameter_delta": _parameter_delta(row),
            "regenerate_asset": regenerate_asset,
            "protected_neighbors": protected_ids,
            "forbidden_compensation": [{"object_id": value, "parameters": PROTECTED_PARAMETERS} for value in protected_ids],
            "evidence": captured,
            "decision": decision,
        })

    if decision == "rollback":
        if previous_plan is None or not previous_plan.is_file():
            issues.append({"code": "rollback_previous_plan_missing"})
        else:
            try:
                previous = _load(previous_plan)
                if not isinstance(previous, dict) or previous.get("schema") != SCHEMA:
                    issues.append({"code": "rollback_previous_plan_invalid"})
            except Exception as exc:
                issues.append({"code": "rollback_previous_plan_unreadable", "detail": str(exc)})

    protected_regressions: list[dict] = []
    evidence_missing: list[dict] = []
    if decision == "accept":
        for action in actions:
            evidence = action.get("evidence") or {}
            owner_evidence = evidence.get("owner") if isinstance(evidence.get("owner"), dict) else {}
            full_page = evidence.get("full_page") if isinstance(evidence.get("full_page"), dict) else {}
            if not (isinstance(owner_evidence.get("before"), dict) and isinstance(owner_evidence.get("after"), dict)):
                evidence_missing.append({"action_id": action["action_id"], "scope": "owner"})
            if not (isinstance(full_page.get("before"), dict) and isinstance(full_page.get("after"), dict)):
                evidence_missing.append({"action_id": action["action_id"], "scope": "full_page"})
            neighbors = evidence.get("protected_neighbors") if isinstance(evidence.get("protected_neighbors"), dict) else {}
            for neighbor_id in action.get("protected_neighbors", []):
                pair = neighbors.get(neighbor_id) if isinstance(neighbors.get(neighbor_id), dict) else {}
                before = pair.get("before", {}).get("path") if isinstance(pair.get("before"), dict) else None
                after = pair.get("after", {}).get("path") if isinstance(pair.get("after"), dict) else None
                if not before or not after:
                    evidence_missing.append({"action_id": action["action_id"], "scope": "protected_neighbor", "object_id": neighbor_id})
                    continue
                try:
                    delta = _mean_pixel_delta(Path(before), Path(after))
                except Exception as exc:
                    evidence_missing.append({"action_id": action["action_id"], "scope": "protected_neighbor", "object_id": neighbor_id, "detail": str(exc)})
                    continue
                pair["mean_pixel_delta"] = round(delta, 6)
                pair["material_regression"] = delta > protected_delta_tolerance
                if pair["material_regression"]:
                    protected_regressions.append({"action_id": action["action_id"], "object_id": neighbor_id, "mean_pixel_delta": round(delta, 6), "tolerance": protected_delta_tolerance})
    if evidence_missing:
        issues.append({"code": "repair_evidence_missing", "items": evidence_missing})
    if protected_regressions and not human_override:
        issues.append({"code": "protected_neighbor_regression", "items": protected_regressions, "human_override_required": True})
    status = {
        "pending": "pending-review",
        "accept": "accepted" if not issues else "blocked",
        "reject": "rejected",
        "rollback": "rollback-requested" if not issues else "blocked",
    }.get(decision, "blocked")
    if not actions and not issues:
        status = "no-repair-required"
    return {
        "schema": SCHEMA,
        "valid": not issues,
        "status": status,
        "decision": decision,
        "decision_reason": decision_reason,
        "action_count": len(actions),
        "repair_loop_required": bool(actions and decision != "accept"),
        "owner_ids": sorted({item["owner"]["object_id"] for item in actions}),
        "protection_set": sorted({neighbor for item in actions for neighbor in item.get("protected_neighbors", [])}),
        "protected_delta_tolerance": protected_delta_tolerance,
        "human_override": human_override,
        "rollback": {"requested": decision == "rollback", "previous_plan": str(previous_plan.resolve()) if previous_plan else None},
        "evidence": {"captured": bool(evidence_dir), "protected_regressions": protected_regressions, "missing": evidence_missing},
        "actions": actions,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoring-plan", type=Path, required=True)
    parser.add_argument("--mismatches", type=Path, required=True, help="B5 coordinate report or render-repair trace")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--decision", choices=("pending", "accept", "reject", "rollback"), default="pending")
    parser.add_argument("--decision-reason")
    parser.add_argument("--previous-plan", type=Path)
    parser.add_argument("--before-render-dir", type=Path)
    parser.add_argument("--after-render-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--crop-margin-px", type=int, default=12)
    parser.add_argument("--protected-delta-tolerance", type=float, default=0.02)
    parser.add_argument("--human-override", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.evidence_dir:
        args.evidence_dir.resolve().mkdir(parents=True, exist_ok=True)
    try:
        authoring_plan = _load(args.authoring_plan.resolve())
        repair_source = _load(args.mismatches.resolve())
        report = build_plan(
            authoring_plan,
            repair_source,
            decision=args.decision,
            decision_reason=args.decision_reason,
            previous_plan=args.previous_plan.resolve() if args.previous_plan else None,
            before_render_dir=args.before_render_dir.resolve() if args.before_render_dir else None,
            after_render_dir=args.after_render_dir.resolve() if args.after_render_dir else None,
            evidence_dir=args.evidence_dir.resolve() if args.evidence_dir else None,
            crop_margin_px=args.crop_margin_px,
            protected_delta_tolerance=args.protected_delta_tolerance,
            human_override=args.human_override,
        )
    except Exception as exc:
        report = {"schema": SCHEMA, "valid": False, "status": "blocked", "decision": args.decision, "action_count": 0, "actions": [], "issues": [{"code": "repair_input_unreadable", "detail": f"{type(exc).__name__}: {exc}"}]}
    args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.report.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or args.report:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
