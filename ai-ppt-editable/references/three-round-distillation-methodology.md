# Three-round editable reconstruction methodology

This is the default improvement loop for image-led `ai-ppt-editable` work.
It turns a visual reference into a reproducible Pareto search between visual
fidelity and editability. A high image score alone is never evidence of an
editable reconstruction.

## 1. Freeze the evaluation contract

Before authoring, create a unique run directory and record:

- every source page, its page number, dimensions, aspect ratio, and SHA-256;
- the page-to-reference mapping and the authoritative formal-text source;
- the selected child-skill entrypoint, backend, font directory, and renderer;
- the expected page count and panel count derived from the actual manifest.

Preserve the source and all previous candidates. Never reuse a filename as a
substitute for a hash, and never overwrite a prior run directory. If the
reference is not 16:9, preserve its ratio unless the user explicitly changes
it.

## 2. Run three intentionally different rounds

### Round 1 — visual baseline

Build the fastest faithful visual candidate, commonly a full-page raster. Use
it to establish composition, ratio, palette, hierarchy, and a pixel/blurred
layout baseline. Then audit the object types.

If the candidate contains one whole-slide picture and no native formal text,
label it `visual-diagnostic-only`, even when its SSIM is excellent. This is a
valid diagnostic baseline and an invalid editable deliverable. A visual-best
full-page image or panel-raster candidate must never be promoted to the final
PPTX merely because its pixel score is higher.

### Round 2 — semantic decomposition

Split the page into independently movable semantic regions: panels, frame
parts, logos, illustrations, and page furniture. Keep formal text out of a
panel whenever its wording is known. Every extracted panel gets a record with
`panel_id`, `file`, `source_bbox`, `asset_size`, treatment, baked-text status,
`raster_text_audit`, native `text_layer_ids`, and current SHA-256. A panel may
contain only a text-free substrate; when its source region contains formal copy,
the audit must point to the native text objects. The panel manifest must be
approved before it is used as delivery evidence.

Count panels from the manifest after all pages are loaded; do not hand-count
from memory. A two-page example may have seven panels on each page, for a
total of fourteen. This round is usually the `visual-best` candidate.

### Round 3 — editable distillation

Replace known formal text with native text boxes/runs, and replace simple
headings or containers with native shapes. Preserve complex artwork as
independent raster/vector assets when reconstructing it natively would reduce
fidelity. Embed the task-local CJK font and keep line breaks, emphasis, and
text bboxes explicit.

Run the strict image-to-editable contract before composition. If any complex
正文 panel still contains formal text, stop the candidate and repair the panel;
do not call it editable-best or hide it behind a high visual score.

Build the object manifest with the panel manifest, so each panel resolves to a
project-relative path and carries source-bbox/hash evidence. Then build the
slide manifest and the handoff, validation, and issue-log artifacts. The
result is the `editable-best` candidate. It is expected that replacing raster
text with native text can reduce pixel scores; compare both candidates instead
of hiding that tradeoff.

## 3. Repair by owner, then distill the fix

Use the first failing gate to choose the repair owner:

| Failure | Owner | Durable fix |
| --- | --- | --- |
| wrong page count or ratio | intake/layout | source-page map and ratio guard |
| whole-slide picture or baked formal text | object plan | split semantic panels and promote formal text to native objects |
| missing bbox, path, or hash | provenance | panel manifest plus object-manifest build with the panel manifest |
| font fallback or clipping | typography/font | explicit CJK font directory, embedding, render, and recheck |
| visual drift | layout/text | repair the affected region, not the reference or copy |
| report missing/stale | project handoff | generate slide manifest, handoff, validation report, and issue log; bind reports to the deck hash |
| package mismatch | invocation | run the standalone `ai-ppt-editable/scripts/run_pipeline.py` when validating this child skill |

After each repair, rerun the affected check, then rerun the full multi-page
DAG. Keep the failed report beside the passing report: failure evidence is
part of the method, not noise to delete.

## 4. Use two gates and one human decision

The technical gate is the intersection of:

1. source/page/ratio and render validity;
2. native-object and independent-panel coverage;
3. source bbox/path/hash provenance;
4. CJK/font delivery and fresh render evidence;
5. pixel comparison and semantic-object comparison;
6. a fresh report bundle bound to the current deck hash.

The human decision chooses the delivery candidate on the visual-best /
editable-best frontier and confirms literal text, panel movement, and target
editor rendering. Technical pass must remain distinct from human approval.

## 5. Generalization rule

Every reusable failure becomes one of: a deterministic regression test, a
manifest/schema contract, or a narrowly scoped adapter. Do not add a second
reconstruction engine for a single reference. Practice images and generated
reports stay outside the skill package unless deliberately promoted as a
versioned golden fixture.

## 6. Self-driving policy

The loop may automate deterministic work, but it must emit one explicit next
action rather than silently retrying forever. Use
`scripts/distillation_scheduler.py` after each cycle. It reads the latest
cycle report and a bounded history, then chooses safe repair, human approval,
more-case collection, external training, or escalation.

The scheduler records the responsible owner, repair round, attempts used, and
remaining budget. Automatic repair is isolated and reversible; human approval,
model promotion, and release eligibility remain false in every machine-
generated decision. This converts repeated practice into a controlled active-
learning queue instead of an unbounded retry loop.
