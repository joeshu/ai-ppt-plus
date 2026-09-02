# Skill routing and ownership

`ai-ppt-plus` is the routing authority for an orchestrated deck. `ai-ppt-editable` is the default editable worker for fixed references, screenshots, rasterized PDF pages, existing PPTX repair, and structured-content-to-editable-PPTX work.

`GordenImage2PPTX` is not the default worker and is not a second route definition. It is a controlled compatibility fallback for a scoped visual asset only, after the editable worker's native path or the approved native image-generation path has failed and the user has explicitly approved the fallback.

| Capability | Default owner | Boundary |
|---|---|---|
| Route, authority, release | `ai-ppt-plus` | Decides the route and owns delivery claims |
| Editable reconstruction and native authoring | `ai-ppt-editable` | Owns decomposition, object mapping, authoring and technical QA |
| Visual-only fallback asset | `GordenImage2PPTX` | Region-only, asset-recorded, user-approved; never formal text, panels, tables, charts or whole pages |
| Rendering and package adapters | `Presentations`, `python-pptx`, LibreOffice, Poppler | Implement declared operations; do not acquire route or release ownership |

## Routing rules

1. Complete deck requests start in `ai-ppt-plus`, which records the route, formal-text authority, engine selection and fallback policy.
2. `reference-reconstruction`, `editable-pptx` and `native-authoring` use `ai-ppt-editable` as the primary engine and target native semantic objects whenever the semantics are known.
3. `visual-creation` uses `ai-ppt-visual-gen` as the visual worker and returns evidence to `ai-ppt-plus`; it is not an editable reconstruction route.
4. A fallback event must be region-bounded, contain no formal content, carry a reason and asset record, and include an explicit user decision. The root engine-route validator is the hard gate.
5. The worker may run standalone, but standalone invocation does not relax the route, authority, editability, asset-provenance or technical-QA contracts.

The machine-readable root contract is `ai-ppt-plus/assets/skill-routing.template.json`; the worker-local contract is only the package boundary and authoring binding. Keep both names visible so a worker invocation cannot be mistaken for route ownership.

## Executable checks

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
python3 scripts/validate_perfect_sync.py
```

In orchestrated mode, consume the immutable route decision and handoff supplied by `ai-ppt-plus`, then return worker-level PPTX and technical evidence. The worker never claims narrative ownership, release eligibility or human sign-off.
