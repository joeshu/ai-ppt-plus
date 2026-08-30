# Three-skill architecture

## Decision

The package exposes exactly three independently discoverable skill entrypoints:

| Skill | Role | Standalone input | Primary output |
|---|---|---|---|
| `ai-ppt-plus` | orchestrator | mixed sources or a complete deck request | approved story, route, delegated work, aggregated QA and release state |
| `ai-ppt-visual-gen` | visual worker | topic/content brief (first stops at thought-table review) or approved thought table | approved-table gate, raster slide pages, prompts, retained sources, manifest and deck strip |
| `ai-ppt-editable` | editable worker | references, image pages, existing deck, or approved structured content | editable PPTX, rendered previews, object evidence and technical QA |

Every skill is a physical self-contained package with its own `scripts/`,
`assets/`, `references/`, package manifest, validator, tests, and agent metadata.
The root repository directory is the `ai-ppt-plus` Super package; the two worker
directories can be copied or installed independently. Deliberate copies are
controlled by matching package revisions, per-package hashes, child package
validation, and regression tests.

## Inspiration and non-dependency

The high-level “one orchestrator plus two workers” organization was informed by
the public GordenSuperPPTSkills repository. AI PPT Plus does not import, invoke,
or formally depend on its skill names, scripts, manifests, or runtime. Its
machine-readable routing names only the three internal skills. Image models,
OCR, renderers, `Presentations`, and `python-pptx` are adapters/tools below the
skill layer.

## Independence contract

A worker is independently callable when it has its own `SKILL.md`, trigger
description, agent metadata, inputs, outputs, blocking states, and standalone
authority rules. Independence does not grant release authority:

- the visual worker can complete image-slide generation but cannot call the
  result editable or released;
- the editable worker can complete technical PPTX validation but cannot claim
  deck-wide narrative approval or human sign-off;
- the orchestrator can release only after it reconciles worker evidence.

All three entrypoints must declare the same package revision. Each package
validator blocks missing local runtime directories and stale managed files. The
root validator additionally blocks missing child packages, duplicate roots,
entrypoint mismatch, or revision drift.

## Narrative-first visual route

For a visual-creation request, the first reviewable product is the PPT thought
table, not a slide image. `ai-ppt-plus` owns source authority, the four-column
table, user feedback, revision history and approval. `ai-ppt-visual-gen` only
consumes the approved table and turns it into a locked visual plan. Its prompt
and manifest make the approved table hash, premium-commercial quality target,
canvas policy and same-model/context session visible. A topic or unapproved
draft cannot cross the A1–A5 generation gate.

## Change boundary

The split is organizational. Existing image-to-PPTX decomposition, asset
extraction, composition, rendering, and QA algorithms are copied into the
editable worker unchanged. Future algorithm changes require their own scoped review;
they must not be smuggled into an entrypoint/routing refactor.

## Operating contract

The complete stage-by-stage module and tool map is maintained in
[`operations-matrix.md`](operations-matrix.md). The root orchestrator's
resumable control plane is `workflow-state/v1`, defined by
`assets/schemas/workflow-state.schema.json` and validated by
`scripts/validate_workflow_state.py`. Worker manifests remain the detailed
page/object evidence; workflow state only decides whether the next stage is
allowed to start.
