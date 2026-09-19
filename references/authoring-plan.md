# AuthoringPlan contract

AuthoringPlan is the pre-build execution plan that sits between Visual Inventory and implementation classification. It exists to reduce first-pass authoring mistakes before Artifact Tool Build, not to create another visual release gate.

## Position in the short loop

`Reference -> Visual Inventory -> AuthoringPlan -> native_editable/imagegen_asset -> Text Slot Preflight -> Asset Generation -> Artifact Tool Build -> Fresh Render -> Repair`

Visual Inventory answers **what is visible**. AuthoringPlan answers **how each visible item will be authored, where it belongs, what it depends on, and what must remain protected**.

## Required object contract

Each planned object must record:

- `object_id`: stable unique identifier used by Artifact Tool object naming and Repair Trace.
- `page`: 1-based page number.
- `semantic_role`: such as `title`, `subtitle`, `body_text`, `panel`, `badge`, `icon`, `table`, `chart`, `filled_arrow`, `connector`, `footer_system`, `decoration`.
- `implementation_type`: one of `native_text`, `native_shape`, `native_table`, `native_chart`, `connector`, `freeform`, `imagegen_asset`.
- `bbox`: normalized source-space `[x, y, width, height]`, each value in `[0,1]` and width/height positive.
- `parent_id`: optional semantic parent.
- `z_role`: semantic layer such as `background`, `container`, `asset`, `text`, `overlay`.
- `anchors`: optional parent-relative or object-relative anchor declarations.
- `protected_neighbors`: object IDs that this object's repair must not materially disturb.

Type-specific contracts:

- `native_text` requires `typography_contract` with observable line topology, role, alignment, font intent and slot-reservation notes.
- `imagegen_asset` requires `asset_contract` with semantic identity, color roles, contour traits, alpha/safe-zone intent and provenance mode.
- `native_shape`, `connector`, and `freeform` require `geometry_contract` describing the intended primitive/geometry semantics.
- `native_table` requires `table_contract` proving table semantics rather than visual-grid appearance.
- `native_chart` requires `chart_contract` describing chart type/data authority and blank-value semantics.

## Relationship-first planning

Repeated components are not assumed to have identical geometry. AuthoringPlan may define a shared `component_family`, but each object keeps its own bbox, text slot, divider position, icon reservation and anchors when the reference differs.

Parent systems such as header/footer bands, composite badges, step systems, timeline systems and card groups should be modeled explicitly. Repair the parent geometry before re-anchoring children.

## Planning rules

1. Do not start Artifact Tool Build with unclassified material objects.
2. Do not let authoring helpers invent geometry that was not present in AuthoringPlan unless the helper writes the decision back to the plan/evidence.
3. Formal text must remain native and traceable to TextGraph/TextFit evidence.
4. Complex pictograms and artwork should not be silently replaced by generic PowerPoint primitives.
5. Filled arrows and connectors are distinct geometry roles.
6. `imagegen_asset` placement must reserve a known slot before text fitting of adjacent objects.
7. Protected neighbors are local regression constraints for Responsible Object Repair, not release-score thresholds.

## Validation

Run:

```bash
python3 scripts/validate_authoring_plan.py PROJECT/authoring-plan.json --json
```

Validation is fail-closed for structural planning errors such as duplicate IDs, invalid bboxes, unresolved parents, parent cycles, missing type-specific contracts, invalid references or missing source binding. It does **not** judge visual fidelity or introduce SSIM/score thresholds.

Use `assets/authoring-plan.template.json` as the minimal shape and `assets/schemas/authoring-plan.schema.json` as the versioned machine contract.
