# Knight text-fit absorption — Batch 3

This batch turns TextFit deficit evidence into a deterministic text-slot/layout repair decision. It is additive to the existing `knight-fidelity-port.md` contract and does not replace the Protected Repair Planner.

Run after `text_fit_deck.py` and before accepting a font-size reduction:

```bash
python3 scripts/text_slot_repair_planner.py \
  --text-fit-report PROJECT/text-fit-all-slots.json \
  --authoring-plan PROJECT/authoring-plan.json \
  --output PROJECT/text-slot-repair-plan.json
```

The mandatory repair order is:

`slot bbox -> text margins -> icon/divider reservation -> per-component/card layout -> reference line topology -> line spacing -> font size last`.

`box_deficit_px` is therefore no longer only a report field. It becomes the pixel input to a target-only bbox proposal, converted through the AuthoringPlan source extent. `protected_neighbors` are hard collision blockers. If bbox growth is unsafe, the planner may use only repair headroom explicitly declared in the typography contract; it does not invent margin/spacing thresholds and it does not move an unrelated object.

Repeated components are planned independently. A shared `component_family` never forces one width, divider position, icon slot or font scale onto every card unless the AuthoringPlan explicitly declares that lock.

Every selected action requires fresh render replay. Protected Repair remains the final audit for unrelated-object drift. Font shrink is the last candidate, not the first response to a bad text box.
