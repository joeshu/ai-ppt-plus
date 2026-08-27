# Failure recovery

Read whenever a gate fails. Input: failed artifact, tool output and latest passing revision. Output: issue record, bounded recovery action, rerun evidence, or manual escalation.

Repair the artifact that owns the failure.

| Failure | Owning artifact | Action |
|---|---|---|
| wrong fact/copy | approved outline/source inventory | stop; correct and reapprove affected rows |
| weak story | outline | revise sequence before visual/PPTX work |
| inconsistent style | design system/intermediate batch | revise tokens or pattern; regenerate affected pages |
| wrong layout | visual intermediate/slide manifest | correct geometry; do not rewrite content |
| clipping/overflow | PPTX object | resize or reflow, rerender, recheck |
| corrupt file | export backend | rebuild from manifest; do not patch blindly |
| missing complex asset | material inventory | create exact placeholder and request asset |
| backend absent | environment | use declared fallback or stop on unsupported contract |

Use at most three automatic repair rounds. Run `scripts/revision_guard.py prepare` before changing a passing PPTX or its manifests, and run `scripts/run_pipeline.py` after each repair batch. A repair passes only after relevant checks rerun. New critical failures require rollback by materializing the last passing snapshot into a separate work directory; do not overwrite the source project automatically. After round three, mark unresolved findings `manual_required`; never suppress them.

| Failure | Recognition signal | Likely cause | Automatic recovery | Human condition | Continue? / report |
|---|---|---|---|---|---|
| unreadable input | parser/nonzero or encryption flag | corrupt/password/unsupported | retry alternate installed extractor; inventory metadata | password, replacement or OCR consent needed | no for critical source; report file/error |
| source conflict | same fact ID has different values/scope | revisions/units/time windows | normalize units and show side-by-side | authority cannot be determined | stop affected pages |
| image generation failure | no image, malformed output, safety/tool error | prompt/tool/context | retry once with same design tokens, then simpler composition | key visual still absent | placeholder only if acceptable |
| visual stage bypassed | no generator evidence or PPT/PPTX render labeled as intermediate | route shortcut/misclassification | return to `design-system-ready`; invoke image generation and create manifest | user explicitly waives image intermediate | do not enter reconstruction while gate applies |
| route conflict | `route-decision.json` authority disagrees with the selected route | stale or mixed visual inputs | rewrite the route decision and rerun `validate_route.py` | user changes the visual authority | block downstream work |
| visual quality below brief | image exists but looks generic, cluttered, low-end or off-context | weak prompt/style drift/model limitation | preserve outline/design tokens; revise one variable and regenerate | alternatives materially change aesthetic direction | remain `visual-draft` |
| visual rejected | focus/order/token checklist fails | weak layout or drift | revise visual artifact, not formal copy | aesthetic alternatives materially differ | return `visual-draft` |
| silent reconstruction redesign | reference zones/order/relationships changed without approval | executor optimized instead of reconstructed | restore approved reference geometry from manifest | user wants a new design direction | return to `reconstruction`; log affected objects |
| prohibited flattening | whole-slide image contains required text/simple elements | shortcut or executor limitation | rebuild text/shapes as editable objects; retain only irreducible raster assets | backend cannot meet editability contract | block delivery or approve reduced scope explicitly |
| editability level failure | object is missing L0-L5 metadata, provenance, acceptance or material request | legacy manifest or optimistic classification | classify each object, derive page summary and rerun manifest/delivery gates | user explicitly accepts a documented degradation | L0/L5/required L4 always block |
| report aggregation failure | required report missing, stale or hidden in project aggregate | manual report collection or changed input | regenerate `report-index.json` and `project-report.json`, then rerun downstream gates | missing evidence needs owner decision | do not claim validated/delivered |
| low-quality complex-asset imitation | missing illustration/logo/photo replaced by fake redraw | asset absent or model guess | remove imitation; create accurate placeholder and material request | user supplies/accepts substitute asset | continue unaffected objects only |
| PPTX creation failure | invalid package or executor nonzero | backend/dependency/manifest | validate manifest, rebuild isolated batch | backend unavailable | stop; never fake file |
| rendering failure | missing renderer/nonzero/page count mismatch | tool/font/corrupt deck | rediscover tools, isolated profile, rerun | tool remains unavailable | block visual completion |
| text overflow | render clipping or heuristic warning | capacity/font substitution | shorten only with outline approval; otherwise resize/reflow | message must change | rerender/recheck |
| style inconsistency | token or deck-strip deviation | context/model drift | reload design system and regenerate affected visuals | exception desired | continue after approval |
| long-context degradation | repeated contradictions/stale versions | chat context growth | close batch and write handoff | hashes conflict | resume from artifacts |
| tool unavailable | executable/import discovery fails | environment gap | use declared compatible adapter | required contract unsupported | stop or explicit degraded scope |
| user confirmation delayed | approval state remains pending | unavailable owner | package decision request and checkpoint | always for locked gate | do not cross gate |

Positive: after a render failure, the command/error is logged and delivery remains blocked. Negative: a screenshot preview is substituted and the deck is called validated. Validate repair-round count, artifact owner, rerun command/result, final state and disclosure.
