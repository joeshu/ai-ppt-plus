# Artifact ownership and conflict resolution

## Use and timing

Read whenever content, visuals, sources, manifests or approvals disagree.

## Input and output

Input: conflicting artifact versions and approval records. Output: chosen authority, conflict log entry, and either a deterministic resolution or user decision request.

## Authority rules

Explicit user requirement > approved outline > approved design system/visual > domain hard constraint > original material > agent preference. Formal data additionally requires the highest-authority traceable source or user confirmation. The outline owns formal words, numbers, facts and narrative; visual/reference images own layout, hierarchy, spatial relationships and style; `route-decision.json` owns the selected visual authority; original image assets own their pixels; manifests own implementation/status and per-object L0-L5 editability; validation reports own observed test results. The reconstruction agent does not own redesign authority.

If two artifacts of equal authority disagree, stop the current stage, present at most three choices with observable consequences, recommend one, and wait. Never back-propagate generated-image spelling or numbers into the outline.

## Examples

Positive: mockup says 25%, approved outline says 18%; PPTX uses 18%, preserves mockup layout, and logs the conflict.

Negative: the agent replaces an approved conclusion because a reference slide “looks more persuasive.”

## Failures and validation

Common failures: absent version IDs, ambiguous approval, stale manifests and silent conflict resolution. Validate artifact hashes/versions, approval records and conflict log before advancing.
