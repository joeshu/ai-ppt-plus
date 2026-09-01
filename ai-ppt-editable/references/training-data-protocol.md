# Approved-case training export

The third batch converts only explicitly human-confirmed cases into a
hash-bound JSONL dataset. It prepares retrieval augmentation and future
specialized-model training without claiming that model weights were updated.

## Approval

Run `scripts/training_export.py approve-case` only after a person has checked
visual fidelity, formal text, and editability. The command requires
`--human-confirmed`, an approver identity, and a non-empty note. It also
rechecks the candidate score and refuses technically invalid or blocker-bearing
cases. Machine pass, a pending review flag, or a filename alone cannot create
training eligibility.

## Export

Run `scripts/training_export.py export` with the case registry, JSONL output,
manifest output, and preferably `--materialize-dir`. The exporter:

- verifies source, deck, score, and report SHA-256 values;
- keeps one highest-scoring approved candidate per source hash group;
- assigns train/validation/test by case ID, so candidates from one case cannot
  leak across splits;
- stores approval and quality metrics with every example;
- rejects stale, duplicate, incomplete, or unapproved candidates;
- can copy artifacts to content-addressed paths for portable retrieval data.

`retrieval_ready` means the approved JSONL and referenced artifacts are
consistent. `supervised_training_ready` remains false because a later
model-specific adapter must convert object manifests and PPTX targets into the
training representation required by the chosen model.
