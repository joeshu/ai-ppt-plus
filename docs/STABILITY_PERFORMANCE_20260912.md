# Stability and performance enhancement report

## Scope and immutable baseline

The candidate starts from `main` commit
`7d5f3c2339acca9497b19c0c24de93052b8c8494` and changes only the independent
branch `codex/stability-performance-engine-20260912`. The package revision is
advanced from `2026.09.12.02` to `2026.09.12.03` across all three entrypoints.
No quality threshold, visual metric, authoring backend, editable-object rule,
Golden decision or Hard Negative policy was changed.

## Bottleneck and critical-path diagnosis

The existing engine already had atomic cache publication, per-key locks,
runtime/code fingerprints, corrupt-cache quarantine and DAG execution. The
remaining reliability gap was that `pipeline-checkpoint.json` recorded task
names but could not safely resume them. An existing output directory was also
rejected unconditionally. The remaining performance gaps were run-directory
strings embedded in compound arguments (preventing cross-run cache hits), a
fixed worker count, and incomplete scheduler/cache/retry telemetry.

## Changes

- `pipeline-checkpoint/v2` binds completed nodes to engine, code, runtime,
  cache key and declared-output hashes, and stores the complete node result.
- `--resume` restores only verified successful nodes. Missing, changed or
  corrupt outputs are recomputed. Failed nodes are never restored as success.
- Task-local retries are finite and error-class constrained. Deterministic
  command/quality failures remain non-retryable by default.
- Cache keys normalize an embedded run-directory prefix, fixing false misses
  for inline commands while retaining all input/code/runtime fingerprints.
- `--parallel-workers 0` selects a bounded CPU-aware limit; explicit values
  remain available for reproducible runs.
- Performance reports now expose resume hits, scheduler idle capacity, output
  and temporary bytes, external-call counters and explicit unavailable
  resource fields rather than silently emitting zero.
- Root and standalone `ai-ppt-editable` adapters carry the same recovery
  behavior. Runtime Mirror and Perfect Sync remain passing.

## Results

| Measure | Before | After | Result |
|---|---:|---:|---|
| Root regression | 74/74 | 75/75 | Passed |
| Cold wall median | 17.529 s | 17.329 s | 1.14% faster |
| Engine hot start | baseline | 97.49% lower | Target met |
| One-page incremental | baseline | 66.83% lower | Target met |
| Unchanged-page cache hit rate | baseline | 80% | Target met |
| Forced termination recovery | unavailable | 1 verified node resumed | Passed |
| Runtime Mirror / Perfect Sync | passed | passed | No regression |

The synthetic engine benchmark is repeated three times with identical inputs
and configuration. It exercises real subprocess nodes, cache publication,
one-page input mutation and forced process termination. Raw reports are under
`artifacts/performance/`.

## Risks and blocked evidence

The managed runtime denies `/proc/<pid>/statm` and `/proc/<pid>/io`, and its
process namespace is not stably visible through `ps`. Peak RSS and disk I/O
therefore remain unavailable rather than being represented as zero. In
addition, base PR #34 deliberately removed the retired 12-case binary replay
assets, preventing a fresh full-pixel comparison of those historical cases.
The repository owner explicitly accepted both limitations on 2026-09-12.
They are retained as visible evidence limitations rather than hidden or
represented as successful measurements. The final verdict is therefore
**PASSED WITH ACCEPTED LIMITATIONS**. This human acceptance does not change
any visual threshold, quality gate, authoring rule or Golden policy.

## Rollback

The change is isolated to one branch. Roll back by not merging it, or revert
its single optimization commit after merge. Cache schema/engine versioning
causes older entries to miss safely; no migration or deletion is required.
