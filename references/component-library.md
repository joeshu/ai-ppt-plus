# Component library contract

`assets/component-library.template.json` is the portable registry for reusable
page components. Every component has a stable `component_id`, a supported
`type`, an explicit editability level, allowed PowerPoint layouts, and default
style tokens. A component definition describes defaults; it does not replace
the page's formal text, source data, geometry, or human review.

Use `scripts/validate_component_library.py` before composing a deck. Duplicate
IDs, missing layout applicability, invalid object types, or missing editability
levels block the build. Component instances should retain the registry ID in
their object manifest so reuse and exceptions can be measured across pages.

The registry supports `text`, `shape`, `group`, `table`, `chart`, `image`, and
`vector` types. Tables and charts remain native only when their source data is
traceable. A logo remains a complete `brand_lockup` asset even when placed in
a component; it must not be converted to ordinary text.
