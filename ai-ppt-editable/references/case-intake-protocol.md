# Case intake protocol

The operator supplies only source files. `scripts/prepare_case.py` turns them
into a hash-bound, reviewable case without requiring JSON labels, scores, or
manifests from the operator.

## Accepted inputs

- One or more PNG, JPG, WebP, BMP, TIFF pages: visual reference for the normal
  image-to-editable-PPTX reconstruction route.
- A PPTX: canonical editable target. The intake command renders its pages into
  reference images when the local renderer is available, while preserving the
  original PPTX as the target artifact.
- Both image(s) and a PPTX: paired mode; images are visual input and the PPTX
  is the strongest editable target for comparison.

All files are copied into a case directory and SHA-256 bound. A PPTX render
failure is recorded as a visible pending status; it is never silently treated
as a successful reference.

## Minimal operator flow

```bash
python scripts/prepare_case.py --source /path/to/page-1.png --source /path/to/page-2.png --output-dir /path/to/cases
```

For a supplied PPTX, omit `--skip-render` so page images are generated:

```bash
python scripts/prepare_case.py --source /path/to/reference.pptx --output-dir /path/to/cases
```

After the reconstruction worker creates an editable candidate, add it to the
same case with `--candidate`. If the worker already produced fresh evidence,
copy it into the same immutable case in one pass:

```bash
python scripts/prepare_case.py \
  --source /path/to/page-1.png --output-dir /path/to/cases \
  --case-id CASE_ID --candidate /path/to/candidate.pptx \
  --candidate-score /path/to/score.json \
  --candidate-report /path/to/editable-object-audit.json \
  --profile perfect-first
```

The case remains `human-review-pending` until a person explicitly approves a
technically valid candidate through `training_export.py approve-case`. After
approval, `ingest_approved_case.py` can immediately run approval, export, and
CPU retrieval indexing as one auditable command; GitHub Actions can run the
same cycle on its scheduled/manual boundary.

The intake layer deliberately separates what the operator provided, what the
reconstruction produced, and what a human judged acceptable.
