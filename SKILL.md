---
name: ai-ppt-plus
description: Orchestrate complete PowerPoint work from PDF, DOCX, Markdown, Excel/CSV, project files, meeting notes, approved outlines, images, or existing PPT/PPTX. Trigger for “做PPT/幻灯片/路演稿/汇报材料”, multi-source intake, outline-first planning, mixed visual/reconstruction routes, deck-wide QA, release, or resuming a project. Owns source authority, narrative, route, design authority, cross-skill manifests, QA aggregation, and release gates. Delegate image-slide generation to $ai-ppt-visual-gen and image/reference-to-editable-PPTX work to $ai-ppt-editable. Do not trigger when the request is only to generate image slides or only to reconstruct supplied slide images; use the narrower worker skill.
metadata:
package_revision: 2026.09.02.02
---

# AI PPT Plus Orchestrator

## Purpose

Run one traceable deck workflow across two independently callable worker
skills. This entrypoint is the only authority for source conflicts, approved
outline, route decisions, design-system revision, deck-wide state, report
aggregation, human closeout, and delivery eligibility. It does not duplicate
the workers' generation or reconstruction procedures.

The repository is one bundle with three self-contained skill directories.
The repository root is the `ai-ppt-plus` Super skill; each worker owns its own
`scripts/`, `references/`, `assets/`, package validator, and tests. Read
`references/three-skill-architecture.md`, `references/operations-matrix.md`,
and `references/skill-routing.md`. The operations matrix is the executable
module/step/tool map, cache policy and recovery policy. Validate the bundle
before intake:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
```

Before any worker starts, create and validate the root contracts. The outline
contract is the formal content master; route and workflow state bind to its
hash:

```bash
python3 scripts/build_outline_contract.py PROJECT/outline.csv \
  --output PROJECT/outline-contract.json --project-id PROJECT_ID --revision R1
python3 scripts/validate_outline_contract.py PROJECT/outline-contract.json \
  --require-approved
python3 scripts/validate_orchestration_gates.py PROJECT \
  --outline-contract PROJECT/outline-contract.json \
  --route-decision PROJECT/route-decision.json \
  --workflow-state PROJECT/workflow-state.json --strict
