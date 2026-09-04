# Case replay visual-fidelity gate

The 12-case suite separates a native-object control from a real reference
reconstruction. A control can prove that cards, tables, charts and textboxes
are technically editable; it cannot be called a candidate when its rendered
composition is materially different from the approved reference.

## Candidate contract

Every promoted candidate must be declared as `candidate_origin:
reference-reconstruction` and carry `reference-reconstruction-evidence.json`
beside the PPTX. The evidence must bind the exact reference SHA-256 and record:

- the final imagegen asset manifest, stable IDs and independent movable asset
  count, plus the text-free boundary for icons, illustrations and complex
  gradients;
- a resolved font manifest, positive font size and source bounding box
  (`[x, y, width, height]`) for every formal text item, including run-level
  style data when a text item is mixed-style; and
- the layout/text/object manifests used to author the PPTX.

Formal text remains native. A whole-slide image, a screenshot used as a
semantic substitute, generic placeholder text, or an unapproved internal QA
label is not a reconstruction.

## Automated visual gate

The case suite declares the minimum raw-slide comparison thresholds:

| Metric | Minimum |
| --- | ---: |
| `global_ssim` | `0.40` |
| `blurred_layout_ssim` | `0.60` |
| `pixel_fidelity_score` | `0.82` |

All three metrics, reference binding, asset evidence, source-bound typography,
formal-text exactness and native/mutation checks are required in strict mode.
The metrics are a blocker and not a substitute for human review. A candidate
that misses a threshold remains blocked even if its native object counts pass.

## Replay commands

The default 12-case runner emits synthetic native controls for diagnostics.
They are deliberately non-promotable. A real replay supplies a directory with
one PPTX per case (`<case_id>.pptx` or `<case_id>/editable.pptx`) and the
reconstruction evidence/manifests:

```bash
python evals/case-replay-12/run_replay_suite.py \
  --candidate-root PROJECT/optimized-candidates \
  --output-dir PROJECT/qa/case-replay-12 \
  --strict
```

Missing candidate evidence, low layout similarity, wrong fonts or missing
imagegen assets must stop promotion and identify the owning repair area.
