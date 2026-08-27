# Outline table contract

## Use and timing

Read after source analysis and before any visual or PPTX generation. It turns narrative decisions into the authoritative formal-content artifact.

## Input and output

Input: deck brief, source inventory, narrative strategy, user constraints. Output: versioned CSV/XLSX with one row per formal slide.

## Required fields

| Field | First author | Lock rule |
|---|---|---|
| `slide_no` | AI | unique positive integer; renumber only with recorded revision |
| `section` | AI | user approves sequence |
| `title` | AI | locked after approval |
| `core_message` | AI | one testable sentence; locked after approval |
| `purpose` | AI | why the page exists |
| `body_content` | AI | formal text/data; approved text outranks visuals |
| `data_sources` | AI/user | URI/file/page/cell or `待验证`; never blank for factual claims |
| `visual_type` | AI | one supported page type; may change only before visual approval |
| `audience_takeaway` | AI | one sentence |
| `owner_notes` | user | explicit comments/decisions |
| `status` | AI/user | `draft`, `needs_user`, `approved`, `blocked`, `superseded` |
| `revision_reason` | editor | required after an approved row changes |

AI fills the first draft except `owner_notes`. The user confirms order, core messages, critical facts and statuses. Any approved-row change creates a new version and records reason, editor and time in the companion handoff/change log.

## Executable rules

1. Slide numbers are continuous and unique within the formal deck; appendix numbering may use a separately declared scheme.
2. A page cannot be `approved` with empty title, purpose, core message, body, takeaway or unresolved critical fact.
3. Generated visual text never updates `body_content`.
4. User comments remain verbatim in `owner_notes`; the AI proposes a revision in a new version.
5. Run `scripts/validate_outline.py`; narrative approval requires every non-superseded row to be `approved`.

## Examples

Positive: slide 4 says “Conversion rose 18% after onboarding simplification,” cites `metrics.xlsx!Q2!B7:C7`, states comparison purpose, and is approved by the owner.

Negative: slide 4 copies “+25%” from a generated mockup, leaves `data_sources` blank, and marks itself approved.

## Failures and validation

Common failures: duplicate numbers, paragraph-sized core messages, missing sources, stale approvals after edits, and visual copy overwriting formal copy. Validate schema, numbering, source markers, statuses and version metadata; unresolved critical failures return to `outline-review` or `revision-required`.
