# Unattended distillation agent

The repository's distillation loop is a bounded GitHub Actions controller, not
an unrestricted self-modifying model. It is enabled by
`.github/workflows/unattended-distillation.yml` and implemented by
`scripts/unattended_distillation_agent.py`.

## Trigger and lifecycle

The workflow starts in three situations:

1. `ai-ppt-plus CI` fails on `main`;
2. a maintainer manually dispatches the workflow;
3. the scheduled health check runs.

The controller downloads the failed run's reports when available, classifies
the evidence by owning layer, chooses a repair from
`assets/unattended-distillation-policy.json`, applies at most one approved
repair per round, and reruns the package, route, governance and repository
regressions. It uses no historical chat state as authority; reports, hashes and
the checked-in policy are the control plane.

## Automatic repair boundary

Only `ensure_block` rules in the policy can edit files. They may update the
skill instructions and focused references, but they cannot modify Python
executables, GitHub workflows, dependencies, YAML contracts or assets. The
agent refuses a dirty tracked worktree, path traversal, an unapproved target,
an unknown failure category, a repair that adds a marker already present, or a
candidate outside the file/line budget.

This boundary makes known governance regressions self-healing while keeping
implementation defects and ambiguous visual decisions reviewable. In
particular, the agent never fabricates text, chart data, image-generation
approval, human sign-off or a fallback decision.

## Improvement proof gate

Passing the repository gates is necessary but not sufficient. Before promotion
the agent writes `baseline-evaluation.json` and `candidate-evaluation.json`,
then runs `scripts/validate_distillation_improvement.py`. Promotion requires
all of the following:

1. the checked-out baseline is reproducibly red;
2. the candidate is green on the same gate suite and source case;
3. the candidate declares a real behavioural change and a non-empty diff;
4. numeric quality metrics do not regress (lower-is-better error metrics are
   checked in the opposite direction);
5. the candidate's regression evidence passes; and
6. when a reconstruction category is involved, the corresponding case replay
   proves the expected native objects and editable structure.

The only promotable result is `promotion=improved`. A green candidate without
proof is `promotion=no-improvement` and remains an uploaded report. Native
structure and visual repairs require case replay evidence; without it the
unattended controller stops before editing the skill. This prevents a generic
governance test from masquerading as proof that a PPTX table or panel became
editable.

## Promotion and stopping rules

A candidate is promotable only when the improvement proof gate passes, all
configured gates pass after the repair, and the final diff is within policy.
The workflow then creates a bot branch, opens a pull request, merges it with
squash, and dispatches the normal CI again on `main`.

The local loop stops after three rounds. A main-branch chain also carries its
round number in the bot commit message; a repeated failure at the configured
limit is left as a blocked artifact instead of causing an infinite commit/CI
loop. Unknown or still-failing cases remain in the uploaded distillation
report for human repair.

## Result states

- `passed`: fresh gates and the improvement proof passed; a diff may be promoted automatically.
- `clean`: no failure evidence and no repair is needed.
- `blocked`: evidence is unknown, a repair is not approved, proof is missing,
  or a gate remains failed.
- `disabled`: the checked-in policy explicitly disables the controller.

Technical acceptance is not a claim of human visual sign-off. For PPTX
reconstruction, the normal native-object, source-hash, visual comparison and
human closeout contracts remain authoritative.

## Case replay evidence contract

A unit test proves that a validator executes; it does not prove that an editable PPTX improved. For each accepted reconstruction case, run `scripts/replay_pptx_case.py` twice: once on the pre-distillation deck to write `baseline-evaluation.json`, and once on the post-distillation deck to write `candidate-evaluation.json`. Both reports must bind the original PPTX hash and process-image hash, rendered slide hashes, native object counts, table/panel/text audits, visual metrics and object deltas.

The social-channel anchor case must verify five native `a:tbl` tables, the three commission-card bodies, the policy table's four vertical merges, the monthly incentive table dimensions, native panels, native body text, the allowed text-free background, visual comparison, object comparison, and a mutation smoke test that edits a cell and moves a panel. The candidate is not promotion evidence unless its deck hash, source hashes and optional repair fingerprint are tied to the current repair. A prebuilt fixture is a CI sentinel; a real distillation candidate must be regenerated after the skill change.

Use a case matrix as the coverage unit rather than treating one case as universal coverage. The anchor case covers dense reference reconstruction with panels and tables; add separate cases for routing ownership, rich-text/font fidelity, icons/gradients, charts/data provenance, multi-slide consistency and package/runtime portability before claiming deck-wide improvement.


## Distillation case matrix

A single integrated replay case is a golden anchor, not full skill coverage. The checked-in matrix at `evals/distillation-case-matrix.json` separates atomic contract cases from actual PPTX replay cases across P0 routing/package safety, P1 native structure and visual fidelity, and P2 full-deck/cache consistency.

Targeted failure runs select the direct responsibility, adjacent responsibilities, and all P0 safety cases. Pre-merge, nightly, and manual full evaluations select the complete matrix. Every replay candidate must emit baseline, candidate, improvement, object, visual, and mutation evidence; unit-test success alone is insufficient.

The current social case is marked `static_sentinel`: it verifies that the replay/audit machinery can run, but it cannot promote a distilled repair. A real candidate must be regenerated after the repair and bound to that repair's fingerprint. The validator reports replay coverage debt, and the unattended controller blocks promotion when the affected category has no actual replay evidence.
