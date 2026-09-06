# Fresh-12: true image → editable PPTX evaluation

Fresh-12 is the capability test for **new image → high-fidelity, fully editable PPTX**. It is intentionally separate from `evals/case-replay-12`, which remains a historical regression/control package.

## Why this exists

The historical 12-case runner is useful for deterministic engine regression, but it is not a valid end-to-end capability proof: its reference PNGs are reused as visual authority and its candidate decks are authored by case-specific `build_layout(...)` code. Fresh-12 removes both shortcuts.

## Non-negotiable rules

1. All 12 source images must be generated again for the current run through the native image-generation path used by `ai-ppt-visual-gen`.
2. `evals/case-replay-12/visual/`, `references/`, and `image2pptx_runs/` are forbidden authoring inputs. Historical material is allowed only after Fresh-12 is complete, for retrospective comparison.
3. During reconstruction, the **only visual authority** is the current run's `generation/fresh-original.png`. `case-suite.json` may supply the generation prompt and post-hoc semantic expectations; it must not provide layout geometry or directly author the PPTX.
4. Every case must retain at least these four visible proofs: fresh original image, current PPTX render, pixel-difference image, and actual editable-object evidence. The PPTX and provenance reports are retained beside them.
5. Current-run PageGraph plus PageGraph provenance is mandatory evidence that the editable reconstruction came from image analysis rather than a case-specific layout shortcut.
6. No 12/12, no capability verdict. Missing evidence produces `INCOMPLETE`; a complete run with a failed gate produces `FAIL`; only 12/12 passes produce `PASS`.

## Evidence layout

```text
<RUN>/
  fresh12-run.json
  fresh12-evaluation.json
  fresh12-capability-verdict.json
  cases/<case-id>/
    generation/
      request.json
      provenance.json
      fresh-original.png
    reconstruction/
      input.json
      editable.pptx
      pagegraph.json
      pagegraph-provenance.json
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

`generation/provenance.json` must bind `run_id`, `case_id`, `generator_skill`, `prompt_sha256`, a unique `generation_id`, `generated_at`, and the SHA-256 of `fresh-original.png` (`generated_image_sha256`, `source_image_sha256`, or `sha256`).

`reconstruction/input.json` is the anti-shortcut contract and must contain:

```json
{
  "run_id": "<same run id>",
  "request_id": "<unique current-run visual-reconstruction request id>",
  "case_id": "<case id>",
  "visual_input_authority": "fresh-image-only",
  "source_image_sha256": "<sha256 of generation/fresh-original.png>",
  "layout_source": "image-analysis",
  "case_spec_usage": "generation-and-posthoc-qa-only"
}
```

`pagegraph-provenance.json` must use schema `ai-ppt-plus/page-graph-provenance/v1`, repeat the same reconstruction `request_id`, declare producer task `visual-reconstruction`, and hash-bind both the current fresh source image and current `pagegraph.json`.

## Run sequence

Prepare a clean run and 12 image-generation requests:

```bash
python evals/fresh-12/fresh12.py prepare \
  --run-dir .distillation/fresh-12/<run-id> \
  --run-id <run-id>
```

For each case, generate a **new** image from `generation/request.json`, save it as `generation/fresh-original.png`, and save generation provenance. Reconstruct the PPTX **from that image only**, then save the reconstruction input contract plus current-run `pagegraph.json` and `pagegraph-provenance.json`.

Collect render, diff, and editable-object evidence for each reconstructed PPTX:

```bash
python evals/fresh-12/fresh12.py collect \
  --run-dir .distillation/fresh-12/<run-id> \
  --case-id <case-id> \
  --pptx <current-run-output.pptx> \
  --font-dir ai-ppt-editable/assets/fonts
```

Run the structural/current-run preflight. This is useful for evidence completeness, but is **not** the final high-fidelity capability verdict:

```bash
python evals/fresh-12/fresh12.py verify \
  --run-dir .distillation/fresh-12/<run-id>
```

Run the authoritative final capability gate:

```bash
python evals/fresh-12/capability_gate.py \
  --run-dir .distillation/fresh-12/<run-id> \
  --blurred-layout-ssim-min 0.90 \
  --global-ssim-min 0.82 \
  --pixel-fidelity-score-min 0.80 \
  --strict
```

The final capability gate rejects a fresh image whose hash equals a known historical `*reference*.png`, rejects duplicate fresh images across the 12 cases, verifies generation time/prompt/hash binding, rejects forbidden historical authoring paths/backends, validates current-run PageGraph provenance, verifies source/PPTX/render/diff hash binding, rejects full-slide flattening, requires native text/editable shapes, and enforces explicit source-vs-render fidelity thresholds.

The default Fresh-12 fidelity gates are deliberately strict starting points: blurred-layout SSIM ≥ 0.90, global SSIM ≥ 0.82, and pixel-fidelity score ≥ 0.80. The final verdict records the exact thresholds used so future rounds remain comparable.

## Interpreting results

- `INCOMPLETE`: fewer than 12 cases have the required current-run evidence. `capability_judgement_allowed=false`; do **not** claim improvement or regression.
- `FAIL`: all 12 are complete, but at least one provenance, fidelity, or editability gate failed. This is still a valid capability measurement and identifies the cases that remain weak.
- `PASS`: all 12 are complete and pass every mandatory gate. Only then should the new round be described as meeting the Fresh-12 high-fidelity target.

Historical comparison is eligible only after 12/12 is complete. The historical suite remains valuable as a control, but it never enters Fresh-12 generation or authoring inputs.
