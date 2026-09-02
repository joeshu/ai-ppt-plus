#!/usr/bin/env python3
"""Run a bounded, policy-driven unattended distillation cycle.

The agent turns structured gate failures into a small, auditable repair
proposal, applies only pre-approved text blocks, reruns the repository gates,
and reports whether a candidate is safe for the workflow to commit. It is
deliberately conservative: unknown failures and implementation defects are
blocked for human repair instead of being guessed at by an unattended job.

The GitHub Actions workflow owns branch creation, commit, pull-request merge,
and the final remote CI dispatch. This program never pushes or merges code.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "ai-ppt-plus/unattended-distillation/v1"
ANALYSIS_SCHEMA = "ai-ppt-plus/distillation-analysis/v1"
RESULT_SCHEMA = "ai-ppt-plus/distillation-result/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


DEFAULT_POLICY: dict[str, Any] = {
    "schema": "ai-ppt-plus/unattended-distillation-policy/v1",
    "enabled": True,
    "max_rounds": 3,
    "max_changed_files": 4,
    "max_changed_lines": 240,
    "allowed_paths": [
        "SKILL.md",
        "references/*.md",
        "ai-ppt-editable/SKILL.md",
        "ai-ppt-editable/references/*.md",
    ],
    "protected_paths": [
        ".github/**",
        "*.yml",
        "*.yaml",
        "requirements*.txt",
        "assets/**",
        "*.py",
    ],
    "gates": [],
    "repair_rules": [],
}


CATEGORY_ORDER = (
    "routing",
    "native-structure",
    "text-visual",
    "package-contract",
    "cache-integrity",
    "unknown",
)

CATEGORY_TOKENS = {
    "routing": (
        "route", "routing", "engine", "fallback", "primary_engine",
        "binding", "backend", "ownership",
    ),
    "native-structure": (
        "native", "table", "panel", "semantic_object", "object_type",
        "formal_content_rasterized", "graphicframe", "a:tbl", "editability",
    ),
    "text-visual": (
        "visual", "pixel", "font", "typograph", "gradient", "icon",
        "text", "render", "overflow", "overlap",
    ),
    "package-contract": (
        "package", "skill_", "self_contained", "runtime", "dependency",
        "sync", "entrypoint",
    ),
    "cache-integrity": (
        "cache", "hash", "stale", "artifact", "fingerprint", "quarantine",
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(root: Path, value: str) -> Path:
    """Resolve a repository-relative path and reject traversal."""
    candidate = Path(str(value).replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"unsafe repository path: {value!r}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {value!r}") from exc
    return resolved


def repo_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return dict(DEFAULT_POLICY)
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("distillation policy must be a JSON object")
    merged = dict(DEFAULT_POLICY)
    merged.update(value)
    if not isinstance(merged.get("gates"), list):
        raise ValueError("distillation policy gates must be an array")
    if not isinstance(merged.get("repair_rules"), list):
        raise ValueError("distillation policy repair_rules must be an array")
    return merged


def text_excerpt(value: Any, limit: int = 1200) -> str:
    if isinstance(value, str):
        return value[:limit]
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        rendered = str(value)
    return rendered[:limit]


def issue_code(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("code", "error_code", "id", "name", "test"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def issue_message(value: Any) -> str:
    if not isinstance(value, dict):
        return text_excerpt(value)
    for key in ("message", "error", "stderr", "stdout", "detail", "observed"):
        candidate = value.get(key)
        if candidate:
            return text_excerpt(candidate)
    return text_excerpt(value)


def classify(code: str | None, message: str) -> str:
    haystack = f"{code or ''} {message}".lower()
    for category in CATEGORY_ORDER[:-1]:
        if any(token.lower() in haystack for token in CATEGORY_TOKENS[category]):
            return category
    return "unknown"


def _append_issue(
    found: list[dict[str, Any]], seen: set[tuple[str, str]], *,
    source: str, code: str | None, message: str, severity: str = "blocker",
) -> None:
    category = classify(code, message)
    normalized_code = code or f"unclassified_{category}"
    key = (normalized_code, message)
    if key in seen:
        return
    seen.add(key)
    found.append({
        "severity": severity,
        "code": normalized_code,
        "category": category,
        "message": message,
        "source": source,
    })


def _walk_report(value: Any, source: str, found: list[dict[str, Any]], seen: set[tuple[str, str]], path: str = "") -> None:
    """Extract failures from the repository's deliberately loose report shapes."""
    if isinstance(value, dict):
        status = str(value.get("status") or value.get("conclusion") or "").lower()
        valid = value.get("valid")
        if valid is False or status in {"failed", "failure", "blocked", "error", "cancelled", "timed_out"}:
            code = issue_code(value)
            message = issue_message(value)
            if code or message:
                _append_issue(found, seen, source=f"{source}:{path or '$'}", code=code, message=message)
        for key in ("issues", "errors", "failures", "failed", "blockers"):
            nested = value.get(key)
            if isinstance(nested, list):
                for index, item in enumerate(nested):
                    if isinstance(item, dict):
                        _append_issue(
                            found,
                            seen,
                            source=f"{source}:{path or '$'}.{key}[{index}]",
                            code=issue_code(item),
                            message=issue_message(item),
                            severity=str(item.get("severity") or "blocker"),
                        )
                    else:
                        _append_issue(
                            found,
                            seen,
                            source=f"{source}:{path or '$'}.{key}[{index}]",
                            code=None,
                            message=text_excerpt(item),
                        )
        for key, nested in value.items():
            if key in {"issues", "errors", "failures", "failed", "blockers"}:
                continue
            _walk_report(nested, source, found, seen, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _walk_report(nested, source, found, seen, f"{path}[{index}]")


def _scan_text(text: str, source: str, found: list[dict[str, Any]], seen: set[tuple[str, str]]) -> None:
    for line in text.splitlines():
        if not re.search(r"\b(fail|failed|failure|error|blocked|exception|traceback)\b", line, re.IGNORECASE):
            continue
        match = re.search(r"(?:code|error_code|id)\s*[:=]\s*['\"]?([A-Za-z0-9_.:/-]+)", line, re.IGNORECASE)
        _append_issue(found, seen, source=source, code=match.group(1) if match else None, message=line.strip())


def discover_reports(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        return []
    return sorted(path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".json", ".log", ".txt"})


def analyze_reports(paths: list[Path], root: Path, *, round_no: int = 0) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    readable: list[str] = []
    for path in paths:
        try:
            relative = repo_relative(root, path)
        except ValueError:
            relative = str(path)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _append_issue(found, seen, source=relative, code="report_unreadable", message=str(exc))
            continue
        readable.append(relative)
        if path.suffix.lower() == ".json":
            try:
                _walk_report(json.loads(raw), relative, found, seen)
            except json.JSONDecodeError:
                _scan_text(raw, relative, found, seen)
        else:
            _scan_text(raw, relative, found, seen)
    categories = {item["category"] for item in found}
    status = "issues-found" if found else "clean" if readable else "no-evidence"
    return {
        "schema": ANALYSIS_SCHEMA,
        "generated_at": utc_now(),
        "round": round_no,
        "status": status,
        "evidence_files": readable,
        "issue_count": len(found),
        "categories": [category for category in CATEGORY_ORDER if category in categories],
        "issues": found,
        "requires_manual": "unknown" in categories,
    }


def rule_candidates(analysis: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    categories = set(analysis.get("categories") or [])
    candidates = [
        rule for rule in policy.get("repair_rules", [])
        if isinstance(rule, dict) and rule.get("category") in categories
    ]
    return sorted(candidates, key=lambda rule: int(rule.get("priority", 0)), reverse=True)


def validate_rule(rule: dict[str, Any], root: Path, policy: dict[str, Any]) -> Path:
    target_text = rule.get("target")
    if not isinstance(target_text, str) or not target_text:
        raise ValueError("repair rule target is missing")
    target = safe_relative(root, target_text)
    relative = repo_relative(root, target)
    protected = policy.get("protected_paths") or []
    allowed = policy.get("allowed_paths") or []
    if matches_any(relative, protected):
        raise ValueError(f"repair target is protected: {relative}")
    if not matches_any(relative, allowed):
        raise ValueError(f"repair target is outside allowlist: {relative}")
    if rule.get("operation") != "ensure_block":
        raise ValueError(f"unsupported repair operation: {rule.get('operation')!r}")
    marker = rule.get("marker")
    block = rule.get("block")
    if not isinstance(marker, str) or not marker.strip() or not isinstance(block, str) or not block.strip():
        raise ValueError("ensure_block requires marker and block")
    return target


def apply_repair(rule: dict[str, Any], root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    target = validate_rule(rule, root, policy)
    relative = repo_relative(root, target)
    if not target.is_file():
        raise ValueError(f"repair target does not exist: {relative}")
    original = target.read_text(encoding="utf-8")
    marker = str(rule["marker"])
    if marker in original:
        return {"changed": False, "target": relative, "rule_id": rule.get("id"), "reason": "marker-already-present"}
    updated = original.rstrip() + "\n\n" + str(rule["block"]).strip() + "\n"
    target.write_text(updated, encoding="utf-8")
    return {
        "changed": True,
        "target": relative,
        "rule_id": rule.get("id"),
        "added_lines": len(updated.splitlines()) - len(original.splitlines()),
    }


def tracked_diff(root: Path) -> tuple[list[str], int]:
    try:
        names = subprocess.run(
            ["git", "diff", "--name-only"], cwd=root, capture_output=True, text=True, check=False,
        )
        stats = subprocess.run(
            ["git", "diff", "--numstat"], cwd=root, capture_output=True, text=True, check=False,
        )
    except OSError:
        return [], 0
    files = [line.strip() for line in names.stdout.splitlines() if line.strip()]
    lines = 0
    for line in stats.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit():
            lines += int(fields[0]) + int(fields[1])
    return files, lines


def tracked_worktree_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "diff", "--quiet"], cwd=root, capture_output=True, check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def run_gate(gate: dict[str, Any], root: Path, report_dir: Path, round_no: int) -> dict[str, Any]:
    gate_id = str(gate.get("id") or "gate")
    argv = gate.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        return {"id": gate_id, "status": "failed", "returncode": 2, "stderr": "invalid gate argv", "stdout": ""}
    command = list(argv)
    if command[0] in {"python", "python3"}:
        command[0] = sys.executable
    timeout = int(gate.get("timeout_seconds", 600))
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout[-12000:]
        stderr = completed.stderr[-12000:]
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = text_excerpt(exc.stdout)
        stderr = text_excerpt(exc.stderr) + f"\ntimed out after {timeout}s"
        returncode = 124
    except OSError as exc:
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}"
        returncode = 127
    result = {
        "id": gate_id,
        "argv": command,
        "status": "passed" if returncode == 0 else "failed",
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / f"gate-{round_no}-{gate_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return result


def run_gates(policy: dict[str, Any], root: Path, report_dir: Path, round_no: int) -> dict[str, Any]:
    results = [run_gate(gate, root, report_dir, round_no) for gate in policy.get("gates", [])]
    result = {
        "schema": "ai-ppt-plus/distillation-gates/v1",
        "generated_at": utc_now(),
        "round": round_no,
        "valid": bool(results) and all(item["status"] == "passed" for item in results),
        "status": "passed" if results and all(item["status"] == "passed" for item in results) else "failed",
        "gates": results,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"gate-results-{round_no}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"result": result, "path": path}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_github_output(path_text: str | None, values: dict[str, Any]) -> None:
    if not path_text:
        return
    path = Path(path_text)
    with path.open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n")


def command_analyze(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    input_dir = Path(args.input_dir).resolve()
    reports = discover_reports(input_dir)
    analysis = analyze_reports(reports, root, round_no=args.round)
    analysis["policy"] = str(Path(args.policy).resolve()) if args.policy else None
    write_json(Path(args.output).resolve(), analysis)
    print(json.dumps(analysis, ensure_ascii=False))
    return 0


def command_apply(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    policy = load_policy(Path(args.policy).resolve() if args.policy else None)
    analysis = load_json(Path(args.analysis).resolve())
    if not isinstance(analysis, dict):
        raise ValueError("analysis must be a JSON object")
    candidates = rule_candidates(analysis, policy)
    if not candidates:
        result = {"schema": SCHEMA, "status": "blocked", "changed": False, "reason": "no-approved-repair-for-analysis"}
    else:
        result = apply_repair(candidates[0], root, policy)
        result.update({"schema": SCHEMA, "status": "changed" if result["changed"] else "no-change", "category": candidates[0].get("category")})
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") in {"changed", "no-change"} else 2


def command_run(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    policy = load_policy(Path(args.policy).resolve() if args.policy else None)
    if policy.get("enabled") is not True:
        result = {"schema": RESULT_SCHEMA, "status": "disabled", "changed": False, "requires_manual": True}
        write_json(Path(args.output).resolve(), result)
        write_github_output(args.github_output, {"status": "disabled", "changed": False})
        print(json.dumps(result, ensure_ascii=False))
        return 2
    if not tracked_worktree_clean(root):
        result = {"schema": RESULT_SCHEMA, "status": "blocked", "changed": False, "requires_manual": True, "reason": "tracked_worktree_not_clean"}
        write_json(Path(args.output).resolve(), result)
        write_github_output(args.github_output, {"status": "blocked", "changed": False})
        print(json.dumps(result, ensure_ascii=False))
        return 2

    input_dir = Path(args.input_dir).resolve()
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    reports = discover_reports(input_dir)
    changed = False
    repairs: list[dict[str, Any]] = []
    gate_runs: list[dict[str, Any]] = []
    analysis = analyze_reports(reports, root, round_no=0)
    max_rounds = min(int(args.max_rounds or policy.get("max_rounds", 3)), int(policy.get("max_rounds", 3)))
    if max_rounds < 1:
        max_rounds = 1

    for round_no in range(1, max_rounds + 1):
        if analysis["status"] in {"clean", "no-evidence"}:
            gate_run = run_gates(policy, root, report_dir, round_no)
            gate_runs.append(gate_run["result"])
            # The downloaded CI report is historical evidence that caused the
            # repair. Once a candidate has been tested, judge the candidate by
            # its fresh gate report rather than replaying the stale failure.
            reports = [gate_run["path"]]
            analysis = analyze_reports(reports, root, round_no=round_no)
            if gate_run["result"]["valid"]:
                break
        if analysis["status"] != "issues-found":
            break
        if analysis.get("requires_manual"):
            break
        candidates = rule_candidates(analysis, policy)
        if not candidates:
            break
        try:
            repair = apply_repair(candidates[0], root, policy)
        except (OSError, ValueError) as exc:
            repairs.append({"rule_id": candidates[0].get("id"), "status": "blocked", "error": str(exc)})
            break
        repairs.append(repair)
        if not repair.get("changed"):
            break
        changed = True
        gate_run = run_gates(policy, root, report_dir, round_no)
        gate_runs.append(gate_run["result"])
        # Do not let the pre-repair failure keep a passing candidate blocked.
        reports = [gate_run["path"]]
        analysis = analyze_reports(reports, root, round_no=round_no)
        if gate_run["result"]["valid"]:
            break

    diff_files, diff_lines = tracked_diff(root)
    allowed = policy.get("allowed_paths") or []
    protected = policy.get("protected_paths") or []
    diff_issues: list[str] = []
    for path in diff_files:
        if matches_any(path, protected) or not matches_any(path, allowed):
            diff_issues.append(path)
    if len(diff_files) > int(policy.get("max_changed_files", 4)):
        diff_issues.append("max_changed_files_exceeded")
    if diff_lines > int(policy.get("max_changed_lines", 240)):
        diff_issues.append("max_changed_lines_exceeded")
    if diff_issues:
        analysis.setdefault("issues", []).append({
            "severity": "blocker",
            "code": "distillation_change_scope_exceeded",
            "category": "package-contract",
            "message": ", ".join(diff_issues),
            "source": "agent",
        })

    gate_valid = bool(gate_runs) and gate_runs[-1].get("valid") is True
    final_status = "passed" if gate_valid and not diff_issues and analysis.get("status") in {"clean", "no-evidence"} else "blocked"
    result = {
        "schema": RESULT_SCHEMA,
        "generated_at": utc_now(),
        "status": final_status,
        "changed": bool(changed and final_status == "passed"),
        "requires_manual": final_status != "passed",
        "max_rounds": max_rounds,
        "rounds_used": len(gate_runs),
        "analysis": analysis,
        "repairs": repairs,
        "gate_runs": gate_runs,
        "changed_files": diff_files,
        "changed_lines": diff_lines,
        "scope_issues": diff_issues,
    }
    write_json(Path(args.output).resolve(), result)
    write_github_output(args.github_output, {
        "status": final_status,
        "changed": result["changed"],
        "requires_manual": result["requires_manual"],
        "rounds_used": result["rounds_used"],
    })
    print(json.dumps(result, ensure_ascii=False))
    return 0 if final_status == "passed" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--repo-root", default=".")
    analyze.add_argument("--input-dir", required=True)
    analyze.add_argument("--policy")
    analyze.add_argument("--output", required=True)
    analyze.add_argument("--round", type=int, default=0)
    analyze.set_defaults(handler=command_analyze)

    apply = subparsers.add_parser("apply")
    apply.add_argument("--repo-root", default=".")
    apply.add_argument("--policy")
    apply.add_argument("--analysis", required=True)
    apply.add_argument("--output", required=True)
    apply.set_defaults(handler=command_apply)

    run = subparsers.add_parser("run")
    run.add_argument("--repo-root", default=".")
    run.add_argument("--input-dir", required=True)
    run.add_argument("--report-dir", required=True)
    run.add_argument("--policy")
    run.add_argument("--output", required=True)
    run.add_argument("--max-rounds", type=int)
    run.add_argument("--github-output")
    run.set_defaults(handler=command_run)

    args = parser.parse_args()
    try:
        return int(args.handler(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"schema": RESULT_SCHEMA, "status": "blocked", "changed": False, "requires_manual": True, "reason": f"{type(exc).__name__}: {exc}"}
        output = getattr(args, "output", None)
        if output:
            write_json(Path(output).resolve(), result)
        write_github_output(getattr(args, "github_output", None), {"status": "blocked", "changed": False, "requires_manual": True})
        print(json.dumps(result, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
