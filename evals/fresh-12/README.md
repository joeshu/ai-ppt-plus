# Fresh-12: true image → editable PPTX evaluation

Fresh-12 is the capability test for **new image → high-fidelity, fully editable PPTX**. It is intentionally separate from `evals/case-replay-12`, which remains a historical regression/control package.

## Why this exists

The historical 12-case runner is useful for deterministic engine regression, but it is not a valid end-to-end capability proof: its reference PNGs are reused as visual authority and its candidate decks are authored by case-specific `build_layout(...)` code. Fresh-12 removes both shortcuts.

## Non-negotiable rules

1. All 12 source images must be generated again for the current run through the native image-generation path used by `ai-ppt-visual-gen`.
2. `evals/case-replay-12/visual/`, `references/`, and `image2pptx_runs/` are forbidden authoring inputs. Historical material is allowed only after Fresh-12 verification for retrospective comparison.
3. During reconstruction, the **only visual authority** is the current run's `generation/fresh-original.png`. `case-suite.json` may supply the generation prompt and post-hoc semantic expectations; it must not provide layout geometry or directly author the PPTX.
4. Every case must retain at least these four visible proofs: fresh original image, current PPTX render, pixel-difference image, and actual editable-object evidence. The PPTX and provenance reports are retained beside them.
5. No 12/12, no capability verdict. Missing evidence produces `INCOMPLETE`; a complete run with a failed gate produces `FAIL`; only 12/12 passes produce `PASS`.

## Evidence layout

```text
<RUN>/
  fresh12-run.json
  fresh12-evaluation.json
  cases/<case-id>/
    generation/
      request.json
      provenance.json
      fresh-original.png
    reconstruction/
      input.json
      editable.pptx
    render/
      pptx-render.png
      render-report.json
    diff/
      diff.png
      visual-compare.json
    evidence/
      editable-objects.json
      pptx-inspection.json
      fresh12-case-evidence.json
```

`generation/provenance.json` must bind `run_id`, `case_id`, `generator_skill` and the SHA-256 of `fresh-original.png` (`generated_image_sha256`, `source_image_sha256`, or `sha256`).

`reconstruction/input.json` is the anti-shortcut contract and must contain:

```json
{
  "run_id": "<same run id>",
  "case_id": "<case id>",
  "visual_input_authority": "fresh-image-only",
  "source_image_sha256": "<sha256 of generation/fresh-original.png>",
  "layout_source": "image-analysis",
  "case_spec_usage": "generation-and-posthoc-qa-only"
}
```

## Run sequence

Prepare a clean run and 12 image-generation requests:

```bash
python evals/fresh-12/fresh12.py prepare \
  --run-dir .distillation/fresh-12/<run-id> \
  --run-id <run-id>
```

For each case, generate a **new** image from `generation/request.json`, save it as `generation/fresh-original.png`, and save generation provenance. Reconstruct the PPTX **from that image**, then save the reconstruction input contract above.

Collect render, diff, and editable-object evidence for each reconstructed PPTX:

```bash
python evals/fresh-12/fresh12.py collect \
  --run-dir .distillation/fresh-12/<run-id> \
  --case-id <case-id> \
  --pptx <current-run-output.pptx> \
  --font-dir ai-ppt-editable/assets/fonts
```

Finally verify all 12 cases:

```bash
python evals/fresh-12/fresh12.py verify \
  --run-dir .distillation/fresh-12/<run-id> \
  --strict
```

The verifier rejects a fresh image whose hash equals a known historical `*reference*.png`, rejects forbidden historical authoring paths/backends in reconstruction provenance, verifies hash binding among source/PPTX/render/diff evidence, rejects full-slide flattening, requires native text/editable shapes, and requires the current source-vs-render visual comparison to pass.

## Interpreting results

- `INCOMPLETE`: fewer than 12 cases have the required current-run evidence. Do **not** claim improvement or regression.
- `FAIL`: all 12 are complete, but at least one provenance, fidelity, or editability gate failed. The failed cases identify what the skill still cannot reconstruct reliably.
- `PASS`: all 12 are complete and pass the mandatory gates. Only then may historical results be compared to quantify improvement across skill revisions.

The historical suite remains valuable after this point as a control, but it never enters Fresh-12 authoring inputs.
