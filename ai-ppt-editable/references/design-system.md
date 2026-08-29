# Design system contract

## Use and timing

Read after narrative approval and before visual drafts; reread on every resumed batch or new page.

## Input and output

Input: approved outline, brand rules, audience/context, reference images and available fonts. Output: `design-system.yaml` plus declared exceptions.

## Executable rules

Persist ratio, grid, margins, fonts and fallback chain, size hierarchy, colors, chart palette, spacing scale, radius, shadows, borders/lines, icons, image treatment, backgrounds and components. Read `references/font-portability.md` for every Chinese deck. Run `scripts/probe_fonts.py` before selecting a font family with the task-local bundled font directory; if a requested Chinese family does not resolve, record `当前环境不支持` and block Chinese rendering sign-off. Define page families and focus rules for priority pages. A new page must either use existing tokens/components or document an approved exception. For reference-led Chinese pages, record both `source_font_family` (when known) and `render_font_family`, then calibrate title/module/body sizes against normalized rendered ink bboxes; keep those scale factors in `typography-calibration.json` instead of silently fixing one slide. Missing brand/font information is an explicit default or `待验证`, never an implied fact.

Deck-wide consistency outranks a locally attractive deviation. Use one visual model/context where feasible; on session change, load this file before generating visuals.

## Examples

Positive: every section page uses the same 12-column grid, title baseline and two background variants; an executive-summary exception is documented.

Negative: each page invents a new palette, radius and icon family because individual generations looked appealing.

## Failures and validation

Common failures: unavailable fonts, insufficient contrast, undefined chart semantics, per-page drift and undocumented exceptions. Validate required YAML keys, font availability, contrast review, component reuse and exception count during deck review.
