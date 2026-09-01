#!/usr/bin/env python3
"""Record, score, and gate repeatable editable-PPT distillation runs.

This controller is intentionally model-agnostic.  It does not pretend that a
technical score is human approval or model training.  It turns existing pixel,
dual-comparison, object, pipeline, and issue reports into a deterministic
candidate score, owner-classified feedback, and a safe promote/rollback
decision.  The resulting case registry is the input contract for a later
retrieval or fine-tuning pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from atomic_output import atomic_write_json


CASE_SCHEMA = "ai-ppt-plus/distillation-case-registry/v1"
SCORE_SCHEMA = "ai-ppt-plus/distillation-score/v1"
FEEDBACK_SCHEMA = "ai-ppt-plus/distillation-feedback/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PROFILES = {"visual-best", "editable-best", "hybrid"}
OWNERS = {"asset", "font", "text", "layout", "object", "provenance", "report", "pipeline", "package"}

WEIGHTS = {
    "visual-best": {"visual_layout": 0.35, "pixel_fidelity": 0.25, "editability": 0.15, "technical": 0.15, "provenance": 0.10},
    "editable-best": {"visual_layout": 0.20, "pixel_fidelity": 0.15, "editability": 0.35, "technical": 0.15, "provenance": 0.15},
    "hybrid": {"visual_layout": 0.30, "pixel_fidelity": 0.20, "editability": 0.25, "technical": 0.15, "provenance": 0.10},
}
DEFAULT_TOLERANCES = {"visual_layout": 0.03, "pixel_fidelity": 0.03, "editability": 0.01, "technical": 0.0, "provenance": 0.0}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return max(0.0, min(1.0, result))


def first_number(data: Any, keys: Iterable[str]) -> float | None:
    wanted = set(keys)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in wanted:
                found = number(value)
                if found is not None:
                    return found
        for value in data.values():
            found = first_number(value, wanted)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = first_number(value, wanted)
            if found is not None:
                return found
    return None


def first_value(data: Any, keys: Iterable[str]) -> Any:
    wanted = set(keys)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in wanted:
                return value
        for value in data.values():
            found = first_value(value, wanted)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = first_value(value, wanted)
            if found is not None:
                return found
    return None


def bool_report(data: dict[str, Any], keys: Iterable[str]) -> bool | None:
    value = first_value(data, keys)
    return value if isinstance(value, bool) else None


def report_metric(reports: list[dict[str, Any]], keys: Iterable[str]) -> float | None:
    values = []
    for report in reports:
        value = first_number(report, keys)
        if value is not None:
            values.append(value)
    return round(sum(values) / len(values), 6) if values else None


def object_editability(reports: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for report in reports:
        candidates: list[dict[str, Any]] = [report]
        nested = report.get("object_comparison")
        if isinstance(nested, dict):
            candidates.append(nested)
        for item in candidates:
            expected = first_value(item, ("expected_objects", "expected_object_count", "manifest_object_count"))
            audited = first_value(item, ("audited_objects", "audited_object_count", "observed_object_count"))
            try:
                expected_int = int(expected)
                audited_int = int(audited)
            except (TypeError, ValueError):
                continue
            if expected_int > 0:
                values.append(max(0.0, min(1.0, audited_int / expected_int)))
                break
            if item.get("valid") is True:
                values.append(1.0)
    return round(sum(values) / len(values), 6) if values else None


def technical_score(reports: list[dict[str, Any]]) -> float:
    if not reports:
        return 0.0
    seen = False
    for report in reports:
        for key in ("technical_valid", "valid"):
            value = report.get(key)
            if isinstance(value, bool):
                seen = True
                if value is False:
                    return 0.0
    return 1.0 if seen else 0.0


def provenance_score(reports: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for report in reports:
        dual = report.get("pixel_comparison")
        if isinstance(dual, dict):
            values.append(1.0 if dual.get("hash_bound") is True else 0.0)
        object_part = report.get("object_comparison")
        if isinstance(object_part, dict) and "valid" in object_part:
            values.append(1.0 if object_part.get("valid") is True else 0.0)
        if report.get("hash_bound") is True:
            values.append(1.0)
        if report.get("provenance_valid") is True:
            values.append(1.0)
    return round(sum(values) / len(values), 6) if values else 0.0


def extract_metrics(reports: list[dict[str, Any]]) -> dict[str, float]:
    explicit: dict[str, float] = {}
    for report in reports:
        values = report.get("distillation_metrics")
        if isinstance(values, dict):
            for key in ("visual_layout", "pixel_fidelity", "editability", "technical", "provenance"):
                parsed = number(values.get(key))
                if parsed is not None:
                    explicit[key] = parsed
    metrics = {
        "visual_layout": explicit["visual_layout"] if "visual_layout" in explicit else (report_metric(reports, ("mean_blurred_layout_ssim", "blurred_layout_ssim", "layout_ssim")) or 0.0),
        "pixel_fidelity": explicit["pixel_fidelity"] if "pixel_fidelity" in explicit else (report_metric(reports, ("mean_pixel_fidelity_score", "pixel_fidelity_score", "pixel_fidelity")) or 0.0),
        "editability": explicit.get("editability") if "editability" in explicit else (object_editability(reports) or 0.0),
        "technical": explicit.get("technical") if "technical" in explicit else technical_score(reports),
        "provenance": explicit.get("provenance") if "provenance" in explicit else provenance_score(reports),
    }
    return {key: round(max(0.0, min(1.0, value)), 6) for key, value in metrics.items()}


def owner_for(code: str, message: str = "") -> str:
    text = f"{code} {message}".lower()
    groups = (
        ("package", ("package", "sync", "revision", "dependency")),
        ("font", ("font", "cjk", "glyph", "typeface")),
        ("text", ("text", "ocr", "copy", "typography", "wrap", "line_break")),
        ("layout", ("layout", "bbox", "overflow", "overlap", "ratio", "position", "coordinate")),
        ("object", ("object", "editable", "shape", "panel", "manifest")),
        ("provenance", ("hash", "source", "provenance", "stale")),
        ("asset", ("asset", "icon", "image", "background", "svg")),
        ("report", ("report", "registry", "evidence", "freshness")),
        ("pipeline", ("pipeline", "render", "compare", "cache", "timeout")),
    )
    for owner, words in groups:
        if any(word in text for word in words):
            return owner
    return "pipeline"


def severity_of(item: dict[str, Any]) -> str:
    severity = item.get("severity") or item.get("level")
    if severity in {"blocker", "critical", "major", "minor", "info"}:
        return severity
    return "major" if item.get("status") in {"failed", "blocked", "open"} else "info"


def collect_feedback(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for report_index, report in enumerate(reports):
        for field in ("issues", "errors", "warnings", "failed_steps", "technical_failed_steps"):
            values = report.get(field)
            if not isinstance(values, list):
                continue
            for raw in values:
                item = raw if isinstance(raw, dict) else {"message": str(raw)}
                code = str(item.get("code") or item.get("id") or f"{field}_{len(feedback)+1}")
                message = str(item.get("message") or item.get("detail") or code)
                key = (code, message)
                if key in seen:
                    continue
                seen.add(key)
                feedback.append({
                    "feedback_id": f"fb-{len(feedback)+1:04d}",
                    "owner": owner_for(code, message),
                    "severity": severity_of(item),
                    "code": code,
                    "message": message,
                    "source_report_index": report_index,
                    "status": "open",
                    "repair_action": "classify-and-repair-owner-layer",
                })
    return feedback


def score_candidate(reports: list[dict[str, Any]], *, candidate_id: str, profile: str) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    metrics = extract_metrics(reports)
    weights = WEIGHTS[profile]
    weighted_score = round(sum(metrics[key] * weights[key] for key in weights), 6)
    feedback = collect_feedback(reports)
    blockers = [item for item in feedback if item["severity"] in {"blocker", "critical"}]
    technical_valid = metrics["technical"] >= 1.0 and not blockers
    return {
        "schema": SCORE_SCHEMA,
        "candidate_id": candidate_id,
        "profile": profile,
        "metrics": metrics,
        "weights": weights,
        "weighted_score": weighted_score,
        "technical_valid": technical_valid,
        "feedback": feedback,
        "blocker_count": len(blockers),
        "human_visual_review_required": True,
        "human_review_status": "pending",
        "training_eligible": False,
    }


def gate_candidate(candidate: dict[str, Any], baseline: dict[str, Any] | None, tolerances: dict[str, float]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    candidate_metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    baseline_metrics = baseline.get("metrics") if isinstance(baseline, dict) and isinstance(baseline.get("metrics"), dict) else {}
    if candidate.get("technical_valid") is not True:
        issues.append({"severity": "blocker", "code": "candidate_technical_gate_failed", "owner": "pipeline"})
    for key, tolerance in tolerances.items():
        current = number(candidate_metrics.get(key))
        previous = number(baseline_metrics.get(key)) if baseline_metrics else None
        if current is None:
            issues.append({"severity": "blocker", "code": f"candidate_metric_missing_{key}", "owner": "report"})
            continue
        if previous is not None and current < previous - tolerance:
            regression = {"severity": "major", "code": f"metric_regression_{key}", "owner": "layout" if "visual" in key or "pixel" in key else "object", "previous": previous, "current": current, "tolerance": tolerance}
            regressions.append(regression)
    if baseline and isinstance(baseline.get("weighted_score"), (int, float)):
        minimum = float(baseline["weighted_score"]) - 0.01
        if float(candidate.get("weighted_score", 0.0)) < minimum:
            issues.append({"severity": "major", "code": "weighted_score_regression", "owner": "pipeline", "minimum": round(minimum, 6), "current": candidate.get("weighted_score")})
    issues.extend(regressions)
    accepted = not any(item.get("severity") in {"blocker", "critical", "major"} for item in issues)
    return {
        "schema": FEEDBACK_SCHEMA,
        "candidate_id": candidate.get("candidate_id"),
        "decision": "accept-for-human-review" if accepted else "reject-and-rollback",
        "rollback_action": "promote_candidate" if accepted else "keep_previous_candidate",
        "candidate_score": candidate.get("weighted_score"),
        "baseline_score": baseline.get("weighted_score") if baseline else None,
        "issues": issues,
        "regressions": regressions,
        "human_visual_review_required": True,
        "human_review_status": "pending",
        "release_eligible": False,
    }


def artifact_ref(path: Path, *, role: str, slide: int | None = None) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    result = {"role": role, "path": str(path.resolve()), "sha256": sha256(path)}
    if slide is not None:
        result["slide"] = slide
    return result


def record_case(args: argparse.Namespace) -> dict[str, Any]:
    registry_path = Path(args.registry).resolve()
    if registry_path.is_file():
        registry = read_json(registry_path)
    else:
        registry = {"schema": CASE_SCHEMA, "version": 1, "cases": []}
    if registry.get("schema") != CASE_SCHEMA or not isinstance(registry.get("cases"), list):
        raise ValueError("registry must use ai-ppt-plus/distillation-case-registry/v1")
    sources = [artifact_ref(Path(value).resolve(), role="source", slide=None) for value in args.source]
    reports = [artifact_ref(Path(value).resolve(), role="report") for value in args.report]
    score_path = Path(args.score).resolve()
    score = read_json(score_path)
    candidate = {
        "candidate_id": args.candidate_id,
        "profile": args.profile,
        "status": args.status,
        "training_eligible": False,
        "deck": artifact_ref(Path(args.deck).resolve(), role="candidate-deck"),
        "score": artifact_ref(score_path, role="candidate-score"),
        "reports": reports,
        "score_summary": {
            "weighted_score": score.get("weighted_score"),
            "metrics": score.get("metrics", {}),
            "technical_valid": score.get("technical_valid") is True,
            "training_eligible": score.get("training_eligible") is True,
        },
    }
    if args.plan:
        candidate["proposal_plan"] = artifact_ref(Path(args.plan).resolve(), role="candidate-plan")
    case = {
        "case_id": args.case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_references": sources,
        "candidates": [candidate],
        "learning_status": "human-review-pending",
        "training_policy": "Only human-approved, hash-bound candidates may enter a training export.",
    }
    cases = [item for item in registry["cases"] if not (isinstance(item, dict) and item.get("case_id") == args.case_id)]
    cases.append(case)
    result = {"schema": CASE_SCHEMA, "version": 1, "updated_at": datetime.now(timezone.utc).isoformat(), "cases": cases}
    atomic_write_json(registry_path, result)
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    score = sub.add_parser("score", help="score one candidate from existing reports")
    score.add_argument("--candidate-id", required=True)
    score.add_argument("--profile", choices=sorted(PROFILES), default="hybrid")
    score.add_argument("--report", action="append", required=True, help="JSON report; repeat for multiple evidence files")
    score.add_argument("--baseline-score")
    score.add_argument("--output", required=True)

    gate = sub.add_parser("gate", help="compare a candidate score against a baseline and decide promotion/rollback")
    gate.add_argument("--candidate-score", required=True)
    gate.add_argument("--baseline-score")
    gate.add_argument("--output", required=True)
    for key in DEFAULT_TOLERANCES:
        gate.add_argument(f"--tolerance-{key.replace('_', '-')}", type=float, default=DEFAULT_TOLERANCES[key])

    case = sub.add_parser("record-case", help="append a hash-bound candidate to the distillation case registry")
    case.add_argument("--registry", required=True)
    case.add_argument("--case-id", required=True)
    case.add_argument("--candidate-id", required=True)
    case.add_argument("--profile", choices=sorted(PROFILES), default="hybrid")
    case.add_argument("--status", default="human-review-pending")
    case.add_argument("--source", action="append", required=True)
    case.add_argument("--deck", required=True)
    case.add_argument("--score", required=True)
    case.add_argument("--plan")
    case.add_argument("--report", action="append", default=[])
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "score":
            reports = [read_json(Path(value).resolve()) for value in args.report]
            result = score_candidate(reports, candidate_id=args.candidate_id, profile=args.profile)
            if args.baseline_score:
                baseline = read_json(Path(args.baseline_score).resolve())
                result["gate"] = gate_candidate(result, baseline, DEFAULT_TOLERANCES)
            atomic_write_json(Path(args.output).resolve(), result)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "gate":
            candidate = read_json(Path(args.candidate_score).resolve())
            baseline = read_json(Path(args.baseline_score).resolve()) if args.baseline_score else None
            tolerances = {key: max(0.0, float(getattr(args, f"tolerance_{key}"))) for key in DEFAULT_TOLERANCES}
            result = gate_candidate(candidate, baseline, tolerances)
            atomic_write_json(Path(args.output).resolve(), result)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["decision"] == "accept-for-human-review" else 2
        result = record_case(args)
        print(json.dumps({"schema": CASE_SCHEMA, "valid": True, "registry": str(Path(args.registry).resolve()), "case_count": len(result["cases"])}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema": FEEDBACK_SCHEMA, "valid": False, "status": "blocked", "code": "distillation_loop_failed", "message": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
