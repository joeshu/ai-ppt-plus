# Text Render Feedback Loop

Render feedback closes the gap between pre-authoring fit evidence and the fresh final render.

The loop is intentionally diagnostic. It does **not** create a whole-page scalar release gate. It binds each TextFit slot to its AuthoringPlan owner, captures the same normalized bbox from the immutable reference render and the fresh candidate render, and records object-scoped text-region evidence.

## What it measures

For each planned text object:

- same-coordinate reference/candidate crops;
- foreground-visible bbox and centroid inside the text slot;
- foreground coverage;
- candidate-vs-reference centroid drift;
- candidate-vs-reference visible-height scale drift;
- candidate-vs-reference coverage drift;
- the TextFit target/recommended size and hierarchy rank.

The foreground extractor estimates the local background from crop borders and measures pixels that depart from it. This is suitable for repair diagnosis, not OCR and not formal-text authority.

## Diagnostic classes

- `aligned`
- `position_drift`
- `scale_or_weight_drift`
- `hierarchy_drift`

Thresholds are review tolerances only. The report always declares `release_gate: false`.

## Command

```bash
python3 scripts/text_render_feedback.py \
  --text-fit-report PROJECT/text-fit-all-slots.json \
  --authoring-plan PROJECT/authoring-plan.json \
  --reference-render-dir PROJECT/reference-render \
  --candidate-render-dir PROJECT/fresh-render \
  --crop-dir PROJECT/qa/text-render-crops \
  --report PROJECT/text-render-feedback.json
```

## Repair binding

A drift record points back to one responsible text owner and suggests editable parameters only for that owner. Position drift prefers bbox/baseline/alignment. Scale or hierarchy drift prefers bbox/margins/line spacing/font size, with font shrink still last.

Batch 4 does not mutate the deck automatically. Its output is evidence for the existing Responsible Object Repair / Protected Repair workflow. Every accepted repair still requires a fresh render and protected-neighbor re-check.

## Acceptance

Regression must prove:

- same-coordinate crop capture;
- position drift detection;
- scale/coverage drift detection;
- hierarchy-drift classification for top hierarchy text when forced below its intended scale;
- aligned-path behavior;
- missing owner/render fail-closed behavior;
- root/worker mirror identity.
