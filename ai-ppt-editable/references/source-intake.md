# Source intake

## Use and timing

Read at `intake`, on added sources, and before resuming a project. Supported inputs are PDF, DOCX, Markdown/text, CSV/XLSX, PPT/PPTX, images and project/meeting files that available extractors can read.

Create `source-inventory.json` with one record per source: `id`, `path_or_url`, `kind`, `size`, `sha256`, `readable`, `extractor`, `pages_or_sheets`, `language`, `topics`, `fact_ids`, `data_ids`, `conflicts`, `gaps`, and `notes`. Preserve originals and never overwrite them.

Create `deck-brief.md` with purpose, audience, setting, desired decision, duration/page target, language, output format, editability, deadline, brand constraints, authoritative-source order, known risks, and open questions.

- Confirm purpose, audience, use setting, delivery format, language, and editability.
- Detect unreadable, encrypted, corrupt, and unsupported files.
- Assign stable fact/data identifiers and provenance.
- Separate explicit facts from model inference. Label engineering assumptions and `待验证` items.
- Detect inconsistent value, unit, date, scope, and duplicate versions.
- Stop when a missing item changes the claim, audience fit, scope, or safety. Otherwise record a declared default.

Prefer user-confirmed facts and designated official data over inferred text. A reference image is visual evidence, not authority for wording, chart values, hidden objects, or authoring history.

When PPT Master is installed, its source conversion and image-analysis utilities may be invoked from its own directory after its documented integrity check. Keep AI PPT Plus inventory and gates authoritative; do not mutate PPT Master or copy its scripts.

The supplied WeChat URL could not be retrieved in the implementation environment; article-specific claims remain `待验证`. The staged A–G method and contracts are user-supplied requirements. PPT Master reuse claims must be checked against the installed version at runtime.

Multiple files are grouped by subject/time/authority, deduplicated by hash, and never merged by silently choosing a winner. Record fact as `fact`, attributed interpretation as `opinion`, model synthesis as `inference`, and implementation choice as `engineering_assumption`. Sensitive signals are reported by category without echoing secrets.

Positive example: two metric files disagree, so both values, scope/date and authority are logged and the page is blocked. Negative example: choose the larger value because it produces a stronger story.

Input: original paths/URLs and brief. Output: inventory, extracted text references, fact/data IDs, conflict/gap list. Common failures are password protection, scan-only PDF, corrupt OOXML, unsupported embeds and sensitive data. Validate existence, hashes, readability, extraction coverage and conflict disposition; request OCR or owner confirmation when needed.
