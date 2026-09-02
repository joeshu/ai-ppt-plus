# P2 regression set

P2 is the repeatable regression layer for the route contract and native
editability boundary. It runs after P0/P1 implementation and remains useful
for every future change to routing, reconstruction, authoring or manifests.

## Automated coverage

- tests/test_engine_route.py checks the editable-first default, missing route
  fields, forbidden GordenImage2PPTX primary use, approved region-only complex
  visual fallback, semantic fallback rejection and visual-creation fallback
  rejection.
- ai-ppt-editable/tests/test_native_structure.py composes a real PPTX and
  verifies a native group, a native PowerPoint table and native formal text.
  It also proves that semantic frame/panel raster inputs are blocked.
- evals/p2-regression-cases.yaml and
  ai-ppt-editable/evals/native-editability-cases.yaml are lightweight
  operator-facing case registries. The executable tests are authoritative;
  YAML fixtures must stay parseable.

Run the focused checks:

    python3 tests/test_engine_route.py
    python3 ai-ppt-editable/tests/test_native_structure.py

Run the full package suites:

    python3 scripts/run_tests.py --parallel-workers 4
    python3 ai-ppt-editable/scripts/run_tests.py

## Non-regression rule

P2 must protect both sides of the deliverable:

1. editable routes keep native formal text, simple semantic panels/cards and
   tables;
2. complex gradients, illustrations, icons and other text-free visual assets
   remain independently movable raster/vector assets when native primitives
   would reduce fidelity;
3. a route or fallback change is never inferred from a file name or silently
   substituted by another skill;
4. a technical pass never claims visual approval or release readiness.
