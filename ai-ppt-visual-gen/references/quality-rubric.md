# Quality rubric

Read before validation, repair prioritization and delivery. Input: structural/render reports, manifests, issue log, visual comparison diagnostics, OCR readback where available and human ratings. Output: severity assignments, score and release decision.

- `blocker`: file missing, corrupt, cannot open/render, wrong slide roster, or authoritative content invented.
- `critical`: major content loss, wrong formal data, unreadable text, severe overlap/overflow, prohibited full-slide flattening, or unapproved redesign of a reference-led page.
- `major`: inconsistent style, weak hierarchy, notable crop/spacing/font issue, or missing source/notes/link requirement.
- `minor`: cosmetic deviation that does not impair meaning or operation.

Release requires: valid PPTX package; expected slide count and ratio; every page rendered; no open blocker/critical issue; approved formal content represented; required editability met; no `L0`/`L5`, no required `L4`, and no rasterized formal content; `L3` requires explicit human editability confirmation and `L2` requires disclosure; reference-led pages preserve approved hierarchy/structure/spatial relationships; every rendered page has a matching reference comparison when a multi-page reference set is supplied; page/deck reports present; a valid `project-report.json` must cover every required report in `report-index.json` with fresh hashes; unresolved major/minor issues disclosed with owner and action.

Machine checks prove package and geometry facts. They cannot prove narrative value, visual quality, semantic correctness, or brand appropriateness without model/user review.

Score 0–100: content/traceability 30, narrative 20, visual consistency/reference fidelity 20, editability 15, structural/render reliability 15. Default delivery threshold is 80 and all blocker/critical findings must be closed; a high score never overrides a blocker.

Positive: 86/100 with no blockers and explicit human sign-off passes. Negative: 92/100 with an untraceable revenue number passes. Common failures are score inflation and missing evidence; validate every criterion against an artifact/report reference.
