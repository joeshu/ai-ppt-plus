# Semantic layout classification

Use this gate in E1 before choosing an authoring primitive. Lines, repeated
rows, aligned columns and a border are visual evidence only; they do not prove
that a region is a table.

## Native table

Choose `native_table` only when all of the following are evidenced: a
field/header system, rows that are records under the same fields, a real
cell-to-cell data relationship, and a user-editing need for row/column data
operations. A known data source, data snapshot or explicit field schema is
supporting evidence. At least the record/data relationship must be present,
plus a header/field or data-operation/grid-data requirement. If table
semantics cannot be proved, fail closed; borders, repeated rows, two aligned
columns and grid lines are not sufficient.

## Repeated information component

Choose `repeated_component_group` when rows are icon + title + explanation,
describe different actions/stages/capabilities, have no header or uniform
fields, or use lines only to separate items. Such regions must not become
`a:tbl`. Author each item as an independent icon, title text box, body text
box, background shape and divider line, optionally inside a movable group;
never flatten an item into a picture or one large text box.

Every ambiguous region must emit `visual_structure`, `semantic_structure`,
`candidate_object_type`, `table_evidence`, `list_evidence`, `confidence`, and
`decision_reason` in PageGraph. A native table candidate with list semantics
fails with `TABLE-SEMANTIC-FALSE-POSITIVE-001` and blocks E3/E5. A declared
repeated group must also carry an independent child contract (`items[]` with
icon/title/body/background/divider IDs). Flattening the list or losing child
editability fails with `REPEATED-COMPONENT-FLATTENED-001` or
`COMPONENT-EDITABILITY-INCOMPLETE-001`; a candidate whose object type differs
from PageGraph fails with `OBJECT-TYPE-REFERENCE-MISMATCH-001`.

The classifier is run before composition and the same metadata is audited
after rendering. Native table count is allowed to be zero when all table-like
regions are lists; do not optimize for a target table count.

This gate does not change visual thresholds. The candidate must still pass the
existing rendered pixel, region, typography, asset, overflow and collision
gates. Asset files and hashes are immutable inputs to this classification.
