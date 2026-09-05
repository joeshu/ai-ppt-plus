# ai-ppt-plus

> 面向 ChatGPT / Codex Skills 的工程化 PowerPoint 系统：从来源治理、叙事与视觉生成，到高保真可编辑重建、渲染验证、回归蒸馏和 Golden 基线晋升。

`ai-ppt-plus` 不是一个“输入一句话，由 Python 黑盒自动画完 PPT”的脚本集合。它是一套 **Skill 编排 + 原生 Image Generation + 确定性 PPTX Authoring + 多轴 QA + 可回归证据链** 的完整工作流。

核心原则只有三条：

1. **模型负责理解、设计判断与视觉 QA，不直接写 PPTX/XML。**
2. **确定性引擎是唯一 PPTX 写入器，正文/表格/图表等语义对象必须保持原生可编辑。**
3. **任何“看起来更像”的结果，都不能覆盖语义正确性、可编辑性、对象漂移和来源可追溯性。**

---

## 1. 这套系统解决什么问题

### 场景 A：从材料生成一套完整汇报

输入可以是 PDF、DOCX、Markdown、Excel/CSV、项目文件、会议纪要、现有 PPTX 或图片素材。

`ai-ppt-plus` 负责：

- 来源权威与冲突治理；
- brief、叙事、大纲和设计系统；
- 页面级路由；
- 调度视觉生成和可编辑重建；
- 聚合技术 QA、人工复核和发布证据。

### 场景 B：只生成高质量图片版 PPT

使用 `ai-ppt-visual-gen`：

- A1–A5 视觉规划；
- 每页复杂 Prompt；
- 原生 Image Generation；
- 源图、Prompt、模型/工具、哈希和 deck strip；
- 图片型 PPTX。

### 场景 C：把截图/图片/PDF 页高保真还原为可编辑 PPTX

使用 `ai-ppt-editable`：

- 视觉理解和对象分层；
- 原生文本、形状、表格、图表、分组和独立资产重建；
- Astra Visual Reconstruction Engine 闭环；
- 渲染比对、语义审计、Object Drift Guard；
- accepted-state、蒸馏记录和 Golden Promotion。

---

## 2. 三技能架构

| 技能 | 角色 | 主要输出 | 明确不做 |
|---|---|---|---|
| `ai-ppt-plus` | Super / Orchestrator | 大纲、路由、共享状态、跨技能 manifest、最终 QA 与发布 | 不替代 worker 的内部算法 |
| `ai-ppt-visual-gen` | Visual Worker | 图片页、Prompt、生成证据、deck strip、image-only PPTX | 不宣称图片页是可编辑 PPTX |
| `ai-ppt-editable` | Editable Worker | 可编辑 PPTX、PageGraph、DifferenceGraph、对象/语义/视觉 QA | 不改写已批准叙事，不用整页截图冒充编辑性 |

目录结构：

```text
ai-ppt-plus/
├── SKILL.md
├── README.md
├── scripts/
├── references/
├── assets/
├── docs/
├── evals/
├── ai-ppt-visual-gen/
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   ├── assets/
│   └── tests/
└── ai-ppt-editable/
    ├── SKILL.md
    ├── reconstruction/
    ├── scripts/
    ├── references/
    ├── assets/
    ├── evals/
    └── tests/
```

---

## 3. 最新核心：Astra Visual Reconstruction Engine

图片转可编辑 PPTX 被定义为一个 **Inverse Rendering / Reverse Layout Reconstruction** 问题，而不是简单 OCR + 坐标抄写。

```text
Reference Image / PDF Page
        │
        ▼
Astra Visual Reasoner
        │
        ▼
PageGraph IR
(Layout / Text / Asset / Native Semantics)
        │
        ▼
Deterministic PPTX Authoring Engine
        │
        ▼
Editable PPTX → Render
        │
        ▼
Deterministic Evidence + Astra Visual QA
        │
        ▼
DifferenceGraph
        │
        ├─ GeometryRepair
        ├─ TypographyRepair
        ├─ AssetRepair
        └─ SemanticRepair
        │
        ▼
Object Drift Guard + Quality Gate
        │
        ├─ rollback
        ├─ EXTERNAL_ASSET
        └─ accepted-state
```

