# AuthoringPlan and staged implementation checklist

This contract moves quality control forward into generation. It is not a visual release gate and does not reintroduce a scalar fidelity threshold.

## Batch A — P0 first-pass correctness

- [x] **AuthoringPlan compiler** — before Artifact Tool Build, every material object has stable `object_id`, semantic role, implementation type, bbox, parent, anchors/relationships, z-role and protected neighbors. Native text receives a text contract; ImageGen assets receive identity/color/alpha contracts.
- [x] **Text Coverage Auditor** — every visible native text-producing path (`text_box`, `add_run`, table cell, badge label, legend, number+unit, chart label, caption/title/subtitle) must map back to Text Slot Preflight evidence. This is authoring completeness, not a visual score.
- [x] **Asset Color/Identity Contract** — ImageGen cache identity now includes semantic identity, contour traits, forbidden substitutions and color roles. A color/identity change invalidates cache reuse. Post-hoc tint is not accepted as a substitute for first-pass color correctness.

## Batch B — P1 geometry and asset placement

- [ ] **Geometry Primitive Resolver** — resolve reference geometry to `RECT`, `ROUNDRECT`, `FILLED_ARROW`, `CONNECTOR`, `FREEFORM`, or `IMAGEGEN_COMPLEX`; calibrate primitive parameters and clear unintended theme effects.
- [ ] **Asset-to-Render Coordinate Loop** — retain both alpha-space and PPT slot-space evidence: visible bbox, visual centroid, scale, inset and final-render delta. Repair placement without regenerating correct artwork.

## Batch C — P1 protected repair execution

- [ ] **Protected Repair Planner** — map mismatch -> owner -> parameter delta -> protected neighbors -> patch -> fresh render -> crop regression. A repair may modify only the owning object/relationship unless an explicit dependency is declared.

## Required execution order

`Visual Inventory -> AuthoringPlan -> Text Slot Preflight + Text Coverage -> Asset identity/color generation -> Artifact Tool Build -> Fresh Render -> Responsible Object Repair`

The plan exists to reduce avoidable first-pass errors. Fresh-render comparison and Responsible Object Repair remain the visual authority. SSIM or another universal number must not become the acceptance authority.
