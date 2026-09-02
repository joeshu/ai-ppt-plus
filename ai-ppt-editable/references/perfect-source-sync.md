# Perfect-source synchronization contract

`ai-ppt-editable` is an independently runnable worker package, but its
reconstruction engine and shared QA contracts are vendored from the
`完美第一版` snapshot of `joeshu/ai-ppt-plus`.

The pinned source is:

- repository: `joeshu/ai-ppt-plus`
- ref: `完美第一版`
- commit: `d5dec0588fe87581112cbe1498ad4dac44f402e4`

The byte-parity list is recorded in
`assets/upstream-perfect-sync.json`. Validate it before using or publishing the
worker:

```bash
python3 scripts/validate_perfect_sync.py
```

When a checkout of the source ref is available, validate both sides:

```bash
python3 scripts/validate_perfect_sync.py \
  --source-dir /path/to/ai-ppt-plus-perfect \
  --require-source
```

The excluded paths are intentional package-boundary files, post-baseline
adapters, and their regression tests. The validator skips parity comparison for
those paths but still requires the local target to exist; the package validator
and focused tests remain responsible for their integrity. Exclusions must not
contain a second reconstruction engine. Any new exclusion requires a reason,
a manifest update and a passing full worker test run.
