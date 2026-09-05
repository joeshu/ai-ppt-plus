from __future__ import annotations

import json
from pathlib import Path

from reconstruction.accepted_state import build_accepted_state, resolve_source_layout, write_accepted_state


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_iteration_one_uses_candidate(tmp_path: Path):
    candidate = tmp_path / "candidate" / "layout.json"
    _write_json(candidate, {"slides": []})
    resolved, meta = resolve_source_layout(case_id="case", iteration=1, candidate_layout=candidate, output_root=tmp_path / "out")
    assert resolved == candidate.resolve()
    assert meta == {
        "source": "candidate",
        "accepted_iteration": 0,
        "layout": str(candidate.resolve()),
    }


def test_iteration_two_uses_persisted_accepted_state(tmp_path: Path):
    candidate = tmp_path / "candidate" / "layout.json"
    accepted = tmp_path / "out" / "case" / "iteration-1" / "layout.json"
    _write_json(candidate, {"version": "candidate"})
    _write_json(accepted, {"version": "accepted-1"})
    record = {
        "accepted": True,
        "iteration": 1,
        "pixel_fidelity_score": 0.95,
        "semantic_accuracy": 1.0,
        "blocking_count": 0,
        "native_editability_valid": True,
        "artifacts": {"layout": str(accepted)},
    }
    state = build_accepted_state("case", record, iteration_dir=accepted.parent)
    write_accepted_state(tmp_path / "out" / "case" / "accepted-state.json", state)
    resolved, meta = resolve_source_layout(case_id="case", iteration=2, candidate_layout=candidate, output_root=tmp_path / "out")
    assert resolved == accepted.resolve()
    assert meta == {
        "source": "accepted-state",
        "accepted_iteration": 1,
        "layout": str(accepted.resolve()),
    }


def test_rollback_iteration_is_skipped_for_next_source(tmp_path: Path):
    candidate = tmp_path / "candidate" / "layout.json"
    accepted1 = tmp_path / "out" / "case" / "iteration-1" / "layout.json"
    rejected2 = tmp_path / "out" / "case" / "iteration-2" / "layout.json"
    _write_json(candidate, {"version": "candidate"})
    _write_json(accepted1, {"version": "accepted-1"})
    _write_json(rejected2, {"version": "rejected-2"})
    _write_json(accepted1.parent / "iteration-record.json", {"accepted": True, "status": "repaired-needs-qa"})
    _write_json(rejected2.parent / "iteration-record.json", {"accepted": False, "status": "rolled-back-regression"})
    resolved, meta = resolve_source_layout(case_id="case", iteration=3, candidate_layout=candidate, output_root=tmp_path / "out")
    assert resolved == accepted1.resolve()
    assert meta == {
        "source": "accepted-history",
        "accepted_iteration": 1,
        "layout": str(accepted1.resolve()),
    }


def test_stale_future_state_is_not_used(tmp_path: Path):
    candidate = tmp_path / "candidate" / "layout.json"
    future = tmp_path / "out" / "case" / "iteration-4" / "layout.json"
    _write_json(candidate, {"version": "candidate"})
    _write_json(future, {"version": "future"})
    _write_json(tmp_path / "out" / "case" / "accepted-state.json", {
        "schema": "ai-ppt-plus/astra-accepted-state/v1",
        "case_id": "case",
        "accepted_iteration": 4,
        "layout": str(future),
        "pptx": None,
        "pixel_fidelity_score": 0.96,
        "semantic_accuracy": 1.0,
        "blocking_count": 0,
        "native_editability_valid": True,
    })
    resolved, meta = resolve_source_layout(case_id="case", iteration=3, candidate_layout=candidate, output_root=tmp_path / "out")
    assert resolved == candidate.resolve()
    assert meta == {
        "source": "candidate",
        "accepted_iteration": 0,
        "layout": str(candidate.resolve()),
    }


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                value(Path(tmp))
    print("Accepted state tests passed")
