# Regression and revision contract

Use this contract whenever a prior case is rerun, the same source is
reuploaded, or a repair is performed after a passing artifact.

## Baseline freeze

Use `scripts/revision_guard.py freeze` to create a self-contained baseline
archive. The archive must contain the authoritative PPTX, the source/reference
image, the preview rendered from that exact PPTX, the relevant manifests and
quality reports, and SHA-256 evidence for every copied artifact.

The freeze operation is no-overwrite: an existing target directory is a
blocker. Runtime decks, source images, generated assets and fonts remain
artifacts of the case; they must not be copied into the skill's source code
commit merely because they are included in a local baseline archive.

Record the accepted revision, source case, excluded experimental revisions and
known open issues in `baseline-manifest.json`. A baseline can be technical-
validated while still requiring human closeout; do not convert that state into
`delivered` without the required closeout evidence.

## Required behavior for a new revision

1. Compute the input/reference hash and record it in the current route and
   source inventory.
2. Allocate a new revision identifier and a new output directory that does
   not already exist. An existing run directory is a blocker, not a cache to
   overwrite.
3. Generate an immutable PPTX filename containing the revision and date or
   content hash. Do not write over an earlier PPTX.
4. After generation, compute the PPTX SHA-256 and update project state and
   handoff to that exact file and hash.
5. Render that exact PPTX into the new run directory. Do not copy or relink a
   preview from an earlier run.
6. Run artifact consistency checks with the current PPTX, current render,
   current render report and current project state. The report index must point
   to the current run.
7. Record inherited issues as `carried_forward`, `fixed` or `reopened`; do not
   silently leave old `open` states in a new revision.

## Failure conditions

- Same-filename replacement or reuse of a prior render directory.
- A report, preview, handoff or project state pointing to a different revision.
- A PPTX hash that differs from the hash in project state or handoff.
- A successful technical gate achieved using stale render output.
- A baseline artifact whose recorded SHA-256 or size no longer matches.

An identical input hash does not make the output interchangeable: revision
identity is part of the evidence chain.
