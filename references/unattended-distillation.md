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

## Promotion and stopping rules

A candidate is promotable only when all configured gates pass after the repair,
the final diff is within policy, and the result is `status=passed`. The workflow
then creates a bot branch, opens a pull request, merges it with squash, and
dispatches the normal CI again on `main`.

The local loop stops after three rounds. A main-branch chain also carries its
round number in the bot commit message; a repeated failure at the configured
limit is left as a blocked artifact instead of causing an infinite commit/CI
loop. Unknown or still-failing cases remain in the uploaded distillation
report for human repair.

## Result states

- `passed`: fresh gates passed; a diff may be promoted automatically.
- `clean`: no failure evidence and no repair is needed.
- `blocked`: evidence is unknown, a repair is not approved, or a gate remains
  failed.
- `disabled`: the checked-in policy explicitly disables the controller.

Technical acceptance is not a claim of human visual sign-off. For PPTX
reconstruction, the normal native-object, source-hash, visual comparison and
human closeout contracts remain authoritative.
