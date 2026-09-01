# Candidate branching and region repair

The second automatic-distillation batch creates isolated repair plans from
machine feedback. It does not silently mutate the PPTX or the previous
baseline.

Run `scripts/candidate_controller.py propose` with one or more reports. Each
proposal contains a deterministic candidate ID, parent candidate, owner layer,
triggering error, slide/object/region/bbox context when available, bounded
mutations, expected checks, risk, backup/isolation policy, and a maximum repair
round (three by default).

The plan is a branch of the reconstruction run, not a Git branch and not a
request to redesign the source. A worker may apply one proposal in a fresh
directory, re-render affected pages first, then run full-deck validation.

After scoring candidates with `distillation_loop.py score` and gating them with
`distillation_loop.py gate`, run `candidate_controller.py select`. Only
`accept-for-human-review` candidates are eligible. The selector ranks them by
weighted score, keeps rejected candidates visible, and returns
`keep_previous_candidate` when none passes.

Selection never means release. It always returns `release_eligible: false` and
`human_review_status: pending` until a human confirms visual fidelity, formal
content, and editability. A local repair without scope must use affected pages
`all` and require a full-deck rerun. Independent panels and native formal text
must not be replaced by a whole-slide bitmap.
