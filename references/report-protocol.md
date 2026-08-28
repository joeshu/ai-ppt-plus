# Project report protocol

The project-level report is the authoritative technical roll-up. Child reports
may retain their native detail and historical schemas, but they must be listed
in `report-index.json` and normalized into `report-envelope/v1` by
`aggregate_project_reports.py`.

## Registry

`report-index.json` records `project_id`, `revision`, `stage`, the deck path and
hash, and every expected report:

```json
{
  "schema": "ai-ppt-plus/report-index/v1",
  "project_id": "month-end-closeout",
  "revision": "R4",
  "stage": "validated",
  "validation_scope": "full",
  "deck_path": "deck.pptx",
  "deck_sha256": "...",
  "source_references": [],
  "reports": [
    {"report_type": "inspection", "path": "inspection.json", "required": true, "stage": "validated"}
  ]
}
```

`required: true` means missing, unreadable or failed reports block the project.
Optional missing reports produce a `degraded` aggregate and remain visible in
evidence. The pipeline records the actual step result as `step_ok` when an old
child report has no `valid` or `ok` field; this compatibility path never turns
a missing file into a pass.

## Envelope

`project-report.json` uses `ai-ppt-plus/report-envelope/v1` and always exposes:

- identity: `project_id`, `revision`, `stage`, `report_type`;
- truth: `valid`, `status`, `technical_valid`, `issues`, `next_state`;
- freshness: `deck_sha256`, `report_index_sha256`, `input_hashes`;
- audit: `generated_at`, `tool`, `reports_total` and per-report evidence;
- source: `source_references` and per-report `source.path`/`source.sha256`;
- honesty: `human_review_required`, `human_review_status`, `release_eligible`,
  `requires_human_closeout` and `may_claim_complete`.

`status` is `passed`, `degraded` or `failed`. `valid: true` means no required
technical gate failed; it does not mean the human closeout is complete.

Run:

```bash
python scripts/aggregate_project_reports.py report-index.json \
  --report project-report.json
```

Every downstream project or delivery report must consume this aggregate or
explicitly state why it is unavailable. A report with a stale deck hash, stale
index hash, missing required child, or hidden child blocker cannot be used to
claim delivery.

## Bundle freshness gate

The runner writes a provisional `pipeline-result.json` after aggregation and
then runs `validate_report_bundle.py`. The resulting
`report-bundle-validation.json` is a meta-gate (it is intentionally not added
as an indexed child, which would create a self-referential aggregate). It
checks that:

- the pipeline result, report index, aggregate and current PPTX share one
  fresh deck SHA-256;
- the aggregate's report-index hash and every child/source/input hash are
  current;
- `full` versus `incremental`, affected pages and full-deck requirements agree;
- failed steps and technical failed steps are complete and not hidden; and
- deck/source references and the generated review status are present and
  consistent when the HTML path is supplied.

Run it directly for a previously generated run:

```bash
python scripts/validate_report_bundle.py pipeline-result.json \
  --report-index report-index.json \
  --project-report project-report.json \
  --deck deck.pptx \
  --review-html review.html \
  --report report-bundle-validation.json
```

`--require-full` makes an incremental bundle fail. The gate only establishes
technical evidence freshness; it never supplies human sign-off or release
eligibility.

The normalized status vocabulary is deliberately separate from a child report's
native status: `passed`, `degraded`, `failed`, `needs-human-review`, `invalid`,
or `missing`. A technical pass still has `human_review_status: pending` and
`release_eligible: false` until the closeout and delivery gates explicitly pass.

Generate the project review page after a pipeline run with:

```bash
python scripts/render_review_html.py pipeline-result.json --output review.html
```

The page is an audit view, not a sign-off mechanism. It links rendered pages
and logs, shows cache/dependency evidence, and keeps technical, human, and
release states visually distinct.

For a release gate, pass `--project-report project-report.json
--require-project-report` to `validate_project.py` or `delivery_check.py`.