### PageGraph

统一的页面对象图 IR：

- 文本、形状、表格、图表、图标、插画、图片、连接线、分组、背景；
- 包含、对齐、等宽/等高、间距、连接、重叠、锚定等关系；
- 几何坐标统一使用 slide fraction `[0,1]`；
- 旧版 px 布局在 bridge 层归一化，不允许多单位继续向下游传播。

### DifferenceGraph

所有 QA 差异统一落到四个责任域：

- `geometry`
- `typography`
- `asset`
- `semantic`

并带有：

- severity：P0–P3；
- confidence；
- metrics；
- evidence；
- whitelisted `proposed_patch`。

模型只允许提出结构化 DifferenceGraph，不能直接操作 XML 或随意执行代码。

---

## 4. 确定性 PPTX 引擎

`ai-ppt-editable` 的 authoring backend 是唯一 PPTX 写入器。

必须优先原生化：

- 标题、正文、标签、数字 → 原生文本框 + rich-text runs；
- 简单卡片、边框、线条、标签 → native shapes；
- 表格 → native table；
- 有可信数据的图表 → native chart + workbook data；
- 分组 → native groups；
- 图标、插画、复杂渐变/艺术元素 → 独立可移动资产。

明确禁止：

- 整页截图冒充可编辑 PPTX；
- 把正文栅格化后再覆盖透明文本；
- 模型直接写 PPTX XML；
- 用全局视觉相似度掩盖语义错误或对象类型错误。

---

## 5. 资产策略：原生生图边界

对于图标、渐变图、复杂艺术元素，默认策略是：

1. 由原生 Image Generation 重新生成；
2. 生成结果先通过 deterministic file/hash/background validation；
3. 再通过 Asset QA v2；
4. 通过后才能绑定回布局；
5. 绑定时保持 `x/y/w/h/rotation` 不变。

Asset QA v2 使用受控 `issue_codes`：

- `semantic_mismatch`
- `silhouette_mismatch`
- `orientation_mismatch`
- `color_mismatch`
- `gradient_flow_mismatch`
- `style_mismatch`
- `missing_detail`
- `extra_detail`
- `composition_mismatch`
- `background_noncompliance`

并强制 confidence gate。自由文本 `reasons` 只作为审计证据，不参与自动重试决策。

默认最多 3 次 native generation retry。达到上限后系统不会自动降级，必须显式选择：

- 继续原生生图；
- 裁剪/抠图 fallback。

---

## 6. 质量闭环

质量不只看视觉相似度，而是同时检查：

### Visual

- pixel fidelity；
- layout SSIM；
- critical region fidelity；
- renderer regression。

### Native editability

- 禁止 full-slide raster；
- 文本必须是真文本；
- 表格/图表/分组必须具有正确原生语义；
- 对象数量、几何和层级可审计。

### Semantic

- `semantic_accuracy == 1.0` 才可进入高质量基线；
- `semantic_audit.valid == true`；
- `error_count == 0`；
- `audited_object_count == expected_object_count`。

### Object Drift Guard

普通修复只允许 `repair-execution-report.applied[]` 中真正执行成功的对象发生变化。

- proposed but not applied → 不允许漂移；
- deferred / skipped → 不允许漂移；
- asset resume → 只允许本轮 `asset-resolution-report.resolved[]` 中的对象变化；
- 无执行证据 → allowlist 为空，fail-closed。

---

## 7. accepted-state、回滚与收敛

多轮视觉修复不能每轮重新从原始 candidate 开始。

每个 case 维护 `accepted-state.json`：

```text
iteration 1
candidate → repair → accepted
                      │
                      ▼
               accepted-state
                      │
iteration 2           ▼
                accepted layout → repair → accepted / rollback
```

