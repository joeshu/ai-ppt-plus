# Geometry Primitive Resolver

## Purpose

Resolve every geometry-bearing AuthoringPlan object to the smallest faithful PowerPoint primitive **before** Artifact Tool authoring. The resolver reduces ad-hoc geometry choice and prevents semantic substitutions such as connector-for-filled-arrow, segmented-line-for-curve, or ordinary native arrow for complex artistic motion graphics.

## Primitive set

- `RECT`
- `ROUNDRECT`
- `ELLIPSE`
- `TRAPEZOID`
- `FUNNEL`
- `FILLED_ARROW`
- `CONNECTOR`
- `FREEFORM_BEZIER`
- `TABLE`
- `CHART`
- `IMAGEGEN_COMPLEX`

## Parameter contract

Primitive selection is not enough. The resolver also emits authoring parameters:

- `ROUNDRECT`: normalized corner radius / adjustment.
- `TRAPEZOID` / `FUNNEL`: direction and taper ratio.
- `FILLED_ARROW`: direction, head ratio and shaft ratio.
- `CONNECTOR`: endpoints and arrow-head semantics.
- `FREEFORM_BEZIER`: cubic requirement, control points, and final OOXML expectation `a:cubicBezTo`.

These parameters are authoring intent, not visual score gates.

## Resolution rules

1. Valid explicit `geometry_contract.primitive_hint` wins.
2. Native table/chart remain semantic objects.
3. Complex artistic geometry, gradient/3D/glow storytelling routes to `IMAGEGEN_COMPLEX`.
4. Curved paths route to `FREEFORM_BEZIER`; final authored OOXML must preserve a true cubic path rather than many short line segments.
5. Stroke-only two-endpoint geometry routes to `CONNECTOR`.
6. Filled body + shaft + arrowhead routes to `FILLED_ARROW`.
7. Direction-sensitive funnel/trapezoid preserve `direction` and `taper_ratio`.
8. Rounded cards preserve round-rect adjustment; circles/nodes use `ELLIPSE`.
9. Simple remaining native shapes use `RECT`.

## Repair semantics

A deterministic mismatch between resolved primitive and AuthoringPlan `implementation_type` is a pre-build `repair-required` signal. An unresolved primitive is a blocker because the authoring backend would otherwise guess.

Do not use unrelated shapes to visually compensate. Update AuthoringPlan, rerun the resolver, then author.

## Build binding

Artifact Tool Build consumes the resolution report alongside AuthoringPlan. For `FREEFORM_BEZIER`, the post-authoring structural check must verify `a:cubicBezTo` exists for the responsible object/path. Direction-sensitive primitives must use the emitted parameter set rather than renderer defaults.

## Usage

```bash
python3 scripts/resolve_geometry_primitives.py PROJECT/authoring-plan.json \
  --report PROJECT/geometry-resolution.json --json
```
