from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from pathlib import Path

from PIL import Image

from reconstruction.accepted_state import build_accepted_state, resolve_source_layout, write_accepted_state
from reconstruction.asset_orchestrator import bind_generated_asset, validate_generated_asset
from reconstruction.asset_quality_qa import parse_asset_quality_response
from reconstruction.difference_graph import DifferenceGraph
from reconstruction.distillation_record import build_distillation_record
from reconstruction.distillation_selection import classify_record
from reconstruction.golden_promotion import build_promotion_manifest, evaluate_case
from reconstruction.repair_executors import execute_plan
from reconstruction.repair_router import RepairRouter


def _deck() -> dict:
    return {
        "units": "fraction",
        "slides": [
            {
                "texts": [
                    {"object_id": "title", "x": 0.10, "y": 0.08, "w": 0.50, "h": 0.10, "text": "Astra", "font_size": 24},
                ],
                "icons": [
                    {
                        "object_id": "hero-icon",
                        "x": 0.68,
                        "y": 0.18,
                        "w": 0.16,
                        "h": 0.16,
                        "rotation": 0,
                        "file": "source-icon.png",
                        "background_mode": "transparent",
                    }
                ],
            }
        ],
    }


def _graph() -> DifferenceGraph:
    return DifferenceGraph.from_dict(
        {
            "version": "1.0",
            "source_id": "source.png",
            "rendered_id": "candidate.png",
            "findings": [
                {
                    "id": "typography:title",
                    "object_id": "title",
                    "domain": "typography",
                    "severity": "P2",
                    "message": "title is too small",
                    "confidence": 0.97,
                    "proposed_patch": {"font_size": 30},
                },
                {
                    "id": "asset:hero-icon",
                    "object_id": "hero-icon",
                    "domain": "asset",
                    "severity": "P1",
                    "message": "icon visual fidelity is insufficient",
                    "confidence": 0.96,
                    "proposed_patch": {
                        "regenerate": True,
                        "generation_prompt": "Recreate the same icon faithfully.",
                        "background_mode": "transparent",
                    },
                },
            ],
        }
    )


def _transparent_png(path: Path) -> None:
    image = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (30, 90, 180, 255))
    image.save(path, format="PNG")


def _semantic_audit() -> dict:
    return {
        "valid": True,
        "accuracy": 1.0,
        "error_count": 0,
        "warning_count": 0,
        "expected_object_count": 2,
        "audited_object_count": 2,
    }


def _iteration_record(*, iteration: int, source_layout: Path, accepted_iteration: int, layout: Path, pptx: Path) -> dict:
    return {
        "case_id": "provider-neutral-full-loop",
        "iteration": iteration,
        "status": "repaired-needs-qa",
        "accepted": True,
        "resume_after_assets": True,
        "source_resolution": {
            "source": "candidate" if accepted_iteration == 0 else "accepted-state",
            "accepted_iteration": accepted_iteration,
            "layout": str(source_layout.resolve()),
        },
        "repair_action_count": 1,
        "repair_engine_counts": {"typography_repair": 1},
        "pixel_fidelity_score": 0.97,
        "blocking_count": 0,
        "native_editability_valid": True,
        "semantic_accuracy": 1.0,
        "semantic_audit": _semantic_audit(),
        "object_drift": {"valid": True, "allowed_object_ids": ["title", "hero-icon"], "unauthorized_drift_count": 0, "unauthorized_objects": []},
        "regression": {"rollback": False, "reasons": [], "pixel_fidelity_delta": 0.02, "blocking_delta": -1},
        "artifacts": {"layout": str(layout.resolve()), "pptx": str(pptx.resolve())},
    }


