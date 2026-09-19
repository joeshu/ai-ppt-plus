# Text Coverage Auditor

## Purpose

The Text Coverage Auditor closes a specific reconstruction failure mode: a visible formal-text path reaches the final PPTX without passing through Text Slot Preflight / TextFit evidence.

It is a P0 correctness contract. It does **not** add a visual score threshold.

## Coverage model

Every formal text producer must create one coverage entry with:

- `target_id`: stable text target identifier.
- `owner_object_id`: AuthoringPlan owner.
- `producer_kind`: `text_box`, `rich_text_runs`, `table_cell`, `badge_label`, `chart_label`, `number_unit`, or `other`.
- `expected_text`: formal text authority for the target.
- `authoring_path`: concrete authoring helper/path.
- `text_fit_evidence`: proof that the slot was measured before or during authoring.
- `output_binding`: final PPT binding identifier.

All AuthoringPlan objects with `implementation_type=native_text` are mandatory coverage owners. Table cells, chart labels, badges and number+unit compositions may use synthetic `target_id` values while keeping the containing AuthoringPlan object as `owner_object_id`.

## Blocking findings

The auditor fails closed for deterministic text correctness defects:

- native text owner missing from coverage;
- coverage owner does not exist in AuthoringPlan;
- duplicate `target_id`;
- empty required formal text;
- missing/false measurement evidence;
- missing fit decision;
- missing authoring path;
- missing or duplicate output binding;
- source AuthoringPlan SHA mismatch.

These map to formal-text correctness and provenance. They are not visual-fidelity gates.

## Usage

```bash
python3 scripts/audit_text_coverage.py \
  PROJECT/authoring-plan.json \
  PROJECT/text-coverage.json \
  --json
```

For a valid run, the audit report must return `valid=true` and `uncovered_native_text=[]`.

## Authoring rule

No helper is allowed to write formal text directly to the deck unless it also records a coverage entry. When a helper creates many text-bearing children, such as table cells or chart labels, each material formal-text target must still be individually traceable.

Text fitting remains repair-oriented: repair slot geometry, margins, reservations, wrapping and line spacing before shrinking type.
