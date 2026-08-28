# Pipeline performance contract

## Execution graph

The verification runner is a DAG, not a required linear chain. Source and
manifest checks can run independently; render-dependent checks wait for the
render node; project validation waits for the technical evidence it consumes.
The graph is declared in `scripts/run_pipeline.py` and executed by
`scripts/pipeline_engine.py`.

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
pipeline result records total task count, cache hits, worker count and selected
scope. Sum of step durations is diagnostic; wall-clock improvement also depends
on the number of independent nodes and external renderer contention.