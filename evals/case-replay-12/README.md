# 12-case visual → editable replay

This is the real case-level regression set for the `ai-ppt-plus` split. Each
case has a deliberately complex one-page visual reference produced through the
`ai-ppt-visual-gen` contract, followed by a native reconstruction through
`ai-ppt-editable`. The images are visual authority; `case-suite.json` is the
copy/data authority.

## Run

```bash
python evals/case-replay-12/run_replay_suite.py --strict
```

`--strict` is a technical gate. It requires all 12 reference replays, all 12
optimized native reconstructions, and all 12 mutation smoke tests to pass. It
does not grant human visual approval.

## Evidence

- `baseline-evaluation.json`: the explicit legacy full-slide-image control,
  with source/reference hashes, render metrics and rasterized-object failures.
- `candidate-evaluation.json`: the actual optimized 12-case replay, including
  optimized-before/after results, native table/panel/text counts, exact
  OOXML `<a:tbl>` counts, merge topology, render metrics and mutation evidence.
- `case-improvement.json`: per-case deltas and the repair that changed the
  merge topology gate.
- `visual-generation-plan.json`, `outline/`, `prompts/`, and
  `visual-generation-manifest.json`: the visual-gen planning, prompt and
  retained-image chain.
- `runs/candidate/`: the 12 editable one-slide PPTX files and their rendered
  previews. `runs/candidate-before/` contains the pre-fix native controls.

The optimized native decks are technically eligible for human review, not
automatically eligible for the golden case library. A reviewer must compare
each reference against its candidate render and explicitly approve visual
fidelity, formal copy and editability before promotion.

The separate `evals/case-replay-social-01/` package is the original
social-channel anchor. It verifies the five native tables, four policy-table
vertical merges, native panels/text, one permitted text-free full-slide asset,
visual thresholds, object comparison and mutation smoke.
