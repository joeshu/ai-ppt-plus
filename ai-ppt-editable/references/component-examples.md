# Component example pack

`examples/component-library/standard-components.deck.json` is a runnable
reference for the standard title, table and trend-chart components. From the
repository root:

```bash
python3 scripts/validate_component_instances.py \
  examples/component-library/standard-components.deck.json \
  --components assets/component-library.template.json \
  --layouts assets/layout-library.template.json \
  --report /tmp/component-instance-validation.json
python3 scripts/compose_pptx.py \
  examples/component-library/standard-components.deck.json \
  /tmp/standard-components.pptx
python3 scripts/render_pptx.py /tmp/standard-components.pptx \
  --output-dir /tmp/standard-components-render \
  --report /tmp/standard-components-render.json
```

The render is a quality diagnostic, not a substitute for human visual review.
Formal content and chart data in real projects must come from approved sources.
