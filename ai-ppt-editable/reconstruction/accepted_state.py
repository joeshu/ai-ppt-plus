#!/usr/bin/env python3
"""Persist and resolve the last accepted Astra reconstruction state per case."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


SCHEMA = "ai-ppt-plus/astra-accepted-state/v1"


@dataclass(frozen=True)
class AcceptedState:
    schema: str
    case_id: str
    accepted_iteration: int
    layout: str
    pptx: str | None
    pixel_fidelity_score: float | None
    semantic_accuracy: float | None
    blocking_count: int
    native_editability_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_accepted_state(case_id: str, record: dict[str, Any], *, iteration_dir: Path) -> AcceptedState:
    if record.get("accepted") is not True:
        raise ValueError("cannot persist a non-accepted iteration as accepted state")
    artifacts = record.get("artifacts") or {}
    layout = Path(str(artifacts.get("layout") or iteration_dir / "layout.json"))
    pptx_value = artifacts.get("pptx")
    score = record.get("pixel_fidelity_score")
    semantic = record.get("semantic_accuracy")
    return AcceptedState(
        schema=SCHEMA,
        case_id=case_id,
        accepted_iteration=int(record.get("iteration") or 0),
        layout=str(layout.resolve()),
        pptx=str(Path(str(pptx_value)).resolve()) if pptx_value else None,
        pixel_fidelity_score=float(score) if score is not None else None,
        semantic_accuracy=float(semantic) if semantic is not None else None,
        blocking_count=int(record.get("blocking_count", 0) or 0),
        native_editability_valid=record.get("native_editability_valid") is True,
    )


def write_accepted_state(path: Path, state: AcceptedState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_accepted_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    return value


def resolve_source_layout(*, case_id: str, iteration: int, candidate_layout: Path, output_root: Path) -> tuple[Path, dict[str, Any]]:
    """Resolve the latest accepted layout strictly before the requested iteration.

    Priority:
    1. accepted-state.json when it points to an earlier accepted iteration and an existing layout;
    2. backward scan of prior iteration records for the newest accepted iteration;
    3. original candidate layout.
    """
    state_path = output_root / case_id / "accepted-state.json"
    state = read_accepted_state(state_path)
    if state is not None:
        accepted_iteration = int(state.get("accepted_iteration", 0) or 0)
        layout = Path(str(state.get("layout") or ""))
        if accepted_iteration < iteration and layout.is_file():
            return layout.resolve(), {"source": "accepted-state", "accepted_iteration": accepted_iteration}

    for previous_iteration in range(iteration - 1, 0, -1):
        iteration_dir = output_root / case_id / f"iteration-{previous_iteration}"
        record_path = iteration_dir / "iteration-record.json"
        layout_path = iteration_dir / "layout.json"
        if not record_path.is_file() or not layout_path.is_file():
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("accepted") is True and not str(record.get("status") or "").startswith("rolled-back"):
            return layout_path.resolve(), {"source": "accepted-history", "accepted_iteration": previous_iteration}

    if not candidate_layout.is_file():
        raise FileNotFoundError(f"candidate layout missing: {candidate_layout}")
    return candidate_layout.resolve(), {"source": "candidate", "accepted_iteration": 0}
