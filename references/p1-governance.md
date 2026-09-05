# Root P1 reinforcement

P1 builds on the P0 contracts without changing route ownership or formal-text
authority.

- `scripts/pipeline_engine.py` uses code/runtime fingerprints, output hashes,
  per-key locks and recoverable quarantine for corrupt cache entries.
- `scripts/validate_design_system.py` checks the deck-wide canvas, grid,
  typography, contrast, tokens, approval and cross-artifact revision binding.
- `scripts/validate_issue_log.py` requires a structured trigger → root cause →
  fix → regression-test record; strict mode blocks unresolved issues.
- `pipeline-checkpoint.json` is written atomically during DAG execution and
  records completed/remaining tasks, fingerprints and cache decisions.
- `scripts/build_review_package.py` creates a portable, hash-indexed package
  containing the review HTML, reports, checkpoint and rendered pages.

Use `--require-p1` on `scripts/run_pipeline.py` when a project is ready to
enforce P0 plus the P1 design-system and issue-log contracts. The review
package can also be generated independently from any final
`pipeline-result.json`.

P1 does not restore removed WPS/iPhone or cross-platform rendering gates, does
not weaken the immutable R13 baseline, and does not allow generated visual
text to override formal copy.

## Performance and dual comparison

`performance-report.json` is the normalized operational record for a run. It
keeps wall duration, sum of task durations, DAG critical path, task/page cache
hit rates, retries and issue-log-derived repair rounds separate. A cache reuse
is not a repair round; a repair round requires a fix followed by re-render and
re-validation.

`dual-comparison.json` joins the existing per-page pixel comparison with the
semantic object audit. Its pixel axis compares the approved reference image to
the final PPTX render. Its object axis compares the reference-derived
`slide-object-manifest.json` to the actual PPTX object tree. The flattened
image object's count is never used as evidence of editability. Pixel and
object results remain separate, and either axis can block a strict run.

## Strict reference-reconstruction gates

When `--require-p1`, `--require-root-p0` or `--release` is used on the
`reference-reconstruction` route, the visual gate records the named
`reference-reconstruction-p1` policy and enforces the P1 floor of
`blurred_layout_ssim >= 0.90`. A comparison report without the recorded
threshold, policy or observed worst-page metric cannot satisfy the project or
delivery gate. The metric is a blocker signal, not a replacement for human
visual review.

`validate_canvas_evidence.py` checks the reference and rendered page sets and
their raw pixel dimensions before any diagnostic resize. `--exact-canvas` is
release-safe only when the report is `passed` and `exact_canvas` is true. If an
image service returns a different canvas, the only allowed continuation is an
explicit `canvas-degradation/v1` record containing the service, reason,
requested and observed canvases, fallback mode and timestamp. Such a run is
marked `degraded`, carries a human-review degradation, and remains ineligible
for strict release.

OCR is a readback aid, never formal-copy authority. Reference runs request the
configured OCR language (default `chi_sim+eng` for CJK-sensitive work); when
the language package or OCR binary is unavailable the report records
`unavailable` and the pipeline carries a human-review degradation. Use
`--require-ocr` when the release policy requires machine OCR evidence.

`validate_host_validation.py` is the final Office/WPS closeout contract. It
binds the evidence to the delivered PPTX hash, requires full slide coverage,
opening/layout/typography/overflow/editability/visual-fidelity checks and, in
strict mode, a PowerPoint or WPS host plus hash-bound screenshots per slide.
The validator records evidence; it does not pretend that Linux/LibreOffice
can simulate an Office/WPS review.
