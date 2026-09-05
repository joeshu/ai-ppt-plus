# Astra Visual Reconstruction Engine

这是根技能的 Astra 文档入口。

## Canonical implementation reference

Editable Worker 内的权威实现说明：

- [`ai-ppt-editable/references/astra-visual-reconstruction-engine.md`](../ai-ppt-editable/references/astra-visual-reconstruction-engine.md)

该文档描述：

- Astra Visual Reasoner / Visual QA 的职责边界；
- PageGraph 与 DifferenceGraph；
- RepairRouter；
- deterministic PPTX authoring；
- Quality Gate；
- provider-neutral host contract。

## Current full-system documentation

最新系统级说明：

- [技术架构](../docs/TECHNICAL_ARCHITECTURE.md)
- [开发者工具链](../docs/DEVELOPER_GUIDE.md)
- [质量、蒸馏与 Golden](../docs/QUALITY_DISTILLATION_GOLDEN.md)

## Boundary

Astra 是视觉理解与视觉 QA 层，不是 PPTX writer。

```text
Astra reasoning / QA
        ↓
PageGraph / DifferenceGraph
        ↓
whitelist + confidence + safety gates
        ↓
Deterministic PPTX Engine
        ↓
render / inspect / semantic & native audit
```

所有模型建议必须经过结构化 contract 和确定性门禁后才能影响最终 PPTX。
