#!/usr/bin/env python3
"""Resumable A-O orchestration state for image/reference reconstruction.

This is a small control plane around the existing worker pipelines.  It does
not author slides itself.  It records immutable input/output hashes, applies
dependency-aware invalidation and exposes a safe resume plan so a caller can
reuse successful analysis without mistaking an old draft for a final PPTX.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Mapping
import uuid

from atomic_output import atomic_write_json


SCHEMA = "ai-ppt-plus/incremental-checkpoint/v1"
STAGE_NAMES = tuple("ABCDEFGHIJKLMNO")


@dataclass(frozen=True)
class StageSpec:
    code: str
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    retry: str
    cacheable: bool
    parallel: bool
    recovery: str


STAGE_SPECS: tuple[StageSpec, ...] = (
    StageSpec("A", "repository_preflight", ("repository",), ("repository-report",), "none", True, False, "resume A after repository SHA check"),
    StageSpec("B", "input_discovery", ("attachments",), ("input-roster",), "bounded lookup", True, False, "rerun B with the same ordered inputs"),
    StageSpec("C", "source_manifest", ("input-roster",), ("source-manifest",), "none", True, True, "resume from C when input hashes match"),
    StageSpec("D", "skill_contract_load", ("package_revision", "skill_artifacts"), ("contract-snapshot",), "none", True, False, "reload the pinned skill revision and artifact hashes"),
    StageSpec("E", "reference_analysis", ("source-manifest",), ("analysis",), "idempotent", True, True, "rerun only affected pages"),
    StageSpec("F", "font_preflight", ("fonts",), ("font-report",), "none", True, True, "rerun when a font hash changes"),
    StageSpec("G", "asset_preparation", ("analysis", "fonts"), ("asset-manifest",), "idempotent", True, True, "invalidate dependent pages"),
    StageSpec("H", "artifact_marker", ("contract-snapshot",), ("marker-receipt",), "none", False, False, "never repeat a successful marker in one run"),
    StageSpec("I", "native_authoring", ("source-manifest", "analysis", "fonts", "assets"), ("intermediate-pptx", "object-inventory"), "content errors fail", False, False, "resume from the last valid authoring source"),
    StageSpec("J", "fast_render", ("intermediate-pptx",), ("fast-render",), "transient only", True, True, "render affected pages"),
    StageSpec("K", "visual_refinement", ("fast-render", "analysis"), ("refined-pptx",), "human decision", False, False, "resume at the affected page/region"),
    StageSpec("L", "finalizer", ("refined-pptx",), ("finalizer-receipt",), "output conflict fails", False, False, "use a new output name after conflict"),
    StageSpec("M", "final_render", ("final-pptx",), ("final-render",), "transient only", True, True, "render the exact final hash"),
    StageSpec("N", "technical_audit", ("final-pptx", "final-render"), ("audit-report",), "none", True, True, "rerun audit when final hash changes"),
    StageSpec("O", "package_delivery", ("audit-report", "final-pptx"), ("delivery-report",), "none", False, False, "promote only after all gates pass"),
)
SPEC_BY_CODE = {spec.code: spec for spec in STAGE_SPECS}
DIRECT_DEPENDENTS: dict[str, tuple[str, ...]] = {
    "A": (),
    "B": ("C",),
    "C": ("E", "I"),
    "D": ("H", "I"),
    "E": ("G", "I", "K"),
    "F": ("G", "I"),
    "G": ("I",),
    "H": ("I",),
    "I": ("J",),
    "J": ("K",),
    "K": ("L",),
    "L": ("M",),
    "M": ("N",),
    "N": ("O",),
    "O": (),
}


def impacted_stages(code: str) -> tuple[str, ...]:
    """Return only the stages reachable from a changed dependency."""
    seen: set[str] = set()
    pending = [code]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(DIRECT_DEPENDENTS.get(current, ()))
    return tuple(item for item in STAGE_NAMES if item in seen)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: str | Path) -> str:
    path = Path(path)
    if path.is_file():
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    if path.is_dir():
        records = []
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            records.append({"path": str(child.relative_to(path)), "sha256": digest(child), "size": child.stat().st_size})
        return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    return ""


def file_record(raw: str | Path) -> dict[str, Any]:
    path = Path(raw).resolve()
    return {"path": str(path), "exists": path.exists(), "sha256": digest(path) if path.exists() else None, "size": path.stat().st_size if path.is_file() else None}


def _stage(code: str) -> dict[str, Any]:
    spec = SPEC_BY_CODE[code]
    return {"code": code, "name": spec.name, "status": "pending", "cacheable": spec.cacheable, "parallel": spec.parallel, "retry_policy": spec.retry, "recovery": spec.recovery, "retry_count": 0, "outputs": {}, "failure": None}


class CheckpointStore:
    """Atomic checkpoint persistence and dependency-aware resume decisions."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.data: dict[str, Any] = {}

    @classmethod
    def create(cls, path: str | Path, *, project_root: str | Path, repository_sha: str, package_revision: str, inputs: Iterable[str | Path] = (), fonts: Iterable[str | Path] = (), skill_artifacts: Iterable[str | Path] = (), run_id: str | None = None) -> "CheckpointStore":
        store = cls(path)
        store.data = {
            "schema": SCHEMA,
            "schema_version": 1,
            "run_id": run_id or f"run-{uuid.uuid4().hex}",
            "project_root": str(Path(project_root).resolve()),
            "repository_sha": repository_sha,
            "package_revision": package_revision,
            "inputs": [file_record(item) for item in inputs],
            "fonts": [file_record(item) for item in fonts],
            "skill_artifacts": [file_record(item) for item in skill_artifacts],
            "stages": {code: _stage(code) for code in STAGE_NAMES},
            "artifact_marker": {"status": "pending", "receipt_sha256": None},
            "build_source_sha": None,
            "intermediate_pptx_sha": None,
            "final_pptx_sha": None,
            "completed_validations": [],
            "failures": [],
            "resume": {"last_plan_at": None, "invalidated": [], "entry_stage": "A"},
            "updated_at": now(),
        }
        store.save()
        return store

    def save(self) -> None:
        if self.data.get("schema") != SCHEMA:
            raise ValueError("checkpoint_schema_invalid")
        self.data["updated_at"] = now()
        atomic_write_json(self.path, self.data)

    def load(self) -> dict[str, Any]:
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        if self.data.get("schema") != SCHEMA or self.data.get("schema_version") != 1:
            raise ValueError("checkpoint_schema_invalid")
        if not isinstance(self.data.get("stages"), dict):
            raise ValueError("checkpoint_stages_invalid")
        return self.data

    def _invalidate(self, code: str, reasons: list[str]) -> None:
        affected = impacted_stages(code)
        for stage_code in affected:
            stage = self.data["stages"].setdefault(stage_code, _stage(stage_code))
            if stage.get("status") == "passed":
                stage["status"] = "invalidated"
            stage["failure"] = {"code": "resume_invalidation", "reasons": sorted(set(reasons))}
            stage["outputs"] = {}
        if code == "H":
            self.data["artifact_marker"] = {"status": "pending", "receipt_sha256": None}

    def resume_plan(self, *, repository_sha: str | None = None, package_revision: str | None = None, skill_artifacts: Iterable[str | Path] | None = None) -> dict[str, Any]:
        if not self.data:
            self.load()
        changed_inputs: list[dict[str, Any]] = []
        for group in ("inputs", "fonts"):
            for record in self.data.get(group, []):
                current = file_record(record.get("path", ""))
                if current.get("sha256") != record.get("sha256") or current.get("exists") != record.get("exists"):
                    changed_inputs.append({"group": group, "path": record.get("path"), "expected": record.get("sha256"), "observed": current.get("sha256")})
                    self._invalidate("B" if group == "inputs" else "F", [f"{group}_hash_changed"])
        if repository_sha and repository_sha != self.data.get("repository_sha"):
            self._invalidate("A", ["repository_sha_changed"])
        if package_revision and package_revision != self.data.get("package_revision"):
            self._invalidate("D", ["package_revision_changed"])
        if skill_artifacts is not None:
            observed_artifacts = [file_record(item) for item in skill_artifacts]
            expected_artifacts = self.data.get("skill_artifacts", [])
            if observed_artifacts != expected_artifacts:
                self._invalidate("D", ["skill_artifact_hash_changed"])
                self.data["skill_artifacts"] = observed_artifacts
        output_mismatches: list[dict[str, Any]] = []
        for code, stage in self.data.get("stages", {}).items():
            if stage.get("status") not in {"passed", "cached"}:
                continue
            outputs = stage.get("outputs", {})
            for raw, expected in outputs.items():
                observed = digest(raw) if Path(raw).exists() else None
                expected_hash = expected.get("sha256") if isinstance(expected, Mapping) else expected
                if not observed or observed != expected_hash:
                    output_mismatches.append({"stage": code, "path": raw, "expected": expected_hash, "observed": observed})
                    self._invalidate(code, ["output_hash_changed"])
                    break
        invalidated = [code for code, stage in self.data["stages"].items() if stage.get("status") == "invalidated"]
        pending = [code for code in STAGE_NAMES if self.data["stages"].get(code, {}).get("status") not in {"passed", "cached"}]
        # Prefer the earliest explicitly invalidated node.  This lets a new
        # run start at A while a resumed run with a changed page starts at B/C
        # instead of replaying an unrelated pending stage from initialization.
        entry = (sorted(invalidated, key=STAGE_NAMES.index)[0] if invalidated else (pending[0] if pending else "O"))
        self.data["resume"] = {"last_plan_at": now(), "invalidated": invalidated, "entry_stage": entry}
        self.save()
        return {"schema": "ai-ppt-plus/resume-plan/v1", "consistent": not changed_inputs and not output_mismatches, "changed_inputs": changed_inputs, "output_mismatches": output_mismatches, "invalidated": invalidated, "entry_stage": entry, "artifact_marker_reusable": self.data.get("artifact_marker", {}).get("status") == "passed" and "H" not in invalidated}

    def record_stage(self, code: str, *, status: str = "passed", outputs: Iterable[str | Path] = (), duration_ms: float = 0.0, retry_count: int = 0, failure: Mapping[str, Any] | None = None, validation_name: str | None = None) -> dict[str, Any]:
        if code not in SPEC_BY_CODE:
            raise ValueError(f"unknown_stage:{code}")
        stage = self.data["stages"].setdefault(code, _stage(code))
        if code == "H" and stage.get("status") == "passed" and status == "passed":
            raise ValueError("artifact_marker_already_completed")
        records = {}
        for raw in outputs:
            path = Path(raw).resolve()
            records[str(path)] = {"sha256": digest(path) if path.exists() else None, "exists": path.exists(), "size": path.stat().st_size if path.is_file() else None}
        stage.update({"status": status, "started_at": stage.get("started_at") or now(), "completed_at": now(), "duration_ms": round(float(duration_ms), 3), "retry_count": int(retry_count), "outputs": records, "failure": dict(failure) if failure else None})
        if status == "passed":
            for item in records:
                if code == "I": self.data["intermediate_pptx_sha"] = records[item].get("sha256")
                if code == "L": self.data["final_pptx_sha"] = records[item].get("sha256")
                if code == "M": self.data["final_pptx_sha"] = records[item].get("sha256") or self.data.get("final_pptx_sha")
            if code == "H":
                marker = next(iter(records.values()), {})
                self.data["artifact_marker"] = {"status": "passed", "receipt_sha256": marker.get("sha256")}
            if validation_name and validation_name not in self.data["completed_validations"]:
                self.data["completed_validations"].append(validation_name)
        elif failure:
            self.data["failures"].append({"stage": code, **dict(failure), "at": now()})
        self.save()
        return stage

    def execute(self, code: str, action: Callable[[], Any], *, outputs: Iterable[str | Path] = (), validation_name: str | None = None) -> dict[str, Any]:
        """Run one stage and persist a failure checkpoint before propagating."""
        started = time.perf_counter()
        try:
            action()
        except Exception as exc:
            self.record_stage(code, status="failed", duration_ms=(time.perf_counter() - started) * 1000, failure={"code": type(exc).__name__, "message": str(exc)})
            raise
        return self.record_stage(code, outputs=outputs, duration_ms=(time.perf_counter() - started) * 1000, validation_name=validation_name)


