# Pipeline performance contract

## Execution graph

The verification runner is a DAG, not a required linear chain. Source and
manifest checks can run independently; render-dependent checks wait for the
render node; project validation waits for the technical evidence it consumes.
The graph is declared in `scripts/run_pipeline.py` and executed by
`scripts/pipeline_engine.py`.

The executor keeps one bounded thread pool alive across all ready-task waves.
This avoids repeatedly constructing and tearing down pools on the large
validation graph while preserving the same dependency barriers and stable
result ordering.

`--execution-mode dag` is the default. `--execution-mode linear` keeps the same
commands and output contract with one worker and no cache, which is useful for
diagnosing an ordering-sensitive environment. A dependency failure blocks
downstream nodes and records `failure: dependency_failed`; it is never silently
skipped as a pass.

## Cache contract

Only successful tasks with declared outputs are cached. The key includes:

- engine version and task name;
- normalized command arguments and the command script SHA-256;
- every declared file/directory input and its content hash;
- task configuration such as DPI, selected pages and required gates.

Artifacts are copied into the cache and restored into each new immutable run
directory. The cache never reuses a run directory, report index or PPTX path.
Failed or incomplete outputs are not cached. Use `--cache-dir PATH` to choose a
cache location or `--no-cache` for a clean run.

## Fast reconstruction profile

Reference reconstruction should spend model time only where it changes the
result. Inventory all visual assets once, then use `source_reuse` for complete
authoritative pixels and reserve imagegen for missing, ambiguous or genuinely
reconstructive visuals. The provenance validator accepts both modes, so this
optimization does not remove the evidence gate.

Use a two-pass loop: first run cheap source, manifest, text, layout and targeted
region checks; then render only affected pages/regions with `--affected-pages`
and `--affected-region`. Run the full-deck render and release bundle once at
the end. Do not use `--no-cache` for ordinary repair iterations: it disables
both task and page caches and is reserved for clean-environment verification.
Batch related typography/layout changes before a render so each repair round
has one render/compare cycle. A stage budget should emit a recorded degradation
or blocker rather than silently retrying expensive generation.

For a reference-reconstruction route, `run_pipeline.py` requires
`typography-calibration.json` before it starts the render graph. A missing
manifest therefore fails fast; a measured font-metric drift fails the
calibration gate. This saves a full render on an incomplete repair and makes
the WPS/PowerPoint typography regression explicit instead of hiding it in a
global similarity score.

## Chart fast path

Charts are a frequent source of long, low-value repair loops. First create one
chart manifest from the source hash and chart crops; run OCR/readback for the
three crops concurrently; and cache the canonical data/style records. If no
authoritative workbook or approved table exists, stop trying native chart
variants and route directly to `static_line_primitives` (or an explicit
`raster_fallback` for a chart whose geometry is not recoverable). This keeps
the visual result editable without inventing data.

During chart repair, pass the affected page and chart region to the pipeline,
validate the chart manifest and visible-content inventory before rendering,
and render only the affected page. Batch line/marker, label and spacing fixes
into one iteration. Reserve one full-deck render, font embedding and report
bundle for release. The chart manifest is content-addressed by source/data
hash, so a typography-only retry does not repeat chart extraction.

## Page and region scope

`--affected-pages 1,3-4` makes the renderer emit only those pages and passes the
same selection to render validation, deck comparison and OCR. `--affected-region
name=x,y,w,h` adds a critical pixel region to the render QA gate. Results record
the page/region scope and set `validation_scope: incremental`; a full release
run must omit `--affected-pages`.

### Page artifact cache

The DAG runner passes a stable page cache directory to `render_pptx.py`; the
default is `.pipeline-cache/render-pages`, and `--page-cache-dir PATH` overrides
it. The renderer fingerprints pages in presentation order from their slide XML,
relationship closure and referenced assets, plus shared presentation,
theme/master/layout and content-type parts. The cache namespace also includes
the DPI, renderer contract version and task-local font-directory digest.

Each cached PNG is decoded before use and written atomically. A corrupt or
missing entry is treated as a miss. If every requested page is a valid hit,
LibreOffice and Poppler are skipped. If only some pages miss, LibreOffice may
still convert the whole deck to PDF, but Poppler rasterizes only the missing
pages and preserves the restored images. The render report records
`page_fingerprints`, `page_cache.hits/misses/stored` and
`conversion.attempted/skipped`; this is artifact reuse evidence, not human
visual approval.

`--no-cache` disables both the task cache and page artifact cache. A linear run
does not enable the default page cache; pass `--page-cache-dir` explicitly if a
linear diagnostic run should reuse page artifacts.

## Measurement

Each step records `deps`, `duration_ms`, `cache_key` and `cache_hit`. The
pipeline result records total task count, cache hits, cache misses, worker
count, wall duration, critical-path duration and selected scope. Sum of step
durations is diagnostic; wall-clock improvement also depends on the number of
independent nodes and external renderer contention. Test reports likewise
retain both summed subprocess time and wall-clock time.

## Regression and runtime gates

The repository test runner executes independent executable tests concurrently
while preserving sorted report order:

```bash
python3 scripts/run_tests.py --parallel-workers 4 --report test-report.json
```

The worker packages use the same runner. A bounded subprocess timeout,
durable stdout/stderr and each test's duration are retained in the report, so a
slow renderer is visible instead of looking like a hung pipeline. Before a
full run, validate the
checked-in capability contract and shared-runtime hashes:

```bash
python3 scripts/probe_environment.py --output environment-report.json
python3 scripts/validate_environment_contract.py --report environment-report.json
python3 scripts/validate_runtime_mirror.py
```

These checks are cheap and should remain ahead of model generation or PPTX
rendering in CI.
