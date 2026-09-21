# Incremental reconstruction protocol

The root skill owns one resumable A–O control plane. The two worker skills
remain responsible for their existing authoring and visual-generation gates.
The protocol saves a checkpoint after each stage using
`scripts/incremental_orchestrator.py`; it never changes the requested
editability target to gain speed.
The source roster uses `assets/schemas/source-manifest.schema.json`; the
checkpoint uses `assets/schemas/incremental-checkpoint.schema.json`.

| Stage | Inputs → outputs | Preconditions and success | Retry/cache/parallel | Recovery |
|---|---|---|---|---|
| A repository_preflight | repository → repository report | main SHA, branch and clean-change inventory recorded | cacheable, serial, no retry | recheck SHA and branch |
| B input_discovery | attachments → ordered input roster | every page has one unambiguous source | bounded lookup, serial | rerun with same page order |
| C source_manifest | roster → source manifest | dimensions, format and SHA recorded | cacheable, page-parallel | reuse when input hashes match |
| D skill_contract_load | package revision → contract snapshot | all required references and validators resolve | cacheable, serial | reload pinned package |
| E reference_analysis | source manifest → analysis | layout, text and asset regions are traceable | idempotent, page-parallel | invalidate affected pages |
| F font_preflight | font files → font report | CJK, weights and actual smoke evidence pass | cacheable, read-only parallel | rerun on font SHA change |
| G asset_preparation | analysis/fonts → asset manifest | binary assets preload and hashes bind | idempotent, page-parallel | invalidate dependent pages |
| H artifact_marker | contract → marker receipt | marker runs once per run and succeeds | never cached or parallel | never repeat a passed marker |
| I native_authoring | manifests/fonts/assets → intermediate PPTX and inventory | JS ESM + `@oai/artifact-tool`, native object rules pass | serial write, content errors fail | resume from last valid source |
| J fast_render | intermediate PPTX → fast render | page count and geometry are valid | cacheable, page-parallel, transient retry | rerender affected pages |
| K visual_refinement | render/analysis → refined PPTX | visual checks pass without deleting detail | human decision, serial write | resume at page/region |
| L finalizer | refined PPTX → finalizer receipt | staging → validate → promote and no output conflict | serial, no blind retry | choose a new output name |
| M final_render | exact final SHA → final render | rendered file hash equals promoted file | cacheable, page-parallel | render exact final hash |
| N technical_audit | final/render → audit report | package, OOXML, layout, fonts and editability pass | read-only parallel | rerun when final SHA changes |
| O package_delivery | audit/final → delivery report | all gates and evidence are fresh | serial, no retry | keep delivery blocked |

Every stage records inputs, outputs and SHA-256, duration, failure class,
retry count and a recovery command. The checkpoint also records the repository
SHA, package revision, input/font hashes, marker status, build-source SHA,
intermediate/final PPTX SHA and completed validations. Resume first compares
these values with disk. A changed input invalidates that stage and all
downstream stages; unchanged successful OCR, font scans, normalization and
page renders stay reusable. A changed final output always invalidates M–O.

The following quality rules are hard gates:

- MUST author with JavaScript ES modules and `@oai/artifact-tool`.
- MUST keep formal text, tables, connectors, arrows, diagrams, icons and
  containers native and editable.
- MUST use staging, validation and explicit promotion for final files.
- MUST run finalizer, final render and full technical audit before delivery.
- MUST preserve the same or higher baseline quality for every active case.
- MUST attach a hash-bound visual comparison before K can pass and before O can
  deliver a reference reconstruction. The balanced
  `reference_fidelity_score` combines blurred layout SSIM and blurred color
  fidelity, but remains diagnostic unless the user explicitly supplied a
  numeric acceptance target. Rank material regions and close observable
  mismatches; do not keep generating candidates to chase a default threshold.
  Keep raw pixel fidelity as a diagnostic because font antialiasing is
  viewer-sensitive.
- MUST report missing Artifact Tool, renderer, font evidence or human review as
  an upstream limitation rather than claiming success.
- MUST NOT use `python-pptx` to create, rewrite or repair a PPTX.
- MUST NOT use full-page screenshots, SVG, canvas, PDF or raster text as a
  substitute for editable objects.
- MUST NOT widen tolerances, delete evidence, skip a gate or overwrite a
  validated deliverable to improve timing.

The optimization metrics use wall time, task-time sum, cache hit rate,
automatic retries, repair rounds, skipped safe stages and final full-deck
validation time. A faster run with a quality regression is a failed run.