def stage_protocol() -> list[dict[str, Any]]:
    return [{"code": spec.code, "stage": spec.name, "inputs": list(spec.inputs), "outputs": list(spec.outputs), "retry": spec.retry, "cacheable": spec.cacheable, "parallel": spec.parallel, "recovery": spec.recovery} for spec in STAGE_SPECS]


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--state", required=True)
    init.add_argument("--project-root", required=True)
    init.add_argument("--repository-sha", required=True)
    init.add_argument("--package-revision", required=True)
    init.add_argument("--input", action="append", default=[])
    init.add_argument("--font", action="append", default=[])
    init.add_argument("--skill-artifact", action="append", default=[])
    resume = sub.add_parser("resume")
    resume.add_argument("--state", required=True)
    resume.add_argument("--repository-sha")
    resume.add_argument("--package-revision")
    resume.add_argument("--skill-artifact", action="append")
    protocol = sub.add_parser("protocol")
    args = parser.parse_args()
    if args.command == "init":
        store = CheckpointStore.create(args.state, project_root=args.project_root, repository_sha=args.repository_sha, package_revision=args.package_revision, inputs=args.input, fonts=args.font, skill_artifacts=args.skill_artifact)
        print(json.dumps({"valid": True, "state": str(store.path), "run_id": store.data["run_id"], "stages": stage_protocol()}, ensure_ascii=False))
        return 0
    if args.command == "resume":
        store = CheckpointStore(args.state); store.load(); print(json.dumps(store.resume_plan(repository_sha=args.repository_sha, package_revision=args.package_revision, skill_artifacts=args.skill_artifact), ensure_ascii=False)); return 0
    print(json.dumps({"schema": "ai-ppt-plus/stage-protocol/v1", "stages": stage_protocol()}, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
