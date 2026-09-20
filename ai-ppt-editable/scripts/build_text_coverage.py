#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "ai-ppt-plus/text-coverage/v1"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value

def owner_from_slot(slot_id: str, kind: str) -> str:
    parts = slot_id.split(":")
    if kind in {"text", "shape_text"}:
        return parts[-1]
    if kind == "table_cell" and len(parts) >= 3:
        return parts[1]
    if kind.startswith("chart_") and len(parts) >= 2:
        return parts[1]
    return parts[-1]

def producer(kind: str, slot: dict | None = None) -> str:
    slot = slot or {}
    explicit = slot.get("producer_kind") or slot.get("text_producer_kind")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if isinstance(slot.get("number_unit"), dict):
        return "number_unit"
    if kind == "text":
        return "rich_text_runs" if int(slot.get("run_count") or 0) > 0 else "text_box"
    return {
        "shape_text": "badge_label",
        "table_cell": "table_cell",
        "chart_title": "chart_label",
        "chart_legend": "chart_label",
        "chart_category_label": "chart_label",
        "chart_data_label": "chart_label",
    }.get(kind, "other")

def binding(kind: str, slot_id: str, owner_id: str) -> dict:
    if kind == "table_cell":
        return {"kind": "table_cell", "binding_id": slot_id}
    if kind.startswith("chart_"):
        return {"kind": "chart_text", "binding_id": slot_id}
    return {"kind": "shape", "binding_id": owner_id}

def _slot_trace(slot: dict, slot_id: str, text: str) -> dict:
    raw_ids = slot.get("run_ids")
    run_ids = [str(value) for value in raw_ids] if isinstance(raw_ids, list) else []
    raw_trace = slot.get("run_trace")
    run_trace = [value for value in raw_trace if isinstance(value, dict)] if isinstance(raw_trace, list) else []
    run_count = int(slot.get("run_count") if slot.get("run_count") is not None else len(run_ids))
    if run_count < 0:
        run_count = 0
    if not run_ids and run_trace:
        run_ids = [str(value.get("run_id")) for value in run_trace if value.get("run_id") is not None]
    content_matches = slot.get("content_matches_runs")
    if content_matches is not None:
        content_matches = bool(content_matches)
    scope = slot.get("measurement_scope")
    if not isinstance(scope, dict):
        scope = {"kind": "whole_phrase", "scope_id": slot_id}
    return {
        "text_spec_id": str(slot.get("text_spec_id") or slot_id),
        "content_sha256": str(slot.get("content_sha256") or sha256_text(text)),
        "content_matches_runs": content_matches,
        "run_count": run_count,
        "run_ids": run_ids,
        "run_trace": run_trace,
        "run_style_sha256": slot.get("run_style_sha256"),
        "base_style_sha256": slot.get("base_style_sha256"),
        "measurement_scope": scope,
        "number_unit": slot.get("number_unit") if isinstance(slot.get("number_unit"), dict) else None,
    }


def build(plan: dict, fit: dict, *, plan_sha: str) -> dict:
    objects = [o for o in (plan.get("objects") or []) if isinstance(o, dict)]
    by_id = {o.get("object_id"): o for o in objects if isinstance(o.get("object_id"), str)}
    entries = []
    for slot in fit.get("slots") or []:
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("object_id") or "").strip()
        kind = str(slot.get("kind") or "").strip()
        text = str(slot.get("text") or "")
        if not slot_id or not kind or not text.strip():
            continue
        owner_id = owner_from_slot(slot_id, kind)
        if owner_id not in by_id:
            continue
        trace = _slot_trace(slot, slot_id, text)
        fit_decision = "slot-preserved"
        if slot.get("geometry_defect"):
            fit_decision = "geometry-repair-required"
        elif slot.get("recommended_pt") and slot.get("target_pt") and float(slot["recommended_pt"]) < float(slot["target_pt"]):
            fit_decision = "font-adjustment-recommended"
        entries.append({
            "target_id": slot_id,
            "owner_object_id": owner_id,
            "producer_kind": producer(kind, slot),
            "expected_text": text,
            "text_spec_id": trace["text_spec_id"],
            "content_sha256": trace["content_sha256"],
            "run_count": trace["run_count"],
            "run_ids": trace["run_ids"],
            "run_trace": trace["run_trace"],
            "measurement_scope": trace["measurement_scope"],
            "number_unit": trace["number_unit"],
            "authoring_path": f"artifact_tool:{kind}",
            "text_fit_evidence_id": slot_id,
            "text_fit_evidence": {
                "measured": True,
                "fit_decision": fit_decision,
                "font_family": None,
                "font_size_pt": slot.get("target_pt"),
                "line_count": slot.get("line_count"),
                "text_spec_id": trace["text_spec_id"],
                "content_sha256": trace["content_sha256"],
                "content_matches_runs": trace["content_matches_runs"],
                "run_count": trace["run_count"],
                "run_ids": trace["run_ids"],
                "run_trace": trace["run_trace"],
                "run_style_sha256": trace["run_style_sha256"],
                "base_style_sha256": trace["base_style_sha256"],
                "measurement_scope": trace["measurement_scope"],
                "number_unit": trace["number_unit"],
            },
            "output_binding": binding(kind, slot_id, owner_id),
            "formal_text_required": True
        })
    return {
        "schema": SCHEMA,
        "source": {"authoring_plan_sha256": plan_sha, "pptx_sha256": None},
        "entries": entries
    }

def main() -> int:
    p = argparse.ArgumentParser(description="Build Text Coverage ledger from AuthoringPlan and text-fit report.")
    p.add_argument("authoring_plan", type=Path)
    p.add_argument("text_fit_report", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        plan = load(args.authoring_plan)
        fit = load(args.text_fit_report)
        if plan.get("schema") != "ai-ppt-plus/authoring-plan/v1":
            raise ValueError("invalid AuthoringPlan schema")
        if not str(fit.get("schema", "")).startswith("ai-ppt-plus/text-fit-deck/"):
            raise ValueError("invalid text-fit report schema")
        if fit.get("all_slots_measured") is not True:
            raise ValueError("text-fit report must have all_slots_measured=true")
        result = build(plan, fit, plan_sha=sha256(args.authoring_plan))
    except Exception as exc:
        print(json.dumps({"schema": SCHEMA, "valid": False, "status": "blocked", "code": "text_coverage_build_failed", "message": str(exc)}, ensure_ascii=False))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "entry_count": len(result["entries"]), "output": str(args.output)}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
