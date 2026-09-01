# Automatic training driver

The fourth batch adds an execution boundary for the distillation loop:
`scripts/run_training_cycle.py`. It is designed to run from GitHub Actions or
another trusted scheduler and produces one `distillation-training-cycle/v1`
report per invocation.

## What the driver does

1. Looks for the configured case registry. Missing input is reported as
   `skipped`, not mistaken for a successful training run.
2. Waits for explicit human approvals. A registry with no eligible candidate is
   `waiting-human-approval`.
3. Calls `scripts/training_export.py export`, which rechecks all artifact
   hashes, deduplicates source groups, and writes the retrieval-ready JSONL
   plus manifest.
4. Builds a dependency-free CPU retrieval index and checks that source hashes
   do not leak across train/validation/test splits. This is immediately
   runnable without a GPU, but it is not semantic embedding or weight
   training.
5. Optionally invokes a trusted external trainer through `--trainer-command`
   or `AI_PPT_TRAINER_COMMAND`. The dataset manifest and JSONL paths are passed
   through `AI_PPT_DATASET_MANIFEST` and `AI_PPT_DATASET_RECORDS`.
6. Records a `prepared` or `trained-candidate` state. Even a passing trainer
   remains `release_eligible: false` and `pending-human-approval`.

The command is intentionally not a model trainer. A model-specific adapter
must define tokenization/structured labels, GPU or queue selection, checkpoint
storage, evaluation, rollback, and model registry policy. Until that adapter
exists, the driver prepares auditable data and exits successfully with
`code: trainer-not-configured` (or blocks when `--require-trainer` is used).

## Repository contract

The GitHub Actions workflow uses this default registry path:
`datasets/ai-ppt-editable/cases.json`. Registry artifact paths may be absolute
or relative to the registry directory. Large source images and PPTX files can
be supplied by a controlled artifact/download step before the driver runs;
their SHA-256 values must still be present in the registry.

The workflow has read-only repository permission and uploads the cycle report,
JSONL, manifest, and materialized artifacts as a build artifact. It does not
write to `main`, auto-approve cases, promote weights, or silently retrain on
unreviewed material.

## Suggested operating cadence

- on a new approved-case commit: prepare a new dataset;
- on a scheduled run: revalidate hashes and report waiting/blocked states;
- after the trainer adapter is installed: run manually with
  `--require-trainer`, then compare the candidate model on a held-out test
  split;
- only after independent evaluation and human sign-off: publish a model
  version and update retrieval indexes.

This makes the driver the automation owner, while keeping the training
algorithm and promotion decision explicit and replaceable.
