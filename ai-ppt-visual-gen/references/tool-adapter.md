# Tool adapter contract

`scripts/tool_adapter.py` is the single boundary for runtime discovery and
external commands. It accepts only absolute existing runtime candidates,
normalizes inputs against a known project directory and confines outputs to a
run staging directory or `deliverables/`. Commands are argv lists with
`shell=False`, bounded timeouts and at most two retries for classified
transient/idempotent failures. Content, OOXML and output-conflict failures are
never blindly retried.

For every Python-backed preflight (source inspection, font discovery, font
asset validation and CairoSVG capability probing), invoke the Python executable
resolved by this adapter, never a bare `python` found on `PATH`. Persist that
executable's absolute path, version and required-package availability in the
run report. If the resolved runtime lacks a required capability, block the
stage instead of retrying under a different interpreter. This keeps runtime
fingerprints deterministic and prevents false unreadable-source or missing-font
reports.

Before authoring, callers validate finite geometry, non-negative dimensions,
colors and enum values, then preload every binary asset and record its SHA.
Promotion refuses an existing destination, so finalizer output conflicts are
visible and cannot create an unexplained `-r2` artifact. Each command record
contains phase, tool, input digest, duration, exit code, error class, retry
count and output hashes.
