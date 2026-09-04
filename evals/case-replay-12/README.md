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

Without `--candidate-root`, the runner emits synthetic native contract
controls so the object/audit machinery can still be exercised. They are
explicitly non-promotable and `--strict` must fail; this prevents a sparse
generic card layout from being mistaken for a reconstruction of the reference
image.

For an actual editable reconstruction, point the runner at a directory with
one candidate per case (`<case_id>.pptx` or `<case_id>/editable.pptx`) and its
`reference-reconstruction-evidence.json` plus layout/object/text manifests:

```bash
python evals/case-replay-12/run_replay_suite.py \
  --candidate-root PROJECT/optimized-candidates \
  --output-dir PROJECT/qa/case-replay-12 \
  --strict
```

`--strict` now requires native structure, mutation smoke, raw-slide visual
thresholds, reference hash binding, independent imagegen asset evidence,
source-bound typography/font evidence and exact formal text. It still does not
grant human visual approval.

## Evidence

- `baseline-evaluation.json`: the explicit legacy full-slide-image control,
  with source/reference hashes, render metrics and rasterized-object failures.
- `candidate-evaluation.json`: the 12-case replay result, including
  optimized-before/after results, native table/panel/text counts, exact
  OOXML `<a:tbl>` counts, merge topology, render metrics, visual-fidelity
  blockers and mutation evidence.
- `visual-fidelity-status.json`: the compact per-case visual gate summary;
  this is the quickest way to see whether an icon/illustration, typography or
  layout blocker remains.
- `case-improvement.json`: per-case deltas and the repair that changed the
  merge topology gate.
- `visual-generation-plan.json`, `outline/`, `prompts/`, and
  `visual-generation-manifest.json`: the visual-gen planning, prompt and
  retained-image chain.
- `runs/candidate/`: the 12 editable one-slide PPTX files and their rendered
  previews. `runs/candidate-before/` contains the pre-fix native controls.

The checked-in optimized decks are synthetic contract controls, not actual
reference reconstructions. They must remain blocked until regenerated through
the editable worker with source-bound text geometry and independent visual
assets. A reviewer must still compare each reference against its candidate
render and explicitly approve visual fidelity, formal copy and editability
before promotion.

If an older detailed JSON report still says that these controls passed, treat
it as historical fixture evidence and rerun the strict command; the compact
status file and the runner's fresh output are authoritative for this revision.

The separate `evals/case-replay-social-01/` package is the original
social-channel anchor. It verifies the five native tables, four policy-table
vertical merges, native panels/text, one permitted text-free full-slide asset,
visual thresholds, object comparison and mutation smoke.
