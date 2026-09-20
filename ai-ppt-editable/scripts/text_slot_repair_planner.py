#!/usr/bin/env python3
"""Plan smallest-scope text-slot repairs from TextFit evidence.

The planner converts measured box deficits/topology defects into an ordered,
auditable repair plan. It never compensates by moving unrelated objects and
keeps font shrinking as the final fallback.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "ai-ppt-plus/text-slot-repair-plan/v1"
TEXT_FIT_REPORT_SCHEMAS = {"ai-ppt-plus/text-fit-deck/v1", "ai-ppt-plus/text-fit-deck/v2", "ai-ppt-plus/text-fit-deck/v3"}
REPAIR_ORDER = ["slot_bbox", "text_margins", "reserved_icon_divider_space", "component_layout", "reference_line_topology", "line_spacing", "font_size_last"]


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pair(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return [0.0, 0.0]
    return [max(0.0, _num(value[0])), max(0.0, _num(value[1]))]


def _bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    out = [_num(item, -1.0) for item in value]
    if out[0] < 0 or out[1] < 0 or out[2] <= 0 or out[3] <= 0:
        return None
    return out


def _index_objects(plan: dict) -> dict[str, dict]:
    rows = plan.get("objects")
    if not isinstance(rows, list):
        raise ValueError("authoring plan must contain objects[]")
    return {str(row["object_id"]): row for row in rows if isinstance(row, dict) and isinstance(row.get("object_id"), str) and row.get("object_id")}


def _owner_candidates(slot_id: str) -> list[str]:
    candidates = [slot_id]
    parts = slot_id.split(":")
    if parts and parts[0] in {"text", "shape"} and len(parts) >= 2:
        candidates.append(":".join(parts[1:]))
    elif parts and parts[0] in {"table", "chart"} and len(parts) >= 2:
        candidates.append(parts[1])
    return list(dict.fromkeys(candidates))


def _resolve_owner(slot: dict, objects: dict[str, dict]) -> tuple[str | None, dict | None]:
    explicit = slot.get("authoring_object_id") or slot.get("owner_object_id")
    if isinstance(explicit, str) and explicit in objects:
        return explicit, objects[explicit]
    slot_id = str(slot.get("object_id") or "")
    for candidate in _owner_candidates(slot_id):
        if candidate in objects:
            return candidate, objects[candidate]
    return None, None


def _overlap(a: list[float], b: list[float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by)


def _within_canvas(box: list[float]) -> bool:
    x, y, w, h = box
    return x >= -1e-9 and y >= -1e-9 and w > 0 and h > 0 and x + w <= 1.0000001 and y + h <= 1.0000001


def _bbox_candidates(box: list[float], dw: float, dh: float) -> list[dict]:
    x, y, w, h = box
    specs = [("right_down", x, y), ("symmetric", x - dw / 2.0, y - dh / 2.0), ("left_down", x - dw, y), ("right_up", x, y - dh), ("left_up", x - dw, y - dh)]
    out = []
    for mode, nx, ny in specs:
        candidate = [nx, ny, w + dw, h + dh]
        if _within_canvas(candidate):
            out.append({"mode": mode, "bbox": [round(v, 8) for v in candidate]})
    return out


def _protected(owner: dict, objects: dict[str, dict]) -> tuple[list[str], list[dict]]:
    ids = [value for value in (owner.get("protected_neighbors") or []) if isinstance(value, str)]
    return ids, [objects[value] for value in ids if value in objects]


def _safe_bbox_patch(owner: dict, protected_rows: list[dict], deficit_px: list[float], source_w: float, source_h: float) -> dict | None:
    box = _bbox(owner.get("bbox"))
    if box is None or source_w <= 0 or source_h <= 0:
        return None
    dw, dh = deficit_px[0] / source_w, deficit_px[1] / source_h
    if dw <= 0 and dh <= 0:
        return None
    blockers = [_bbox(row.get("bbox")) for row in protected_rows]
    blockers = [row for row in blockers if row is not None]
    for candidate in _bbox_candidates(box, dw, dh):
        if not any(_overlap(candidate["bbox"], blocker) for blocker in blockers):
            return {"bbox": candidate["bbox"], "growth_norm": [round(dw, 8), round(dh, 8)], "growth_px": [round(deficit_px[0], 3), round(deficit_px[1], 3)], "anchor_mode": candidate["mode"]}
    return None


def _margin_candidate(contract: dict, deficit_px: list[float]) -> dict | None:
    margins, minimum = contract.get("margins_px"), contract.get("min_margins_px")
    if not (isinstance(margins, (list, tuple)) and len(margins) == 4 and isinstance(minimum, (list, tuple)) and len(minimum) == 4):
        return None
    current, floor = [max(0.0, _num(v)) for v in margins], [max(0.0, _num(v)) for v in minimum]
    available_w = max(0.0, current[0] - floor[0]) + max(0.0, current[2] - floor[2])
    available_h = max(0.0, current[1] - floor[1]) + max(0.0, current[3] - floor[3])
    if deficit_px[0] > available_w + 1e-6 or deficit_px[1] > available_h + 1e-6:
        return None
    need_w, need_h, next_margins = deficit_px[0], deficit_px[1], list(current)
    for index in (0, 2):
        take = min(max(0.0, next_margins[index] - floor[index]), need_w)
        next_margins[index] -= take
        need_w -= take
    for index in (1, 3):
        take = min(max(0.0, next_margins[index] - floor[index]), need_h)
        next_margins[index] -= take
        need_h -= take
    return {"margins_px": [round(v, 3) for v in next_margins], "from_margins_px": current}


def _contract_candidate(contract: dict, key: str, output_key: str) -> dict | None:
    value = contract.get(key)
    if isinstance(value, dict) and value:
        return {output_key: value}
    if isinstance(value, list) and value:
        return {output_key: value}
    return None


def _line_spacing_candidate(contract: dict) -> dict | None:
    current, minimum = contract.get("line_spacing"), contract.get("min_line_spacing")
    if current is None or minimum is None:
        return None
    current_n, minimum_n = _num(current, -1), _num(minimum, -1)
    if current_n <= 0 or minimum_n <= 0 or minimum_n >= current_n:
        return None
    return {"line_spacing": minimum_n, "from_line_spacing": current_n}


def _font_candidate(slot: dict, contract: dict) -> dict | None:
    target, recommended, minimum = _num(slot.get("target_pt"), 0), _num(slot.get("recommended_pt"), 0), _num(contract.get("min_font_size_pt"), 0)
    if target <= 0 or recommended <= 0 or recommended >= target or (minimum > 0 and recommended < minimum):
        return None
    return {"font_size_pt": round(recommended, 2), "from_font_size_pt": round(target, 2), "last_resort": True}


def _responsible_parameter(step: str) -> str:
    return {"slot_bbox": "bbox", "text_margins": "margins", "reserved_icon_divider_space": "bbox", "component_layout": "bbox", "reference_line_topology": "bbox", "line_spacing": "line_spacing", "font_size_last": "font_size"}.get(step, "bbox")


def _action(slot: dict, owner_id: str, owner: dict, objects: dict[str, dict], source_w: float, source_h: float) -> dict:
    deficit = _pair(slot.get("box_deficit_px"))
    geometry_defect = bool(slot.get("geometry_defect") or not slot.get("geometry_fits", True))
    topology_defect = bool(slot.get("topology_defect") or not slot.get("line_topology_preserved", True))
    contract = owner.get("typography_contract") if isinstance(owner.get("typography_contract"), dict) else {}
    protected_ids, protected_rows = _protected(owner, objects)
    candidates: list[dict] = []
    bbox_patch = _safe_bbox_patch(owner, protected_rows, deficit, source_w, source_h) if geometry_defect else None
    candidates.append({"step": "slot_bbox", "available": bbox_patch is not None, "patch": bbox_patch})
    margin_patch = _margin_candidate(contract, deficit) if geometry_defect else None
    candidates.append({"step": "text_margins", "available": margin_patch is not None, "patch": margin_patch})
    reserve_patch = _contract_candidate(contract, "reserved_slot_repair", "reserved_slot_repair") if geometry_defect else None
    candidates.append({"step": "reserved_icon_divider_space", "available": reserve_patch is not None, "patch": reserve_patch})
    component_patch = _contract_candidate(contract, "component_layout_repair", "component_layout_repair") if geometry_defect else None
    candidates.append({"step": "component_layout", "available": component_patch is not None, "patch": component_patch})
    topology_patch = None
    if topology_defect:
        topology_patch = {"target_lines": int(slot.get("target_lines") or 0), "observed_lines": int(slot.get("line_count") or 0), "line_count_delta": int(slot.get("line_count") or 0) - int(slot.get("target_lines") or 0), "mode": "preserve_text_content_reflow_only"}
    candidates.append({"step": "reference_line_topology", "available": topology_patch is not None, "patch": topology_patch})
    spacing_patch = _line_spacing_candidate(contract) if geometry_defect else None
    candidates.append({"step": "line_spacing", "available": spacing_patch is not None, "patch": spacing_patch})
    font_patch = _font_candidate(slot, contract) if geometry_defect or topology_defect else None
    candidates.append({"step": "font_size_last", "available": font_patch is not None, "patch": font_patch})
    selected = next((row for row in candidates if row["available"]), None)
    proposed_patch = dict(selected["patch"]) if selected and isinstance(selected.get("patch"), dict) else {}
    return {
        "object_id": owner_id, "text_slot_id": slot.get("object_id"), "page": int(owner.get("page") or slot.get("slide") or 1), "producer_kind": slot.get("producer_kind"), "classification": "text_slot_layout", "repair_required": True,
        "defect": {"geometry_defect": geometry_defect, "topology_defect": topology_defect, "box_deficit_px": [round(v, 3) for v in deficit], "target_lines": slot.get("target_lines"), "observed_lines": slot.get("line_count"), "reference_scale": slot.get("reference_scale")},
        "repair_order": REPAIR_ORDER, "candidates": candidates, "selected_step": selected["step"] if selected else "manual_layout_review", "responsible_parameters": [_responsible_parameter(selected["step"])] if selected else [], "proposed_patch": proposed_patch,
        "protected_neighbors": protected_ids, "forbidden_compensation": protected_ids, "font_shrink_last": True, "requires_render_replay": True, "repair": {"classification": "text_slot_layout", "regenerate_asset": False},
    }


def build_plan(text_fit_report: dict, authoring_plan: dict) -> dict:
    issues: list[dict] = []
    if text_fit_report.get("schema") not in TEXT_FIT_REPORT_SCHEMAS:
        issues.append({"code": "text_fit_schema_mismatch", "observed": text_fit_report.get("schema")})
    if text_fit_report.get("valid") is False:
        issues.append({"code": "text_fit_report_invalid"})
    if authoring_plan.get("schema") != "ai-ppt-plus/authoring-plan/v1":
        issues.append({"code": "authoring_plan_schema_mismatch", "observed": authoring_plan.get("schema")})
    objects = _index_objects(authoring_plan)
    source = authoring_plan.get("source") if isinstance(authoring_plan.get("source"), dict) else {}
    source_w, source_h = _num(source.get("width_px"), 0), _num(source.get("height_px"), 0)
    if source_w <= 0 or source_h <= 0:
        issues.append({"code": "authoring_source_extent_invalid"})
    slots = text_fit_report.get("slots")
    if not isinstance(slots, list):
        raise ValueError("text-fit report must contain slots[]")
    actions = []
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            continue
        geometry_defect = bool(slot.get("geometry_defect") or not slot.get("geometry_fits", True))
        topology_defect = bool(slot.get("topology_defect") or not slot.get("line_topology_preserved", True))
        if not geometry_defect and not topology_defect:
            continue
        owner_id, owner = _resolve_owner(slot, objects)
        if owner is None or owner_id is None:
            issues.append({"code": "text_slot_owner_unknown", "slot": slot.get("object_id"), "index": index})
            continue
        actions.append(_action(slot, owner_id, owner, objects, source_w, source_h))
    unresolved = [row for row in actions if row["selected_step"] == "manual_layout_review"]
    return {"schema": SCHEMA, "valid": not issues, "source": {"text_fit_schema": text_fit_report.get("schema"), "authoring_plan_schema": authoring_plan.get("schema")}, "policy": {"repair_order": REPAIR_ORDER, "font_shrink_last": True, "move_unrelated_objects": False, "require_render_replay": True}, "summary": {"action_count": len(actions), "unresolved_count": len(unresolved), "bbox_first_count": sum(row["selected_step"] == "slot_bbox" for row in actions), "font_last_count": sum(row["selected_step"] == "font_size_last" for row in actions)}, "actions": actions, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-fit-report", required=True)
    parser.add_argument("--authoring-plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_plan(_load(Path(args.text_fit_report)), _load(Path(args.authoring_plan)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "actions": len(report["actions"]), "output": str(output)}, ensure_ascii=False))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
