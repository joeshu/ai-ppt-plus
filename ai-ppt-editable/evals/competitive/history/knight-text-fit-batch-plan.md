# Development history: Knight text-fit absorption batches

This file records the staged port into `ai-ppt-editable` so the Knight text-fit work is not confused with the separate B1–B6 fidelity roadmap.

- Batch 1 — TextFit Core: CJK/mixed-run wrapping, target size, line topology and measurable box deficit.
- Batch 2 — TextSpec/TextRunSpec + Text Coverage: content/run trace, number+unit binding and formal-text coverage evidence.
- Batch 3 — Text-slot/layout repair: convert `box_deficit_px` into target-only repair decisions; geometry/margins/dependencies/topology/line spacing before font shrink.
- Batch 4 — Visual hierarchy + render feedback: `TextSpec -> TextFit -> PPTX runs -> fresh render -> text-region crop -> hierarchy/position review -> targeted repair`.
- Batch 5 — Real-case replay + complete CI: freeze representative cases and verify the absorbed text-fit behavior without regressing the existing Geometry Resolver, Asset-to-Render Coordinate Loop or Protected Repair Planner.

The two roadmaps are independent. Existing fidelity-roadmap B5/B6 are baselines to protect, not future Knight text-fit batches.
