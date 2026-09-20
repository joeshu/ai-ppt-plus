# Text Slot Repair Planner

Batch 3 of the Knight text-fit port turns measured `box_deficit_px` and line-topology evidence into a smallest-scope repair decision. It does not add a new visual score gate and it never repairs a text defect by moving an unrelated object.

## Repair order

The planner uses one fixed order:

1. `slot_bbox` — repair the target text box position/size first;
2. `text_margins` — reduce margins only when the AuthoringPlan declares both current and minimum margins;
3. `reserved_icon_divider_space` — use only an explicitly declared typography-contract repair for icon/divider reservation;
4. `component_layout` — use only an explicitly declared per-component/card layout repair;
5. `reference_line_topology` — restore the observed reference line count without changing formal text content;
6. `line_spacing` — change only when current and minimum line spacing are declared;
7. `font_size_last` — use the measured TextFit recommendation only as the final candidate and never below a declared minimum font size.

No numeric margin, spacing or font threshold is invented by the planner. Missing contract evidence means that candidate is unavailable rather than guessed.

## Protected-neighbor rule

`AuthoringPlan.protected_neighbors` are hard blockers for automatic text-box growth. The planner tests deterministic target-only bbox candidates against the slide canvas and those protected bboxes. It does not move a neighbor to create space. When no safe target-only geometry exists, it advances to the next declared repair mechanism.

Repeated cards are repaired per object. A component family does not imply identical text widths, divider positions or icon reservations unless the AuthoringPlan explicitly declares that lock.

## Inputs and output

```bash
python3 scripts/text_slot_repair_planner.py \
  --text-fit-report PROJECT/text-fit-all-slots.json \
  --authoring-plan PROJECT/authoring-plan.json \
  --output PROJECT/text-slot-repair-plan.json
```

The output schema is `ai-ppt-plus/text-slot-repair-plan/v1`. Each action records the measured deficit/topology defect, all ordered candidates, the selected responsible parameter, proposed patch, protected neighbors, and `requires_render_replay: true`.

The output carries `object_id`, `responsible_parameters`, `proposed_patch`, `protected_neighbors`, `repair.classification` and `repair.regenerate_asset=false` as downstream repair evidence. The existing Protected Repair Planner remains the final protected-neighbor checker; Batch 3 does not replace or weaken it. Final acceptance still requires fresh render/local-crop evidence and protected-neighbor review.

## Fail-closed cases

- a defective TextFit slot cannot be mapped to an AuthoringPlan owner;
- source pixel extent is missing, so a pixel deficit cannot be converted to normalized bbox growth;
- no safe/declared candidate exists: the action becomes `manual_layout_review` rather than silently shrinking or moving another object.

## Acceptance

A Batch 3 regression must demonstrate width and height deficit planning, protected-neighbor collision avoidance, declared-margin fallback, topology-only repair, font-size-last behavior, and unknown-owner fail-closed behavior. Root/worker mirrors must remain byte-identical for the planner, schema, reference and test.
