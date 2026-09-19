# Astra Visual Reconstruction Engine + Deterministic PPTX Engine

## Objective

Convert a rasterized slide/reference image into a PowerPoint deck that is simultaneously:

1. visually high fidelity to the immutable source image;
2. semantically editable at object level;
3. deterministic and auditable at PPTX generation time;
4. repairable by responsibility domain without rebuilding the whole slide;
5. regression-gated against the existing native-editability and replay suite.

## Non-negotiable boundary

Astra is the **visual reasoner and visual QA judge**. It is not the PPTX renderer.

The deterministic engine remains responsible for native PowerPoint construction:

- text -> native text frames / rich-text runs;
- structural boxes / lines -> native shapes;
- tables -> native tables when semantic evidence exists;
- charts -> native charts with data where recoverable;
- connectors -> native connectors;
- icons / illustrations / complex artistic visuals -> independent assets;
- no full-slide raster may satisfy an editable semantic route.

## Pipeline

```text
Immutable source image
        |
        v
Astra Visual Reasoner
        |
        v
PageGraph IR
  |-- layout relations
  |-- text semantics / runs
  |-- native semantic object types
  `-- independent asset metadata
        |
        v
Deterministic PPTX Engine
        |
        v
Editable PPTX
        |
        v
Deterministic render
        |
        v
Astra Visual QA + metric/object evidence
        |
        v
DifferenceGraph
  |-- geometry
  |-- typography
  |-- asset
  `-- semantic
        |
        v
RepairRouter (bounded, whitelist-only)
        |
        v
Targeted repair engine
        |
        v
Re-render -> QualityGate
```

## PageGraph

`reconstruction/graph_ir.py` is the normalized intermediate representation.

It records:

- stable object id;
- semantic object type;
- normalized geometry;
- parent/child hierarchy;
- visual/semantic metadata;
- object source metadata;
- confidence;
- alignment, equality, spacing, containment and connector relations.

The graph is validated before it reaches the authoring backend. Unknown relation targets, duplicate ids and invalid object types fail closed.

`PageGraph.to_authoring_deck()` projects the IR into the existing deterministic authoring contract and forces native semantics for tables/charts and the editable route.

## DifferenceGraph

`reconstruction/difference_graph.py` replaces a plain diff image as the primary repair artifact.

Each finding contains:

- object id;
- exactly one responsibility domain;
- P0-P3 severity;
- confidence;
- measured metrics/evidence;
- a bounded proposed patch.

Responsibility domains:

- `geometry`: x/y/w/h, spacing, crop, alignment, rotation;
- `typography`: font metrics, rich runs, spacing, margins, autofit;
- `asset`: subject scale/crop/style/opacity/regeneration;
- `semantic`: wrong object type, rasterized table/chart/text, grouping/connector errors.

Semantic editability violations are P0 even when visual similarity is high.

## Repair safety

`reconstruction/repair_router.py` never executes arbitrary model output.

Automatic repair requires all of the following:

- confidence >= configured threshold;
- patch contains only responsibility-domain whitelist keys;
- patch is non-empty;
- no P0 semantic mutation is executed without review/reconstruction evidence.

Unsafe, incomplete or low-confidence repairs are deferred and can block delivery.

## Quality gate

`reconstruction/quality_gate.py` separates two decisions:

1. **hard correctness** — editability ratio, semantic accuracy, full-slide-raster prohibition, renderer regressions and non-diagnostic P0/P1 findings;
2. **Golden visual target** — global and critical-region similarity used for final promotion/release-quality assessment.

Visual metrics remain visible on every iteration, but they do not replace render review and do not turn a technically valid draft into a hard failure by themselves. A high visual score still cannot override semantic/editability failure.

## Closed-loop behavior

`reconstruction/pipeline.py` implements a bounded state machine:

`UNDERSTAND -> AUTHOR -> RENDER -> QA -> GATE -> REPAIR -> REVIEW/COMPLETE`

The pipeline:

- edits only findings that have safe executable actions;
- re-renders after every accepted repair;
- stops on unresolved hard correctness failures;
- returns `REVIEW` rather than falsely declaring completion when the deck is technically valid but below the Golden visual target or has low-confidence/deferred visual findings;
- preserves per-iteration metrics/actions and draft lineage for Repair Trace / distillation evidence;
- promotes to `COMPLETE` only when hard correctness passes, no further safe repair is pending, and the Golden visual target is met.

## Astra host contract

`reconstruction/astra_contract.py` is provider-neutral. The host runtime supplies source/render images to Astra and returns JSON only.

Two strict model tasks are defined:

- `visual-reconstruction` -> `PageGraph`;
- `visual-qa` -> `DifferenceGraph`.

The repository validates both responses before deterministic execution. This prevents prose/tool drift from changing the PPTX contract.

## Integration with existing ai-ppt-editable

This architecture **extends rather than replaces** the existing engine:

- `authoring_backend.py` remains the deterministic PPTX writer;
- existing TextSpec/runs behavior remains authoritative for native text;
- asset placement/chroma-key/imagegen rules remain authoritative for independent assets;
- existing semantic/native editability audits remain required;
- 12-case replay/distillation remains the regression baseline;
- `performance-report.json` remains the performance evidence surface.

## Acceptance policy

A draft may continue through render-driven repair when hard correctness passes even if the Golden visual target has not yet been met. Golden/release promotion requires:

- no blocking non-diagnostic DifferenceGraph findings remain;
- hard QualityGate correctness passes;
- Golden visual target passes or a documented human-approved special-case decision exists;
- no full-slide semantic raster exists;
- critical editable objects pass native-object audit;
- source image remains the immutable visual reference;
- same-coordinate local-crop evidence and Repair Trace cover the last accepted repair round.
