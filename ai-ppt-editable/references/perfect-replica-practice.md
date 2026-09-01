# Perfect-replica practice protocol

This protocol keeps `ai-ppt-editable` anchored to the frozen
`完美第一版` while allowing narrowly scoped improvements in portability and
quality gates. The goal is a repeatable repair loop, not a one-off green
report.

## Contract

- Source of truth: `joeshu/ai-ppt-plus`, ref `完美第一版`, commit
  `d5dec0588fe87581112cbe1498ad4dac44f402e4`.
- Baseline files are checked by `assets/upstream-perfect-sync.json`.
- Post-baseline adapters are enumerated in that manifest. They may normalize
  paths or connect existing modules, but must not introduce a second rendering
  or reconstruction engine.
- Every repair records the owning layer, input/reference hashes, affected
  slides or regions, and the resulting render and validation reports.

## Repeatable loop

1. **Freeze inputs.** Create a unique run directory, preserve the source and
   any prior deck, record SHA-256 values, and run the environment doctor before
   the first reconstruction build.
2. **Verify the baseline.** Run the package validator, routing validator, and
   perfect-source validator. When the source checkout is available, add
   `--source-dir ... --require-source`.
3. **Plan independently.** Decide the route before composition. For a fixed
   reference, keep the reference authoritative; inventory background, frame,
   panels, icons, formal text, charts, and page furniture with bboxes and
   provenance.
4. **Compose strictly.** Use `compose_pptx.py --strict-input`, retain native
   text/shapes/tables/charts where their semantics are known, and keep panels
   and decorative assets independently movable. Pass an explicit font
   directory and embed fonts when delivery requires it.
5. **Calibrate typography.** Measure prominent title/body masks against the
   source and record `typography-calibration.json`. Do not accept a good global
   SSIM score as proof that text metrics are correct.
6. **Render from the declared final backend.** Render every page with
   `render_pptx.py`, compare against the authoritative reference, and compare
   the authoring preview with the final render.
7. **Run the full DAG.** Require route, CJK/font evidence, source and asset
   hashes, object and text manifests, independent panels, icon/imagegen
   evidence, manifest registry, typography calibration, preview consistency,
   and pixel plus semantic dual comparison as applicable.
8. **Repair the owner.** Classify each failure as path/asset/font/text/layout/
   object/provenance/registry. Fix that layer, rerun affected checks, then run
   a full-deck validation after the repair batch. Never repair by changing
   approved copy or redesigning the reference.
9. **Distill the regression.** Add a small deterministic fixture or test for
   every reusable fix. Keep the practice deck and reports outside the skill
   package unless they are intentionally promoted as a golden fixture.

## Exit criteria

A practice run is technically complete only when:

- the package, routing, source-sync, structural, font, asset, object, text,
  registry, render, preview, and dual-comparison gates pass;
- the final report bundle is fresh and bound to the current deck hash;
- the full-deck visual metrics are recorded with their renderer and DPI;
- `human_visual_review_required` remains true whenever visual or formal-content
  confirmation is still needed; technical pass must not be promoted to human
  approval or release eligibility;
- known unresolved copy such as a literal `**元` mask remains explicitly
  listed for human closeout rather than silently normalized.

## R1 reference rehearsal

The representative one-page rehearsal is
`image2pptx_runs/baselines/R1_20260828_53_5`. It exercises a Chinese CJK
reference, a photographic background, six independent panels, ten extracted
icons/illustrations, native formal text, embedded `Noto Sans CJK SC`, and a
full manifest registry. The expected rehearsal profile is:

- 1 page at 16:9;
- 44 audited objects, 25 native formal-text boxes, 6 independent panels;
- typography calibration max relative drift no greater than `0.12`;
- preview/final-render blurred-layout SSIM at least `0.90` when that threshold
  is declared;
- visual comparison remains diagnostic and human-reviewable even after the
  technical gate passes.

This rehearsal is intentionally run more than once: first to expose stale
paths or evidence, then after refreshing hashes and registry bindings. A later
run must use the same input hashes and must not inherit an old deck or report
hash merely because the filenames match.
