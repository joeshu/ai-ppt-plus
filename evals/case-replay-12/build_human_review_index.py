#!/usr/bin/env python3
"""Create the reviewer-facing per-case admission checklist."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    evaluation = json.loads((ROOT / "candidate-evaluation.json").read_text(encoding="utf-8"))
    rows = []
    for case in evaluation["cases"]:
        candidate = case["candidate"]
        score = candidate.get("visual", {}).get("metrics", {}).get("pixel_fidelity_score")
        rows.append({
            "case_id": case["case_id"],
            "title": case["title"],
            "reference": candidate.get("reference"),
            "candidate_deck": candidate.get("deck"),
            "candidate_render": candidate.get("rendered"),
            "pre_fix_technical_status": case["pre_fix"].get("technical_status"),
            "candidate_technical_status": candidate.get("technical_status"),
            "visual_pixel_fidelity_score": score,
            "native_tables": candidate.get("objects", {}).get("native_table_count", 0),
            "exact_a_tbl": candidate.get("objects", {}).get("a_tbl_count", 0),
            "formal_text_native_ratio": round(candidate.get("objects", {}).get("formal_text_native_count", 0) / max(1, candidate.get("objects", {}).get("formal_text_count", 0)), 6),
            "mutation_smoke": bool(candidate.get("mutation_smoke", {}).get("pixel_change", {}).get("changed")),
            "automatic_case_library_admission": False,
            "human_visual_review": "pending",
            "review_note": "技术门禁通过；请对照 reference 与 candidate_render 判断视觉保真。" if isinstance(score, (int, float)) and score >= 0.8 else "技术门禁通过但视觉差异较大；暂不建议直接纳入 golden case library。",
        })
    report = {
        "schema": "ai-ppt-plus/human-review-index/v1",
        "suite_id": evaluation["suite_id"],
        "case_count": len(rows),
        "automatic_case_library_admission": False,
        "human_visual_review_required": True,
        "cases": rows,
    }
    output = ROOT / "qa" / "human-review-index.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "output": "qa/human-review-index.json"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