def test_provider_neutral_control_plane_completes_one_asset_resume_round_and_promotes_only_reproducible_history():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_layout = root / "candidate-layout.json"
        source_layout.write_text(json.dumps(_deck()), encoding="utf-8")

        router = RepairRouter(min_auto_confidence=0.82)
        plan = router.build_plan(_graph())
        execution = execute_plan(_deck(), plan)
        assert execution["report"]["requires_external_asset_generation"] is True
        assert [item["object_id"] for item in execution["report"]["applied"]] == ["title"]
        assert [item["object_id"] for item in execution["report"]["regeneration_requests"]] == ["hero-icon"]
        assert execution["deck"]["slides"][0]["texts"][0]["font_size"] == 30

        generation_request = execution["report"]["regeneration_requests"][0]
        generated_png = root / "hero-icon-generated.png"
        _transparent_png(generated_png)
        generated = validate_generated_asset(
            generation_request,
            {"object_id": "hero-icon", "file": str(generated_png), "background_mode": "transparent"},
        )
        quality = parse_asset_quality_response(
            {
                "object_id": "hero-icon",
                "approved": True,
                "score": 0.96,
                "structure_score": 0.97,
                "style_score": 0.95,
                "confidence": 0.94,
                "issue_codes": [],
                "reasons": [],
                "retry_native_generation": False,
            },
            expected_object_id="hero-icon",
        )
        assert quality["approved"] is True

        before_geometry = {k: execution["deck"]["slides"][0]["icons"][0][k] for k in ("x", "y", "w", "h", "rotation")}
        bound = bind_generated_asset(execution["deck"], generation_request, generated)
        after_geometry = {k: bound["deck"]["slides"][0]["icons"][0][k] for k in ("x", "y", "w", "h", "rotation")}
        assert after_geometry == before_geometry
        assert bound["deck"]["slides"][0]["icons"][0]["generation_provenance"]["kind"] == "native_image_generation"

        iteration1_dir = root / "runs" / "provider-neutral-full-loop" / "iteration-1"
        iteration1_dir.mkdir(parents=True)
        layout1 = iteration1_dir / "layout.json"
        layout1.write_text(json.dumps(bound["deck"]), encoding="utf-8")
        pptx1 = iteration1_dir / "editable.pptx"
        pptx1.write_bytes(b"pptx-sentinel")
        record1 = _iteration_record(iteration=1, source_layout=source_layout, accepted_iteration=0, layout=layout1, pptx=pptx1)
        state1 = build_accepted_state("provider-neutral-full-loop", record1, iteration_dir=iteration1_dir)
        accepted_state_path = root / "runs" / "provider-neutral-full-loop" / "accepted-state.json"
        write_accepted_state(accepted_state_path, state1)

        resolved2, meta2 = resolve_source_layout(
            case_id="provider-neutral-full-loop",
            iteration=2,
            candidate_layout=source_layout,
            output_root=root / "runs",
        )
        assert resolved2 == layout1.resolve()
        assert meta2["accepted_iteration"] == 1
        assert meta2["layout"] == str(layout1.resolve())

        iteration2_dir = root / "runs" / "provider-neutral-full-loop" / "iteration-2"
        iteration2_dir.mkdir(parents=True)
        layout2 = iteration2_dir / "layout.json"
        layout2.write_text(json.dumps(bound["deck"]), encoding="utf-8")
        pptx2 = iteration2_dir / "editable.pptx"
        pptx2.write_bytes(b"pptx-sentinel-v2")
        record2 = _iteration_record(iteration=2, source_layout=resolved2, accepted_iteration=1, layout=layout2, pptx=pptx2)

        distilled1 = build_distillation_record(iteration_record=record1, asset_resolution={"resolved_count": 1}, human_approved=True).to_dict()
        distilled2 = build_distillation_record(iteration_record=record2, asset_resolution={"resolved_count": 1}, human_approved=True).to_dict()
        assert distilled1["source_accepted_iteration"] == 0
        assert distilled2["source_accepted_iteration"] == 1
        assert distilled2["source_layout"] == str(layout1.resolve())
        assert classify_record(distilled2)["positive"] is True

        promotion = evaluate_case([distilled1, distilled2])
        assert promotion["promotable"] is True
        assert promotion["candidate_iteration"] == 2
        assert promotion["candidate_source_lineage"]["source_accepted_iteration"] == 1
        manifest = build_promotion_manifest(evaluation=promotion, previous_golden=None, version="provider-neutral-golden-v1")
        assert manifest["immutable"] is True
        assert manifest["source_lineage"]["source_layout"] == str(layout1.resolve())

        broken = deepcopy(distilled2)
        broken["source_layout"] = None
        rejected = evaluate_case([distilled1, broken])
        assert rejected["promotable"] is False
        assert "source_layout_missing" in rejected["evaluations"][-1]["reasons"]


if __name__ == "__main__":
    test_provider_neutral_control_plane_completes_one_asset_resume_round_and_promotes_only_reproducible_history()
    print("Provider-neutral Astra full-loop integration test passed")
