# Root P0 governance contract

The root skill controls five cross-cutting invariants:

1. `outline-contract/v1` freezes the approved PPT thought table with an outline
   hash, row hashes, revision and approval evidence.
2. `content-authority/v1` traces formal wording from source references through an
   outline row to a PPTX object and rendered region. Generated pixels and OCR
   never become formal-copy authority.
3. `validate_orchestration_gates.py` makes route and phase transitions explicit;
   a worker cannot silently change route, authority or project identity.
4. `worker-handoff/v1` normalizes worker output into the same evidence shape so
   an interrupted run can resume from hashes and artifact paths.
5. `quality-gates/v1` separates content, visual, structure and delivery status
   from human closeout and release eligibility.
6. `skill-routing/v1` and `engine-route-validation/v1` bind editable
   reconstruction/native authoring to `ai-ppt-editable`. Any
   `GordenImage2PPTX` use is region-only visual fallback evidence and cannot
   cover formal text, a semantic panel/table/card frame or a whole page.

The old route, workflow and handoff schemas remain readable for compatibility.
Strict root release mode requires the new bindings and protocols. This allows
existing projects to be inspected and migrated without silently treating them
as release-ready.

## Evidence-integrity hardening (2026-08-31)

Release and recovery additionally enforce these invariants:

- a successful DAG task must materialize every declared output before it may be
  cached or reported as passed;
- strict pixel evidence binds every rendered/reference image by SHA-256, while
  semantic evidence binds the current PPTX and object manifest by SHA-256;
- a worker handoff resolves relative paths from the handoff file, and its root
  and worker revisions must match the active package before recovery;
- human sign-off records the reviewer, confirmation time and exact PPTX hash;
- `human-closeout` represents a valid pending-review state, while only
  `delivered` requires completed sign-off;
- a reused review-package path is rebuilt in a clean staging directory and
  atomically replaced, then its pipeline and report-bundle hashes are resealed.
