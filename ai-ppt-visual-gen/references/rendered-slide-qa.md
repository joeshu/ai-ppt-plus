# Rendered slide QA and regression rules

This guide is reusable for raster-generated slides. A polished image and a
passing plan/evidence validator do not prove that the image contains the exact
approved copy or communicates one relationship only once.

## Findings abstracted from the five-page regression

- A formal sentence can disappear while a shortened paraphrase appears. This
  is a copy-coverage failure, not a typography preference.
- The same sentence can appear as a large conclusion and again as a small
  label. This usually comes from asking the model to render both
  `content_model` and `formal_text` independently.
- A process can be shown once as five numbered nodes and again as grouped
  `01—02 / 03—04 / 05` summaries. Correct labels can still create competing
  reading paths and weaken the primary relationship.
- Chinese punctuation, spacing and full-width glyphs may be normalized by the
  image model. “Looks close” is not exact-copy evidence.
- A lower rail is valid when it carries a real case, action or evidence role.
  A repeated decorative bottom bar is a layout defect. This decision is
  semantic and page-local, not a universal footer rule.

## General rules

1. Declare one `copy_contract.render_copy` list per page. It is the only
   visible-copy authority and must be deduplicated. `formal_text` proves source
   authority; `content_model` describes slots and capacity.
2. Set `exact_once: true`. A sentence may repeat only when the plan explicitly
   records a new semantic role; otherwise use an icon, connector or different
   visual treatment rather than a second copy.
3. Set a total-character budget appropriate to the declared viewing distance.
   If the budget is exceeded, shorten, merge or split content before asking an
   image model to typeset it.
4. Declare `representation_policy`. One primary relationship gets one primary
   encoding. A secondary rail, inset or tag is allowed only when it adds a new
   decision cue, evidence item or constraint.
5. Use `visual_assertions.readback_scope: all-render-copy` when exact page copy
   matters. OCR failures remain manual review; OCR misses remain blockers.
6. Inspect each full-resolution page and the deck strip. Check title, all
   must-render copy, punctuation, duplicate sentences, reading path, empty or
   overcrowded zones, accidental footer bands and unapproved labels.

## Retry decision

Retry only the failed slide. Typical retry triggers are missing/rewritten copy,
duplicate encoding, collapsed hierarchy, unreadable body text, or a closure
treatment that became a repeated banner. Do not redraw text over the raster
after generation and do not regenerate accepted pages merely to make the deck
feel more uniform.
