# Standard layout library

`assets/layout-library.template.json` defines stable `layout_id` values for
page families. Each entry records the corresponding PowerPoint layout name,
safe margins and grid. A slide may set `layout_id`; the composer resolves it
through `layout_library` and then selects the existing master layout. A
deck-level `theme.layout_id` supplies the default.

Run `scripts/validate_layout_library.py` before composition. The library is a
layout contract, not a source of formal content: slide objects still own their
geometry, text, data and provenance. Unknown layout IDs, invalid margins or
invalid grids block the build.
