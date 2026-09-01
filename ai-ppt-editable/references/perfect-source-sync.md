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

The excluded paths are intentional package-boundary files: the standalone
entrypoint, package/routing validators, the current orchestrator integration
adapters, and a small set of post-baseline compatibility or correctness tests.
`scripts/component_expander.py` and `scripts/compose_pptx.py` are the two
explicit post-baseline adapters: they preserve the baseline algorithms while
making layout-relative assets and explicit font directories work from an
arbitrary caller directory. They must not contain a second reconstruction
engine. Any change to the synchronized list or adapter set requires a refreshed
manifest and a passing full worker test run. The repeatable practice protocol
is in `references/perfect-replica-practice.md`.
