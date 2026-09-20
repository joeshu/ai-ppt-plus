# Protected Repair Planner

B6 converts a render mismatch into a constrained repair batch. It resolves one
stable owner from AuthoringPlan, chooses a whitelist of editable parameters,
copies the smallest numeric delta available from B5/Repair Trace and records
the owner's `protected_neighbors` as a no-compensation set.

The planner is not an authoring backend and does not mutate a PPTX. It can
capture owner, protected-neighbor and full-page before/after crops from two
fresh render directories. A batch may be `pending`, `accept`, `reject` or
`rollback`; rollback is a materialized decision reference and never overwrites
the source project.

```bash
python3 scripts/protected_repair_planner.py \
  --authoring-plan project/authoring-plan.json \
  --mismatches run/asset-render-coordinate-report.json \
  --before-render-dir run/before/rendered \
  --after-render-dir run/after/rendered \
  --evidence-dir run/repair-evidence \
  --decision pending \
  --report run/protected-repair-plan.json
```

For `accept`, owner and full-page before/after evidence is required. Every
protected neighbor must also have a before/after crop. The crop comparison is a
local regression check with an explicit tolerance stored in the plan; it is
not an SSIM gate or a universal release score. A material protected-neighbor
regression blocks acceptance unless `--human-override` is present. Placement-only
asset defects keep `regenerate_asset=false` and stay within slot/transform
parameters.
