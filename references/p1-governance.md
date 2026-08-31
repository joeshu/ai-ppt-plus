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
