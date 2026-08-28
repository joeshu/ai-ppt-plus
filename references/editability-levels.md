# Editability levels (L0–L5)

Read this contract whenever a reference page contains photography, illustration,
logos, textures, screenshots, chart images or any other object that may not be
reliably rebuilt as native PowerPoint content. The level is assigned per visible
object, never to the whole page by optimistic average.

Editability is multidimensional and must not be inferred from the object count:

| Dimension | Values | Meaning |
|---|---|---|
| `content_editability` | `content_editable`, `not_applicable` | Whether formal wording/data can be changed directly. |
| `movement_editability` | `moveable`, `group_moveable`, `locked` | Whether the object can be independently moved, cropped or replaced. |
| `component_editability` | `component_editable`, `static_asset` | Whether internal geometry/pixels can be edited as native parts. |
| `asset_policy` | `normal_asset`, `brand_lockup`, `user_supplied_asset` | Whether OCR/reconstruction is allowed for the visible asset. |

Use `asset_policy: brand_lockup` for a complete logo mark and wordmark. Keep it
as one authoritative movable asset and do not recreate its Chinese or English
lettering as ordinary text unless the user explicitly requests a redesigned
or component-editable logo. A panel count is a page fact, not a schema field:
store repeated regions in `regions[]`/`objects[]` and validate any positive N.

| Level | Meaning | Typical object types | Machine rule | Delivery rule |
|---|---|---|---|---|
| `L0` | prohibited flattening: a full-page bitmap or a rasterized required text/simple shape | `flattened_full_slide` | always blocker | rebuild as objects |
| `L1` | natively or structurally editable | `editable_text`, `native_shape`, `editable_vector`, `editable_chart`, `editable_table` | required fields and chart/table data/provenance | auto-allowed |
| `L2` | independent image object; movable, crop-able and replaceable, but pixels are not internally editable | `independent_image`, `extracted_icon`, `decorative_art` | provenance + `replaceable: true`; never formal text/data | allowed with disclosure; human visual review |
| `L3` | verified static graphic whose source/data is traceable but whose internal structure is not editable | `traceable_static_graphic` | provenance/data source + `reduced_editability_accepted: true` | explicit human editability confirmation |
| `L4` | accurate placeholder for a missing or unsafe-to-recreate material | `documented_placeholder` | reason + exact `material_request` | manual review; blocks if required for delivery |
| `L5` | unresolved, unverifiable or falsely reconstructed content | `unresolved` | always blocker | do not deliver |

Each `objects[]` record must include:

```json
{
  "object_id": "S01-O07",
  "object_type": "independent_image",
  "editability_level": "L2",
  "required_for_delivery": false,
  "provenance": "asset-manifest#hero-photo",
  "replaceable": true,
  "contains_formal_content": false,
  "human_review_required": true
}
```

For `L1` charts, add `data_source` or `provenance`. For `L3`, add
`data_source` where applicable and set `reduced_editability_accepted` only
after the source has been checked. For `L4`, add `placeholder_reason` and a
specific `material_request`; “素材缺失” alone is not sufficient.

For extracted icons, decorations and artistic typography, also record
`asset_id`, `role`, `source_bbox`, `extraction_method`, `alpha_quality`,
`edge_touch`, `split_status`, `duplicate_guard`, `anchor`, and `replaceable`.
Validate these with `scripts/validate_icon_assets.py`; a clean alpha channel
or valid file is not a substitute for rendered visual review.

The page summary is derived, not hand-waved:

```json
{
  "primary_level": "L2",
  "delivery_decision": "allowed-with-disclosure",
  "counts_by_level": {"L0": 0, "L1": 8, "L2": 2, "L3": 0, "L4": 0, "L5": 0},
  "object_count": 10,
  "fully_editable_object_count": 8,
  "raster_object_count": 2,
  "placeholder_count": 0,
  "blocked_object_count": 0,
  "fully_editable_ratio": 0.8,
  "human_review_required": true,
  "formal_content_rasterized": false
}
```

`validate_manifest.py --require-editability` checks object records and that the
declared summary matches the derived summary. `delivery_check.py
--require-editability` repeats the safety check at release time. A legacy
manifest without `objects[]` is reported as `legacy-untyped` in compatibility
mode, but cannot pass a strict new-project gate. `validate_project.py` and
`run_pipeline.py` can consume the same reports so a child gate cannot disappear
from the project result.

The ratio is diagnostic, not a waiver: a high `L1` ratio cannot override one
`L0`, `L5`, required `L4`, rasterized formal-content object, missing provenance,
or an unaccepted `L3` degradation.