source resolution 优先级：

1. 最新有效 `accepted-state.json`；
2. 历史 accepted iteration；
3. 原始 candidate。

出现以下情况会回滚：

- pixel fidelity 回退；
- blocker 增加；
- native editability 回退；
- semantic accuracy 回退；
- unauthorized object drift。

---

## 8. Distillation 与 Golden Promotion

每轮被结构化为 Distillation Record，记录：

- case / iteration / status；
- accepted / rollback；
- source accepted iteration；
- source layout；
- repairs 与执行 engine；
- visual score / delta；
- semantic audit；
- native editability；
- drift；
- asset retry / user choice；
- human approval；
- artifacts。

Distillation Selection 使用 fail-closed 分类：

- `positive`
- `hard_negative`
- `rejected`

缺失 native/semantic/source evidence 的样本不能成为 positive。

Golden Promotion 默认要求：

- visual score 达标；
- `semantic_accuracy == 1.0`；
- semantic audit 完整；
- native editability 为 true；
- zero blockers；
- zero unauthorized drift；
- human approval；
- no rollback；
- source lineage 完整；
- 连续 2 个稳定 iteration。

Golden baseline 是版本化、不可覆盖的 manifest，并保留 previous golden / rollback pointer。

---

## 9. 12-case 回归与 provider-neutral full loop

仓库内置真实 12-case replay suite，覆盖：

1. 默认 editable 路由；
2. native shape/card；
3. native table；
4. merge/rich-text table；
5. CJK/font；
6. chart/data provenance；
7. gradient/icon assets；
8. irregular framework；
9. multi-slide consistency；
10. fallback stop；
11. package/render portability；
12. cache/idempotency。

严格运行：

```bash
python evals/case-replay-12/run_replay_suite.py --strict
```

另有 provider-neutral full-loop integration test，验证：

```text
DifferenceGraph
 → RepairRouter
 → deterministic repair
 → EXTERNAL_ASSET
 → generated asset validation
 → Asset QA v2
 → geometry-safe bind
 → accepted-state
 → next iteration
 → Distillation
 → lineage
 → Golden Promotion
```

这条集成测试验证控制平面连续性；真实 PPTX author/render 仍由现有 replay suite 验证。

---

## 10. 快速使用

### 完整生成 + 可编辑交付

```text
请使用 ai-ppt-plus，把这些材料做成一份 8 页中文管理层汇报。
16:9，科技商务风，先给我确认大纲和视觉方向；确认后生成视觉稿，
再还原为可编辑 PPTX，并执行逐页视觉、语义、对象和交付 QA。
```

### 只生成图片版

```text
请使用 ai-ppt-visual-gen，根据这份大纲生成 6 页高信息密度图片版 PPT。
逐页保留 Prompt、生成源图、哈希和 deck strip。
```

### 只做图片转可编辑

```text
请使用 ai-ppt-editable，把这些参考页严格还原为可编辑 PPTX。
保持原布局、层级、颜色和 z-order；正文使用原生文本框，表格/图表保持原生语义；
图标、渐变和复杂艺术元素使用原生生图，最终执行 Astra 闭环 QA。
```

---

## 11. 安装与环境自检

```bash
git clone https://github.com/joeshu/ai-ppt-plus.git
cd ai-ppt-plus

python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-ci.txt

python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
python3 scripts/probe_environment.py --output environment-report.json
```

三技能独立校验：

```bash
python3 ai-ppt-visual-gen/scripts/validate_skill_package.py --skill-dir ai-ppt-visual-gen
python3 ai-ppt-editable/scripts/validate_skill_package.py --skill-dir ai-ppt-editable
python3 ai-ppt-editable/scripts/validate_routing_contract.py
```

环境探针会报告 Python 包、LibreOffice、Poppler、Inkscape、OCR、字体和渲染能力。`probe_environment.py` 执行成功不代表所有能力都可用，应检查报告中的实际 `available` 状态。

