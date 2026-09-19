# Next-stage fidelity roadmap

This roadmap sequences the next six improvements after the Knight-style short-loop merge. The objective is not more release gates; it is fewer first-pass authoring mistakes and more precise object-level repair.

## Batch 1 — P0 AuthoringPlan

Status: **merged / complete**.

Deliverables:
- versioned `AuthoringPlan` schema and template;
- fail-closed structural validator;
- stable object IDs, semantic roles, implementation type, normalized bbox, parent, z-role, anchors and protected neighbors;
- type-specific contracts for text, geometry, image assets, tables and charts;
- short-loop integration before implementation classification and Artifact Tool Build;
- root/worker Runtime Mirror coverage and package inclusion.

Exit criteria:
- valid plan passes;
- duplicate IDs, invalid bbox, unresolved parent/protected neighbor, parent cycle and missing type contract fail with stable codes;
- no SSIM or visual score is introduced as a blocker;
- package validation, Runtime Mirror and full regression are green.

## Batch 2 — P0 Text Coverage Auditor

Status: **in implementation**.

Goal: every visible formal-text-producing path is traceable to TextGraph/TextFit evidence.

Scope:
- audit native text boxes, rich-text runs, table-cell text, badge labels, chart labels, number+unit components and helper-generated text;
- assign `text_object_id` and `text_fit_evidence_id` to every formal text object;
- compare final PPTX-visible text objects with the planned text ledger;
- flag authoring helpers that bypass Text Slot Preflight;
- preserve exact line topology, baseline rhythm, margins and role hierarchy.

Exit criteria:
- 100% formal text objects have evidence or an explicit exempt semantic class;
- stable failure codes for missing ledger entry/evidence and unexpected formal text;
- regression for CJK rich text, table labels, badges and number+unit layouts.

## Batch 3 — P0 Asset Color/Identity Contract

Goal: make asset identity and color correctness first-pass generation inputs rather than late visual fixes.

Scope:
- semantic identity, contour traits, color-role palette, alpha/safe-zone and provenance in `asset_contract`;
- feed contract into ImageGen asset jobs and cache keys;
- distinguish placement-only failures from identity/color failures;
- reject generic-icon substitution when semantic identity differs;
- retain current true-alpha and no-source-crop fallback policy.

Exit criteria:
- generated asset jobs expose identity/color contract;
- color roles and contour identity survive sheet slicing/repacking;
- placement-only replay does not consume regeneration attempts;
- icon regression demonstrates improved first-pass identity without new score gates.

## Batch 4 — P1 Geometry Primitive Resolver

Goal: choose the best native PowerPoint geometry before authoring.

Scope:
- resolve `RECT`, `ROUNDRECT`, `FILLED_ARROW`, `CONNECTOR`, `FREEFORM`, `ARC/BEZIER`, `TABLE`, `IMAGEGEN_COMPLEX`;
- separate filled arrows from connectors;
- preserve direction-sensitive trapezoids/funnels and rounded-rectangle adjustment;
- require continuous editable freeform/Bezier for compact curves rather than segmented-line approximations;
- clear unintended effects when reference is flat.

Exit criteria:
- resolver produces deterministic primitive choice and parameters;
- geometry choice is written into AuthoringPlan;
- regressions cover filled arrow vs connector, curved path, rounded card and complex-art fallback.

## Batch 5 — P1 Asset-to-Render Coordinate Loop

Goal: close the coordinate gap between transparent asset canvas and final PPT render.

Scope:
- record asset alpha-visible bbox, visual centroid, safe padding and aspect ratio;
- map asset alpha-space to PPT slot-space and final render crop-space;
- emit centroid/scale/visible-bbox deltas for Responsible Object Repair;
- keep adaptive placement and reference-visible-fit behavior;
- diagnose clipping/z-order from final render, not asset contact sheet alone.

Exit criteria:
- every placed independent asset has a coordinate transform record;
- placement-only defect yields numeric delta without forcing regeneration;
- crop replay shows repair convergence without neighbor movement.

## Batch 6 — P1 Protected Repair Planner

Goal: turn Responsible Object Repair into constrained, regression-safe patch planning.

Scope:
- map mismatch -> owner -> editable parameters -> protected neighbors;
- plan smallest responsible parameter delta;
- forbid unrelated-neighbor compensation;
- capture before/after owner crop, protected-neighbor crops and full-page evidence;
- support accept/reject/rollback per repair batch.

Exit criteria:
- repair plan lists editable parameters and protection set;
- local fix cannot be accepted if a protected neighbor materially regresses without explicit human override;
- replay demonstrates targeted title/footer/icon repair without cross-region drift.

## Batch order and promotion policy

Execute strictly in order: `B1 AuthoringPlan -> B2 Text Coverage -> B3 Asset Identity -> B4 Geometry Resolver -> B5 Coordinate Loop -> B6 Protected Repair Planner`.

Each batch remains on an isolated branch/PR until its targeted tests, root regression, editable standalone regression, package validation and Runtime Mirror pass. Do not lower existing hard-correctness requirements and do not reintroduce a universal visual-score release gate.