```

Formal copy must be traceable through `content-authority/v1`: source → approved
outline row → PPTX object → rendered region. Generated pixels and OCR never
become formal-copy authority. Validate the manifest strictly with
`scripts/validate_content_authority.py --require-pptx-refs --require-render-refs`.

The root package validator also validates both child packages. If any
configured runtime copy differs by revision or managed-file SHA-256,
stop. Never continue on chat memory or an unversioned worker copy.

## Ownership and delegation

| Entrypoint | Owns | Must not claim |
|---|---|---|
| `ai-ppt-plus` | intake, source authority, narrative, approved outline, route, design authority, shared state, QA aggregation, human closeout, release | the workers' internal generation/decomposition algorithms |
| `$ai-ppt-visual-gen` | self-contained A1–A5 image-slide planning, prompting, raster generation evidence, page-local retry, source retention, deck strip and image-only PPTX | narrative/formal-text authority in orchestrated mode, editable reconstruction, release |
| `$ai-ppt-editable` | self-contained reference decomposition, editable-object planning, PPTX authoring, rendering and technical QA | narrative redesign, whole-deck release, human sign-off |

`Presentations`, `python-pptx`, image models, OCR, and renderers are adapters or
tools, not extra business skills. A worker may use them only through the
checked-in routing and backend contracts.

## Orchestration workflow

### O0 — Restore and preflight

1. Restore `deck-brief.md`, `handoff.json`, source inventory, approved outline,
   design system, route decision, manifests, issue log, and reports. Validate a
   resumed handoff with `scripts/validate_handoff.py`.
2. Run `scripts/probe_environment.py`,
   `scripts/validate_backend_binding.py`, and `scripts/probe_fonts.py` before
   selecting adapters. For Chinese delivery, follow
   `references/font-portability.md` and validate the task-local CJK font.
3. Inventory every input under `references/source-intake.md`. Record authority,
   readability, conflicts, missing facts, OCR requirements, and sensitive data.
4. Create or restore `workflow-state.json`. Validate it with
   `scripts/validate_workflow_state.py`; use `--strict` when it is a required
   handoff or release prerequisite. This file is the durable control plane,
   not a replacement for page/object manifests.

### O1 — Brief, story, and approval

1. Establish goal, audience, setting, language, page/time limit, output type,
   editability target, data authority, brand/font constraints, and deadline.
2. Build the narrative using `references/narrative-strategy.md`; create the
   structured outline from `references/outline-table-contract.md`, then freeze
   its hash-backed outline contract before delegation.
3. Obtain explicit outline approval before visual generation or reconstruction.
   If approval is intentionally waived, record scope and risk. Do not invent
   critical facts or let pixels override approved text.

### O2 — Route and design authority

Choose one visual authority per page and persist `route-decision.json`:

- `visual-creation`: no approved fixed reference governs the page; delegate to
  `$ai-ppt-visual-gen`.
- `reference-reconstruction`: a supplied/approved reference governs layout;
  delegate to `$ai-ppt-editable` without generating a replacement whole page.
- `native-authoring`: a deterministic text/chart/table page can be authored
  directly by `$ai-ppt-editable` from approved content.

Bind the route decision to the outline contract and run both
`scripts/validate_route.py` and `scripts/validate_orchestration_gates.py`. A `needs_user` or `blocked` route cannot
proceed. Persist the deck design system and its revision before delegating.
The orchestrator's outline/design revisions are immutable inputs to workers;
workers return evidence and issues, not replacement authority.

### Engine routing contract

For `reference-reconstruction`, `editable-pptx`, and `native-authoring`,
`ai-ppt-editable` is the primary execution engine. The route decision must
persist `primary_engine`, `fallback_policy`, `fallback_used`,
`fallback_events`, and `editable_object_policy` before delegation.

`GordenImage2PPTX` is not a fourth business skill and is never selected as the
primary engine. It is an explicitly approved, region-only fallback for visual
assets such as icons, decorative art, artistic typography, complex gradients,
illustrations or background texture. It is forbidden for formal text, simple
semantic panels/cards/frames, tables, charts and whole-page composition. Every
fallback event must record the affected region, reason, generated/recovered
asset record and explicit user decision; otherwise the route is blocked.

### O3 — Delegate visual generation

For image slides or high-end visual intermediates, invoke
`$ai-ppt-visual-gen` from `ai-ppt-visual-gen/`. Supply approved outline rows, source references, design
system, page count, ratio, language, density, reference policy, and target
mode. Require its A1–A5 outputs:

- `visual-generation-plan.json` and materialized prompt files;
- retained generated source plus project copy for every page;
- `visual-generation-manifest.json` with hashes and page-local attempts;
- a complete deck strip and review status.

Do not accept a whole-page image as editable delivery. Generated text remains
provisional until reconciled against the approved formal-text authority.

### O4 — Delegate editable PPTX work

Invoke `$ai-ppt-editable` when the deliverable is editable PPTX, when a fixed
reference must be reconstructed, or when approved content must be authored as
native objects. Invoke it from `ai-ppt-editable/` and supply route decision, formal-text authority, references or
visual intermediates, design revision, editability target, fonts, and worker
manifests. Require editable-object evidence, rendered previews, technical QA,
and a worker handoff. The worker may repair its own technical defects but may
not change the story or redesign an approved reference.

After A's generated images/evidence and B's reviewed editable layout plan exist,
the deterministic handoff can be executed in one command:

```bash
python3 scripts/run_super_pipeline.py PROJECT \
  --mode full --route-decision PROJECT/route-decision.json \
  --workflow-state PROJECT/workflow-state.json \
  --visual-plan PROJECT/visual-generation-plan.json \
  --visual-manifest PROJECT/visual-generation-manifest.json \
  --editable-layout PROJECT/editable-layout.json \
  --output-deck PROJECT/deliverable.pptx --expected-pages N
