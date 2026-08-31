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

The old route, workflow and handoff schemas remain readable for compatibility.
Strict root release mode requires the new bindings and protocols. This allows
existing projects to be inspected and migrated without silently treating them
as release-ready.