---

## 12. 关键命令

### 根包测试

```bash
python3 scripts/run_tests.py --parallel-workers 4 --report test-report.json
```

### Editable worker tests

```bash
python3 ai-ppt-editable/scripts/run_tests.py --report editable-skill-test-report.json
```

### 真实 12-case replay

```bash
python3 evals/case-replay-12/run_replay_suite.py --strict
```

### 生成 Astra 12-case closed-loop batch

```bash
python3 evals/case-replay-12/build_astra_closed_loop_batch.py \
  --output-dir .distillation/astra-closed-loop \
  --strict
```

### Provider-neutral QA ingestion

```bash
python3 evals/case-replay-12/ingest_astra_qa_batch.py ...
```

### 单轮 deterministic iteration

```bash
python3 evals/case-replay-12/run_astra_iteration.py ...
```

### 多 case iteration + rollback

```bash
python3 evals/case-replay-12/run_astra_iteration_batch.py ...
```

### Asset resolution / resume

```bash
python3 evals/case-replay-12/resolve_generated_assets.py ...
```

### Golden promotion

```bash
python3 evals/case-replay-12/promote_astra_golden.py ...
```

---

## 13. CI 门禁

`.github/workflows/ci.yml` 当前会执行：

- Python compile；
- 三技能 package/routing validation；
- runtime mirror validation；
- standalone worker smoke tests；
- Astra reconstruction contract tests；
- 12-case Astra closed-loop batch；
- schema / DAG / package / golden regressions；
- social-channel 真 PPTX replay；
- 12-case visual/native-editability replay；
- distillation matrix validation；
- strict P2 guards；
- whitespace gate。

CI 全绿表示技术契约通过，但 **不自动代表人工视觉签核或最终发布批准**。

---

## 14. 项目目录建议

```text
PROJECT/
├── source/
├── brief/
├── outline/
├── design/
├── route-decision.json
├── workflow-state.json
├── visual/
├── editable/
├── project-fonts/
├── deliverables/
└── qa/
```

对于 Astra reconstruction case，建议额外保留：

```text
case/
├── page-graph.json
├── deterministic-difference-graph.json
├── astra-visual-qa-request.json
├── merged-difference-graph.json
├── repair-execution-report.json
├── object-drift-report.json
├── semantic-audit.json
├── native-editability.json
├── visual-comparison.json
├── accepted-state.json
└── iteration-record.json
```

---

## 15. 技术文档

建议阅读顺序：

1. [使用教程](docs/TUTORIAL.md)
2. [技术架构](docs/TECHNICAL_ARCHITECTURE.md)
3. [开发者工具链与扩展指南](docs/DEVELOPER_GUIDE.md)
4. [质量、蒸馏与 Golden 基线](docs/QUALITY_DISTILLATION_GOLDEN.md)
5. [三技能架构](references/three-skill-architecture.md)
6. [操作矩阵](references/operations-matrix.md)
7. [技能路由](references/skill-routing.md)
8. [Astra Visual Reconstruction Engine](references/astra-visual-reconstruction-engine.md)
9. [根技能规范](SKILL.md)
10. [Visual Worker 规范](ai-ppt-visual-gen/SKILL.md)
11. [Editable Worker 规范](ai-ppt-editable/SKILL.md)

---

## 16. 设计边界

本项目明确区分：

- **AI reasoning**：视觉理解、页面语义、差异诊断、视觉 QA；
- **native image generation**：图标、渐变、复杂艺术元素；
- **deterministic authoring**：PPTX 原生对象写入；
- **deterministic evidence**：render、inspect、semantic/native audit、pixel comparison；
- **human approval**：视觉确认、fallback 决策、Golden 人工签核。

任何一层都不能冒充另一层的证据。

这也是 `ai-ppt-plus` 的核心目标：**不是让模型“更自由地改 PPT”，而是让模型在严格证据、原生语义和可回滚控制下，持续缩短最终 PPTX 与视觉目标之间的差距。**
