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

### P0 fidelity extensions (host integration required)

Reference reconstruction through `ReconstructionPipeline.run` requires an
independent `source_inventory` and an `extract_objects` callback. Bind inventory
and graph `source_sha256`, distinct observation/planning IDs, and each graph
node's `source.source_object_id`. Source inventory must be observed separately
from the image, not exported from the plan. `source_coverage.extract_pptx_objects`
reads actual PPTX names recursively; authoring names must equal stable object
IDs. This is an additional completeness check, not a replacement for semantic
type, text, geometry or source-file hash validation. IDs/evidence alone cannot
prove that an observer actually inspected an image.

Use `repair_executors.execute_typography_search` for explicit bounded candidates
measured by the actual renderer. The callback receives a candidate authoring
deck and object ID and must return normalized ink bbox, line count, baselines,
font verification, overflow state, renderer ID and render hash. Preserve copy
and runs. A missing match leaves the old deck unchanged and requires review.
The module does not supply a renderer or infer correct font metrics itself.

Use `execute_peer_layout` for approved ordered peer constraints. It preserves
unrelated objects, refuses locked-object changes and cannot shrink peers to
make an infeasible constraint fit. This initial solver supports x/y equal gaps
and optional equal size; containment, connector rerouting, and arbitrary
PageGraph constraint solving remain unsupported and must not be inferred.

`asset_subject.subject_placement` returns full-image placement from an alpha
subject bbox without changing image bytes. Supply an isotropic target unit
(pixels or inches, not unequal-axis slide fractions). Convert its result to
the authoring unit explicitly. Asset visual QA and native imagegen policy
remain required; transparent-boundary alignment is not a fidelity pass.

These extensions have unit/fixture coverage. They are not evidence that the
12 visual cases or PowerPoint/WPS end-to-end acceptance has improved. Host
adapter wiring and actual render measurements must be verified before claiming
production coverage. Do not describe the pending P1 delivery/benchmark work as
complete on the strength of these tests.

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

`reconstruction/quality_gate.py` evaluates four independent contracts:

1. visual fidelity: global and critical-region similarity;
2. editability: semantic object editability ratio and full-slide-raster prohibition;
3. semantic correctness: object type/data contract accuracy;
4. renderer stability: renderer-specific regressions (PowerPoint/WPS evidence when available).

A high global similarity score cannot override semantic/editability failure.

## Closed-loop behavior

`reconstruction/pipeline.py` implements a bounded state machine:

`UNDERSTAND -> AUTHOR -> RENDER -> QA -> GATE -> REPAIR`

The pipeline:

- edits only findings that have safe executable actions;
- stops on unresolved blocking semantic findings;
- stops after a configured maximum number of repair iterations;
- preserves per-iteration metrics and actions for `performance-report.json` / distillation evidence;
- re-renders after every repair before another decision.

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

A candidate may be delivered only when:

- no blocking DifferenceGraph findings remain;
- QualityGate passes;
- no full-slide semantic raster exists;
- critical editable objects pass native-object audit;
- source image remains the immutable visual reference;
- every repair round is reflected in evidence/history.