```

In `full` mode this validates the route, runs A (when the route is
`visual-creation`), builds the deck strip, invokes B's composer and full
technical QA, and writes/validates `handoff/v2`. The native image-generation
event remains external and must happen before A; the coordinator never fakes
it. The default `handoff` mode remains a quick compatibility diagnostic. Add
`--require-workflow-state` to block the chain when phase-required artifacts,
authority approvals, blocker records or SHA-256 evidence are incomplete.

Before release or a CI run, validate the local capability report against
`assets/environment-contract.json` and run the runtime mirror gate. Missing
capabilities, OCR engines, or drifted shared worker files are blocking
evidence; they are not silently substituted.

### O5 — Reconcile, review, and release

1. Reconcile worker outputs into the canonical manifest registry. Run the
   pipeline and validators appropriate to the route. Follow
   `references/report-protocol.md` and `references/quality-rubric.md`.
2. Keep the four quality dimensions—content, visual, structure, and delivery—
   separate from automated state, human visual review, and release eligibility.
   Validate `quality-gates.json` with `scripts/validate_quality_gates.py`; a
   technical pass does not imply human closeout or release eligibility.
   A technical pass never claims human sign-off.
3. Render the final PPTX, inspect deck strip and full pages, repair only the
   owning stage, rerun affected gates, and record every revision.
4. Deliver only when blockers are zero, required human review is recorded,
   hashes match, and the user-requested editability/font conditions pass.

## Route-specific rules

- Outline-only stops after an approved outline and narrative report.
- Visual-only stops after `$ai-ppt-visual-gen` evidence and visual review.
- Reference-only reconstruction uses `$ai-ppt-editable`; user transcription or
  approved copy is formal authority, never OCR confidence alone.
- Existing PPTX repair preserves the original, diagnoses before mutation, and
  returns through rendering and validation.
- Charts require traceable data, units, missing-value policy, and the chart
  reconstruction contract; never infer authoritative values from decoration.
- Critical missing input moves the run to `revision-required`; present no more
  than three concrete choices and wait.

## Shared state and recovery

The canonical state is files, not conversation: workflow state, brief, source inventory,
outline, design system, route decision, worker manifests, object manifests,
report index, issue log, handoff, and delivery report. Freeze accepted
regression baselines with `scripts/revision_guard.py freeze`; never overwrite a
baseline. On interruption, resume only after validating hashes and remaining
slides. A failed worker page is retried within that worker's bounded policy;
successful pages and unrelated downstream artifacts remain intact.

P1 reinforcement is available through `--require-p1`: it adds the approved
deck-wide design-system gate, structured issue-log closure gate, atomic DAG
checkpoints and a portable review package. Existing DAG/page caches remain
usable, but cache entries are fingerprinted by local code and runtime,
published under a per-key lock, and moved to a recoverable quarantine when
metadata or output hashes fail.

Each run can also emit `performance-report.json` for normalized wall/task/cache
timings, retries and repair rounds. When a reference and editable object
manifest are available, `dual-comparison.json` combines pixel comparison of the
reference against the final render with semantic object comparison of the
reference-derived manifest against the final PPTX. These reports remain
diagnostic unless the corresponding strict gate is requested.

## Non-negotiable gates

- No silent route or backend substitution.
- No `GordenImage2PPTX` primary selection or unrecorded/full-page fallback.
- Editable routes default to `ai-ppt-editable`; semantic panels, cards and
  tables must remain native objects unless an explicit contract records a
  text-free complex-visual exception.
- No generated fact, number, logo, or formal text becomes authority.
- No whole-page bitmap is described as editable PPTX.
- No child skill lowers the requested L0–L5 editability target.
- No release claim without aggregated technical evidence and explicit human
  closeout where required.
- No downstream stage may run from a missing or stale required workflow state.
- No downstream stage may run from an unbound or stale outline contract.
- Every worker handoff must expose the same protocol fields: skill revision,
  input hashes, output artifacts, manifest paths, QA results, known issues and
  next action.
- No three-skill package change is valid unless all three entrypoints share the
  same `package_revision`, each directory passes its own package validation,
  and the root bundle validation passes.


<!-- unattended-distillation:entrypoint -->
## Unattended distillation

When an unattended maintenance cycle is enabled, use `scripts/unattended_distillation_agent.py` and `assets/unattended-distillation-policy.json`. The controller may analyze structured gate evidence, apply only an allowlisted repair rule, rerun the package/route/governance gates, and report a candidate as promotable. GitHub Actions owns branch, PR and merge operations. Unknown failures, implementation changes, visual ambiguity, human sign-off, image-generation decisions and protected-file edits remain blocked. Read `references/unattended-distillation.md` for trigger, scope, three-round and stopping rules.
<!-- /unattended-distillation:entrypoint -->
<!-- unattended-distillation:improvement-proof -->
## Improvement proof requirement

Unattended distillation may be promoted only when the checked-out baseline is reproducibly red, the candidate is green, the candidate declares a real behavioural change, regression metrics do not degrade, and the improvement validator returns `promotion=improved`. A passing gate without this red-green proof is not a promotion signal.
<!-- /unattended-distillation:improvement-proof -->

<!-- unattended-distillation:case-replay -->
## Case-level replay requirement

A generic repository test is never sufficient evidence that a PPTX reconstruction improved. For native-structure or text/visual distillation, require a fresh baseline/candidate case replay with the actual deck, source/process hashes, rendered output, OOXML `a:tbl` count, table merge topology, native panel audit, native text audit, visual comparison, object comparison and mutation smoke test. Promote only when the candidate is bound to the current repair fingerprint and returns `promotion=improved`.
<!-- /unattended-distillation:case-replay -->
