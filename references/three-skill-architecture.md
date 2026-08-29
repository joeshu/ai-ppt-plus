# Three-skill architecture

## Decision

The package exposes exactly three independently discoverable skill entrypoints:

| Skill | Role | Standalone input | Primary output |
|---|---|---|---|
| `ai-ppt-plus` | orchestrator | mixed sources or a complete deck request | approved story, route, delegated work, aggregated QA and release state |
| `ai-ppt-visual-gen` | visual worker | topic, content brief, or approved outline | raster slide pages, prompts, retained sources, manifest and deck strip |
| `ai-ppt-editable` | editable worker | references, image pages, existing deck, or approved structured content | editable PPTX, rendered previews, object evidence and technical QA |

The repository keeps one shared `scripts/`, `assets/`, and `references/`
runtime. Worker entrypoints do not copy implementation files. This is deliberate:
independent invocation is a product boundary, while shared code is a versioning
boundary. Copying the same validators and schemas into three directories would
allow revisions to drift and make cross-skill evidence non-reproducible.

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

All three entrypoints must declare the same package revision. The package
validator blocks missing entrypoints, duplicate names/roles/paths, revision
drift, or a shared-runtime policy other than `single-source`.

## Change boundary

The split is organizational. Existing image-to-PPTX decomposition, asset
extraction, composition, rendering, and QA algorithms remain in the shared
runtime unchanged. Future algorithm changes require their own scoped review;
they must not be smuggled into an entrypoint/routing refactor.
