# Fresh-12 R1 — Case 01 invalidation

Case: `route-editable-default-01` / 政企客户增长作战舱

Status: **INVALID — DO NOT COUNT**

The first attempt is not a valid Fresh-12 sample and must not be used in the final capability verdict.

## Why it is invalid

The attempt bypassed the checked-in `ai-ppt-editable` reconstruction workflow and directly authored a new PPTX with ad-hoc `python-pptx` code. That violates the current skill contract and does not establish true image → high-fidelity all-element editable PPTX capability.

Missing / noncompliant gates include:

- E0 package / routing / perfect-sync / backend / font preflight was not executed as required.
- E1 visible-object inventory and canonical editable-object plan were not built from the reference.
- E2 reference decomposition did not run the required reference-fidelity, asset-boundary, imagegen-final-asset, panel/text/chart contracts.
- Icons / gradients / complex art were not rebuilt through the required independent native-imagegen asset path.
- E3 composition did not use the checked-in `ai-ppt-editable` composer / synchronized perfect-first backend and canonical object manifests.
- E4 did not run the complete semantic object audit, strict geometry/type/manifest audit, visual lock, font/text layout/overflow/overlap/route/preview consistency gates.
- E5 technical repair / re-render / rerun gate loop was not performed.
- The earlier editable-object count and pixel metrics are therefore diagnostic only and are not valid Fresh-12 evidence.

## User review correction

The user explicitly rejected the first attempt because it did not follow the skill-standard steps and did not achieve the required image → high-fidelity all-element editable PPTX behavior. Any earlier `ACCEPTED_WITH_MACHINE_GATE_FAIL` note is superseded and must not be treated as acceptance.

## Required restart

Restart case 01 from the current-run fresh source image only if its generation provenance remains trustworthy; otherwise regenerate the fresh source. The reconstruction itself must be rerun from zero through the checked-in skill flow:

`E0 intake/preflight → E1 inventory/object plan → E2 decomposition + independent imagegen assets → E3 checked-in composition → E4 full render/QA/visual-lock/semantic-object audit → E5 repair/handoff`.

The case remains incomplete until a new evidence bundle is produced by that flow. No human override can convert the invalid attempt into a benchmark PASS.
