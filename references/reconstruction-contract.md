# PPTX reconstruction contract

## Purpose and entry gate

Read before turning an approved visual intermediate, reference slide image or screenshot into PowerPoint. This is an engineering-reconstruction contract: reproduce the reference's layout, hierarchy and visual relationships as a genuinely editable PPTX. It is not permission to redesign the page. The route must first be recorded in `route-decision.json`: `reference-reconstruction` uses an approved reference as visual authority and may skip image generation; `visual-creation` uses a generated visual intermediate and must retain its generation evidence. These routes are mutually exclusive per page/batch.

If the user says “先讨论任务，不要立即生成”, acknowledge this contract, confirm inputs and wait. Do not create the PPTX until the user begins page execution or confirms the reference page. Required inputs are the page reference, formal-text authority (`approved_outline`, `user_transcription`, or `transcription_pending_confirmation`), available original assets and any ratio/font/brand constraints.

Preserve, in order: information hierarchy → page structure → spatial relationships → typography metrics → graphics/icons → decoration.

## Hard requirements

- Default to 16:9 unless the confirmed design system says otherwise.
- Use real editable text boxes for every title, body paragraph, label, note and number. Never bake required text into a whole-slide image.
- Rebuild simple cards, lines, color blocks, tags, process nodes and geometry with PowerPoint native shapes or editable vector objects whenever reliable.
- Use editable charts or traceable data where supported; otherwise retain an exact verified graphic and disclose reduced editability.
- All icons, decorations and artistic typography in a reference reconstruction must go through the imagegen B4 asset-sheet route and B5 cutout/split QA. A small generic icon may be semantically equivalent, but it still must be generated through that route; supplied originals may guide the edit target but may not bypass it.
- Insert every independently separable image as an independent picture object so it can be moved, cropped or replaced later. Do not merge separable elements into a full-page screenshot.
- Do not force a low-quality redraw of complex illustration, photography, texture, logo or specialized visual material. If the original asset is supplied, place it at the reference position. If it is missing, create a precisely sized and positioned placeholder and emit a material request describing the required asset.
- When both outline and reference image exist, the approved outline owns formal wording, numbers and facts; the reference image owns layout, hierarchy, spatial relationships and design language. Generated or OCR text from the image never overrides the outline.
- Do not generatively recreate charts, tables, logos, names, numbers or unreadable text as if they were verified originals.
- Do not redesign, improve, simplify or reorder an approved page during reconstruction unless the user explicitly changes the brief.
- Save, open, render and inspect every completed page; required text and simple graphic objects must remain directly editable.

## Per-page execution protocol

1. **Analyze the reference:** record canvas ratio, margins, major zones, alignment anchors, content hierarchy, reading path, focal point, typography roles, colors and asset bounds.
2. **Create an object decomposition plan:** map each visible element to one of `editable_text`, `native_shape`, `editable_vector`, `editable_chart`, `independent_image`, `extracted_icon`, `decorative_art`, `traceable_static_graphic`, or `documented_placeholder`; use `flattened_full_slide` and `unresolved` only to produce a blocking finding. For icons/decorations/artistic typography, first apply `references/icon-asset-protocol.md`, then assign the corresponding `L0`–`L5` level, provenance, required-for-delivery flag and human-review flag. See `references/editability-levels.md`.
3. **Resolve authority:** take formal text/data from the approved outline; use the image only for visual relationships. Log conflicts before implementation.
4. **Engineer the page:** reproduce confirmed geometry and layers without substituting a different design system.
5. **Render and compare:** compare reference and render for hierarchy, page structure, spatial relationships, typography and graphics in the fixed priority order.
6. **Verify editability and package health:** confirm the file opens, the page renders, text is selectable, simple elements are independent/native, replaceable images are separate, and no required region is silently flattened. For icon-bearing pages, run `scripts/validate_icon_assets.py icon-asset-manifest.json` and `scripts/audit_icon_layers.py icon-asset-manifest.json`; both are required gates. The manifest must prove B4 source-vs-frame exclusion and B5 cutout/split evidence, with a frame preview and contact sheet. Inspect alpha/contact-sheet QA and compare icon count, edge integrity, centers, size and duplicates in the rendered page. The portable B4/B5 tools are `probe_palette.py` → `chroma_key.py` (`frame-safe`/`icon-safe`) → `slice_grid.py` → `placement_qa.py`; keep the frame intact unless frame splitting is explicitly requested.

For a multi-page reference set, keep a one-to-one `slide-N` mapping between each reference image and rendered page. A first-page comparison is never sufficient evidence for a multi-page reconstruction; missing or mismatched reference pages block the batch and must identify the affected slide number.

The `slide-manifest.json` page entry must record `reference_image`, `formal_content_source`, `object_plan`, `objects[]`, the derived `editability` summary, `editable_object_counts`, `raster_object_counts`, `placeholders`, `substitutions`, `tradeoffs`, `render_path`, and `review_status`. New projects must validate it with `scripts/validate_manifest.py --require-editability`.

## Allowed substitution and degradation

Allowed without redesign: a semantically equivalent generic vector icon only after the mandatory imagegen B4/B5 route; a metrically compatible font when the specified font is unavailable and substitution is disclosed; a traceable static chart image only when editable-chart support is unavailable and the user accepts the explicit `L3` degradation. Independent supplied photos/textures/icons are `L2` only when their provenance and replacement path are recorded. Missing complex assets are `L4` placeholders, not invented artwork.

Not allowed: a whole-slide background screenshot as the sole implementation (`L0`); invented complex artwork; low-quality imitation of a missing key visual; silent removal of content; changing the narrative to fit an easier layout; claiming full editability when required text or simple shapes are rasterized; treating a high aggregate editability ratio as permission to ignore an `L0`, `L5` or required `L4` object.

When reliable reconstruction is impossible, stop the affected object—not the whole project when isolation is safe—place an accurate placeholder, record the blocking reason and request the exact missing asset. Do not manufacture a pass.

Discover PPT Master only through `scripts/probe_environment.py` and an explicit `PPT_MASTER_SKILL_DIR` containing `SKILL.md`. Run its documented integrity guard before its scripts. Prefer its SVG-to-PPTX, image analysis, finalization, visual review, and postflight capabilities only after each selected script and `--help` is verified. When probe returns unavailable, select the host `artifact-tool + LibreOffice/Poppler` backend and record the limitation.

If unavailable, use the host presentation runtime for native PPTX authoring and LibreOffice only when its executable is actually discovered for rendering. Do not use `python-pptx`. This fallback does not claim identical SVG mapping, animation, narration, or exact reconstruction fidelity. Mark unsupported capabilities `待验证` or `manual_required`.

Input: approved outline or confirmed transcription, design system, approved visual/reference manifest, assets and provenance. Output: editable PPTX, object-level slide manifest, placeholder/material requests, render comparison and tradeoff log.

Positive example: a timeline mockup becomes native text boxes, lines and nodes while its wording comes from the approved outline. Negative example: the mockup is inserted as one full-slide bitmap and called editable.

Common failures are font substitution, grouped raster content, missing provenance, whole-slide flattening, low-quality fake assets, icons swallowed by the frame layer, duplicate frame/icon assets, residual cutout backgrounds, edge-touch truncation and silent redesign. Validate object mix, icon asset roster, alpha/split QA, formal-copy diff, package openability, page renders, reference comparison, placeholder log and user-approved exceptions.
