# Geometry Primitive Resolver

## Purpose

Resolve each AuthoringPlan geometry-bearing object to the smallest faithful PowerPoint primitive before Artifact Tool authoring. The resolver reduces ad-hoc geometry choices and prevents common semantic mistakes such as using a connector for a filled arrow, short line segments for a smooth curve, or a native arrow for complex artistic motion graphics.

## Primitive set

- `RECT`
- `ROUNDRECT`
- `ELLIPSE`
- `FILLED_ARROW`
- `CONNECTOR`
- `FREEFORM_BEZIER`
- `TABLE`
- `CHART`
- `IMAGEGEN_COMPLEX`

## Resolution rules

1. Explicit `geometry_contract.primitive_hint` wins when it is valid.
2. `native_table` and `native_chart` remain native semantic objects.
3. Complex artistic geometry, gradient/3D/glow storytelling, or decorative motion graphics route to `IMAGEGEN_COMPLEX`.
4. Continuous curves or `requires_cubic_bezier=true` route to `FREEFORM_BEZIER`; final OOXML should contain a true cubic path rather than many short line segments.
5. Stroke-only paths with two endpoints route to `CONNECTOR`.
6. A filled arrow requires explicit filled body + shaft + arrowhead evidence and routes to `FILLED_ARROW`.
7. Circle/node/dot semantics route to `ELLIPSE`; rounded cards route to `ROUNDRECT`; simple remaining native shapes default to `RECT`.

## Repair semantics

A deterministic mismatch between the resolved primitive and AuthoringPlan `implementation_type` is a pre-build `repair-required` signal. An unresolved primitive is a blocker because the authoring backend would otherwise guess.

This resolver does not use SSIM or visual score thresholds. It controls implementation semantics before build.

## Usage

```bash
python3 scripts/resolve_geometry_primitives.py PROJECT/authoring-plan.json --report PROJECT/geometry-resolution.json --json
```

The authoring stage should consume the resolution report and repair mismatches before constructing the final deck.
