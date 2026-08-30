---
name: ai-ppt-plus
description: Orchestrate complete PowerPoint work from PDF, DOCX, Markdown, Excel/CSV, project files, meeting notes, approved outlines, images, or existing PPT/PPTX. Trigger for “做PPT/幻灯片/路演稿/汇报材料”, multi-source intake, outline-first planning, mixed visual/reconstruction routes, deck-wide QA, release, or resuming a project. Owns source authority, narrative, route, design authority, cross-skill manifests, QA aggregation, and release gates. Delegate image-slide generation to $ai-ppt-visual-gen and image/reference-to-editable-PPTX work to $ai-ppt-editable. Do not trigger when the request is only to generate image slides or only to reconstruct supplied slide images; use the narrower worker skill.
metadata:
 package_revision: 2026.08.29.21
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
`references/three-skill-architecture.md` and
`references/skill-routing.md`. Validate the bundle before intake:

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
```

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

### O1 — Brief, story, and approval

1. Establish goal, audience, setting, language, page/time limit, output type,
   editability target, data authority, brand/font constraints, and deadline.
2. Build the narrative using `references/narrative-strategy.md`; create the
   structured outline from `references/outline-table-contract.md`.
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

Run `scripts/validate_route.py`. A `needs_user` or `blocked` route cannot
proceed. Persist the deck design system and its revision before delegating.
The orchestrator's outline/design revisions are immutable inputs to workers;
workers return evidence and issues, not replacement authority.

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
  --visual-plan PROJECT/visual-generation-plan.json \
  --visual-manifest PROJECT/visual-generation-manifest.json \
  --editable-layout PROJECT/editable-layout.json \
  --output-deck PROJECT/deliverable.pptx --expected-pages N
```

In `full` mode this validates the route, runs A (when the route is
`visual-creation`), builds the deck strip, invokes B's composer and full
technical QA, and writes/validates `handoff/v2`. The native image-generation
event remains external and must happen before A; the coordinator never fakes
it. The default `handoff` mode remains a quick compatibility diagnostic.

Before release or a CI run, validate the local capability report against
`assets/environment-contract.json` and run the runtime mirror gate. Missing
capabilities, OCR engines, or drifted shared worker files are blocking
evidence; they are not silently substituted.

### O5 — Reconcile, review, and release

1. Reconcile worker outputs into the canonical manifest registry. Run the
   pipeline and validators appropriate to the route. Follow
   `references/report-protocol.md` and `references/quality-rubric.md`.
2. Keep automated state, human visual review, and release eligibility separate.
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

The canonical state is files, not conversation: brief, source inventory,
outline, design system, route decision, worker manifests, object manifests,
report index, issue log, handoff, and delivery report. Freeze accepted
regression baselines with `scripts/revision_guard.py freeze`; never overwrite a
baseline. On interruption, resume only after validating hashes and remaining
slides. A failed worker page is retried within that worker's bounded policy;
successful pages and unrelated downstream artifacts remain intact.

## Non-negotiable gates

- No silent route or backend substitution.
- No generated fact, number, logo, or formal text becomes authority.
- No whole-page bitmap is described as editable PPTX.
- No child skill lowers the requested L0–L5 editability target.
- No release claim without aggregated technical evidence and explicit human
  closeout where required.
- No three-skill package change is valid unless all three entrypoints share the
  same `package_revision`, each directory passes its own package validation,
  and the root bundle validation passes.
