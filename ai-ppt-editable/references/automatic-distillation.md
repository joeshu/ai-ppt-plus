# Automatic distillation loop

The three-round protocol is the reconstruction method. This document adds an
execution layer that makes repeated practice accumulate as reproducible skill
evidence.

## What is automatic

- `scripts/distillation_loop.py score` normalizes existing visual, dual,
  object, pipeline, and issue reports into five bounded dimensions:
  `visual_layout`, `pixel_fidelity`, `editability`, `technical`, and
  `provenance`.
- `score` also turns heterogeneous issue arrays into one feedback list with a
  stable owner layer: asset, font, text, layout, object, provenance, report,
  pipeline, or package.
- `gate` compares a candidate with the previous baseline, enforces per-metric
  regression tolerances, and returns either `promote_candidate` or
  `keep_previous_candidate`. A rejected candidate must never replace the
  previous baseline automatically.
- `record-case` stores source, deck, report, and score SHA-256 references in a
  case registry. The registry is the durable input to retrieval or later
  training export.

## Profiles and the Pareto boundary

Use `visual-best` when the reference match is the primary objective,
`editable-best` when native object semantics are primary, and `hybrid` for
ordinary delivery. Never collapse the two baselines into one scalar without
retaining the five component metrics. The weighted score is a ranking signal,
not proof of visual or semantic correctness.

## Safe learning policy

Technical acceptance is only `accept-for-human-review`; it is not approval or
release eligibility. A case may become training data only after human review,
stable source/deck/report hashes, and a closed issue log. Unreviewed or stale
artifacts remain evaluation-only. This prevents the loop from learning a bad
OCR transcription, an accidental redesign, or a flattened whole-slide image.

## Recommended batch progression

1. Build the case registry and feedback protocol (this batch).
2. Add automatic candidate branching and region-level repair proposals.
3. Add hard-example mining and a golden corpus across page types.
4. Export only approved cases to retrieval examples and supervised training
   records.
5. Evaluate a specialized structure/layout model offline before allowing it to
   influence production composition.

The controller is deliberately model-agnostic. Repeated runs improve the
skill immediately through deterministic rules, tests, and retrieval cases;
model-weight training is a later consumer of the approved registry, not an
implicit side effect of running a PPT job.
