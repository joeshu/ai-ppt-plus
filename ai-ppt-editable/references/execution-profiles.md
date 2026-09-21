# Execution profiles

Use `fast` by default for a normal single-page image-to-editable-PPTX job. It permits one initial candidate and one batched repair, at most two full renders, one ImageGen retry per failed asset, and 3–5 high-risk same-coordinate crops cut from the final full-page render.

Use `strict` when the user requests strict release evidence or the page is unusually dense. It permits one initial candidate plus two repair candidates, at most four full renders including exact-final confirmation, two ImageGen retries per failed asset, and 5–10 crops.

Use `ci` only for package regression and developer checks; it is not a delivery profile.

Run finalization preflight in `prebuild` stage before ImageGen or candidate construction. Formal text remains native in every profile. In `fast`, preflight every high-risk text slot: long or mixed-script titles, tables, metric lines, compact labels/buttons, and any slot close to its measured capacity. Low-risk short text uses the role style plus the final render.

Targets of 8–12 minutes to first visual render and 15–20 minutes total are benchmark goals, not acceptance gates. Correctness blockers remain separate from diagnostics.

Every production run records: time to first visual render (TTFVR), total wall time, candidate/render/ImageGen counts, native-text coverage, required-native coverage, whole-slide raster count, unresolved material mismatches, protected regressions, and reproducibility. Time targets remain diagnostic; required-native coverage, zero whole-slide rasters, zero protected regressions, and reproducibility are correctness gates.

`run_super_pipeline.py` owns profile selection. It validates the canonical profile and runs an execution-budget preflight before visual validation or candidate construction. The preflight reads `imagegen-assets-manifest.json`, excludes verified cache hits, derives retries from `retry_count` or generation attempts, and blocks over-budget work. It passes the observed generation count and candidate count into editable QA; the performance report derives TTFVR from the render node's dependency path.
