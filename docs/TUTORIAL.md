# ai-ppt-plus 使用教程

本教程从一个主题或一组材料开始，带你走完：来源治理 → 大纲确认 → 路由选择 → 视觉生成/参考还原 → 可编辑 PPTX → 渲染 QA → 人工收口 → 发布。

适用对象：使用 Codex/ChatGPT Skills 做 PPT 的用户、需要在本地复核产物的工程师，以及需要把图片版 PPT 接入可编辑 PPTX 流程的团队。

## 0. 先记住四条规则

1. **正式文字有唯一权威。** 已批准大纲、用户提供的文案和可追溯数据优先于 OCR、生成图片里的文字和模型补写。
2. **参考图只教声明的东西。** 可以学习构图、层级、密度和阅读路径；是否学习配色/字体/图标语言必须在参考策略中声明。参考图里的文字、数字、Logo 和品牌身份不能偷偷变成内容。
3. **图片版不等于可编辑。** 一页一张全幅 PNG 的 PPTX 仍然是图片型 PPTX。要可编辑，必须把文字恢复为原生文字，把语义对象和资产按目标编辑性拆开。
4. **自动通过不等于人工确认。** OCR、哈希、渲染和对象审计只能给出技术证据；视觉方向、事实价值、品牌和最终交付仍需人工 closeout。

## 1. 安装和能力检查

### 1.1 安装 Python 依赖

```bash
git clone https://github.com/joeshu/ai-ppt-plus.git
cd ai-ppt-plus
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-ci.txt
```

三个目录均自包含。只使用图片版或可编辑版时，可以在对应目录执行它自己的 `requirements-ci.txt` 和校验器：

```bash
(cd ai-ppt-visual-gen && python -m pip install -r requirements-ci.txt)
(cd ai-ppt-editable && python -m pip install -r requirements-ci.txt)
```

### 1.2 校验技能包和本地工具

```bash
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_routing_contract.py
python3 scripts/probe_environment.py --output environment-report.json
python3 scripts/validate_environment_contract.py \
  --report environment-report.json \
  --output environment-validation.json
```

重点看：

- `python_pptx`：是否能执行 PPTX 对象创建和检查；
- `libreoffice_renderer`、`poppler_renderer`：是否能得到最终渲染图；
- `ocr_engine`：是否能执行文字回读；
- `fonttools` / `fontconfig`：是否能验证字体交付；
- `pptx_authoring_runtime`：是否真的存在，不能只因为环境变量存在就假设可用。

原生 ImageGen 是宿主能力，不在 `requirements-ci.txt` 中安装。没有可用的图像生成工具时，图片生成阶段必须返回 `unavailable`/`blocked`，不能用 SVG、HTML、Pillow 绘图或 PPTX 截图伪装成生成图。

### 1.3 准备中文字体

```bash
mkdir -p PROJECT/project-fonts PROJECT/qa
cp assets/fonts/NotoSansSC-Regular.ttf PROJECT/project-fonts/
cp assets/fonts/font-manifest.json PROJECT/project-fonts/
python3 scripts/probe_fonts.py \
  --output PROJECT/qa/font-report.json \
  --font-dir PROJECT/project-fonts \
  --require-cjk
python3 scripts/validate_font_asset.py \
  --font-dir PROJECT/project-fonts \
  --require-cjk \
  --report PROJECT/qa/font-asset-validation.json
```

如果用户提供了已授权字体，优先使用用户字体；不要复制或重新分发未获授权的系统字体。

## 2. 选择交付路线

先问自己两个问题：有没有固定参考页？最终是否必须可编辑？

| 情况 | 路由/技能 | 说明 |
|---|---|---|
| 只有主题、材料或大纲，希望新做一套 PPT | `visual-creation` → `ai-ppt-visual-gen`，需要可编辑时再接 `ai-ppt-editable` | 生成新的视觉中间态；正式内容来自批准大纲 |
| 有截图、图片页或 PDF 页，要尽量复刻原版 | `reference-reconstruction` → `ai-ppt-editable` | 工程还原，不重新设计；参考图是视觉权威 |
| 有结构化内容/数据，强调文字、图表、表格可编辑 | `native-authoring` → `ai-ppt-editable` | 直接用原生对象；不得静默退回整页图片 |
| 用户只说“做一份 PPT”，没指定输出形式 | `ai-ppt-plus` Super | 先确认目标，默认规划 A→B，最终同时交图片视觉稿和可编辑 PPTX |

在支持 Skills 的客户端中，可以这样开始：

```text
请使用 ai-ppt-plus。
输入材料在 PROJECT/source/，做成 8 页 16:9 中文高管汇报。
目标受众是集团管理层，先输出 deck brief、逐页大纲和路由建议，等我确认后再生成视觉稿和可编辑 PPTX。
```

如果用户已经明确只要一种能力，直接点名子技能，避免让 Super 增加不必要的后半段。

## 3. 初始化一个可恢复项目

建议每个项目使用独立目录，原始输入只读保存：

下文的 `PROJECT` 表示这个项目目录的绝对路径；使用绝对路径可以避免在进入子技能目录后引用路径失效。

```bash
mkdir -p PROJECT/{source,brief,outline,design,visual,editable,project-fonts,deliverables,qa}
cp assets/workflow-state.template.json PROJECT/workflow-state.json
cp assets/route-decision-visual-creation.template.json PROJECT/route-decision.json
```

如果是参考图重建，改用 `assets/route-decision.template.json` 并把参考页放到 `PROJECT/reference/slide-1.png`、`slide-2.png` 等位置；如果是原生内容，改用 `assets/route-decision-native-authoring.template.json`。

模板只是起点。必须根据项目实际情况修改：

- `project_id`、`run_id`、`revision`、`package_revision`；
- `phase`、`route`、`page_count`、`canvas_ratio`；
- `formal_text_authority` 和 `visual_authority`；
- `artifacts` 中真实存在的相对路径和 SHA-256；
- `approvals`、`open_blockers`、`next_action`。

初始化阶段不要对还没有生成的必需产物使用 `--strict`。随着 O1/O2/A/B 阶段完成，再把状态推进并补齐哈希。

## 4. O0：来源、环境和状态

### 4.1 清点输入

```bash
python3 scripts/inspect_sources.py \
  PROJECT/source \
  --output PROJECT/brief/source-inventory.json
```

逐项记录：来源是否可读、哪些内容是事实、哪些是观点或模型推断、来源冲突、缺失字段、OCR 需求和敏感信息。图片参考在进入 OCR、调色或抠图前，先执行完整像素解码校验：

```bash
python3 scripts/validate_source_images.py \
  PROJECT/reference/slide-1.png PROJECT/reference/slide-2.png \
  --report PROJECT/qa/source-image-validation.json
```

“文件存在”不代表“图片可用”；容器能读元数据但像素解码失败时必须阻断。

### 4.2 验证工作流状态

```bash
python3 scripts/validate_workflow_state.py \
  PROJECT/workflow-state.json \
  --project-root PROJECT \
  --expected-pages 6 \
  --report PROJECT/qa/workflow-state-validation.json
```

在交接、恢复和发布前使用严格模式：

```bash
python3 scripts/validate_workflow_state.py \
  PROJECT/workflow-state.json \
  --project-root PROJECT \
  --expected-pages 6 \
  --strict \
  --report PROJECT/qa/workflow-state-validation.json
```

`revision-required` 必须有带 `severity`、`owner_artifact`、`status` 的阻塞项；`delivered` 不能带开放阻塞，也不能缺少人工 closeout。

## 5. O1：先做大纲，再做画面

每页大纲至少要有：

- 页面目的和一句话核心结论；
- 与前后页的关系；
- 表达类型（流程、比较、时间线、矩阵、图表、框架等）；
- 必须保留的文字、数据、事实和来源；
- 可以压缩/合并的内容；
- 受众看完这一页要带走什么；
- 页面状态和审批记录。

大纲可以用 CSV 或 XLSX 保存，随后校验：

```bash
python3 scripts/validate_outline.py \
  PROJECT/outline/approved-outline.xlsx \
  --require-approved \
  --report PROJECT/qa/outline-validation.json
```

不要先做一张“看起来漂亮”的图，再倒推故事；也不要把生成图片里的新增文字直接复制成正式文案。视觉稿中的辅助文字必须回到大纲/正式文本权威中复核。

## 6. O2：路由和设计系统

### 6.1 生成新视觉：`visual-creation`

适用于主题/材料驱动的新 PPT。`ai-ppt-visual-gen` 会执行 A1–A5：

| 阶段 | 做什么 | 关键产物 |
|---|---|---|
| A1 | 锁定画布、页数、受众、密度、色彩和风格 | generation context |
| A2 | 把每页内容变成有焦点、有阅读路径、有容量的视觉框架 | visual-generation-plan |
| A3 | 生成自包含 Prompt，写入正式文字白名单和重点词颜色 | materialized prompts |
| A4 | 宿主 ImageGen 逐页生成，留存源图/副本/哈希，失败只重试单页 | visual-generation-manifest |
| A5 | 生成全套 deck strip，再逐页看原图并交接 | strip、review status、handoff |

商业/信息图默认使用 `dense`。如果只能提供少量事实，降低密度必须记录原因，不能用模型编造内容填满卡片。

### 6.2 参考还原：`reference-reconstruction`

适用于截图或图片页驱动的复刻。`ai-ppt-editable` 执行 B0–B9（其对外文档仍按 E0–E5 说明）：

1. 建立唯一运行目录并查看原始页；
2. 盘点背景、框架、卡片、文字、图表、表格、图标、装饰和艺术字；
3. 分离背景、框架/骨架、图标/插画、正式文字和图表数据；
4. 把已知文字恢复为原生文本框/文本 runs；
5. 把复杂图形保留为有来源证据的独立可移动资产；
6. 按原比例、边界、层级和 z-order 组成 PPTX；
7. 渲染后逐页对照，修复所属对象，再交接。

这是工程还原，不是重新设计。不可辨识的文字、身份、数据或几何必须标记 `manual_required`；图表和表格不能靠生成模型猜出来。

### 6.3 原生创作：`native-authoring`

适用于结构化内容、可追溯图表和表格。正文、数据标签使用原生对象；图表只有在数据和单位可追溯时才做原生图表。不能因为布局困难就静默改走视觉生成或整页截图。

### 6.4 校验路由

```bash
python3 scripts/validate_route.py \
  PROJECT/route-decision.json \
  --require-files \
  --expected-pages 6 \
  --require-confirmation \
  --require-formal-content \
  --report PROJECT/qa/route-validation.json
```

`needs_user` 或 `blocked` 路由不能进入下游。路由模板和共享边界见 `assets/skill-routing.template.json` 与 `references/skill-routing.md`。

## 7. A1–A5：生成图片版 PPT

### 7.1 生成计划和 Prompt

```bash
cd ai-ppt-visual-gen
cp assets/visual-generation-plan.template.json PROJECT/visual/visual-generation-plan.json
python3 scripts/materialize_visual_generation_prompts.py \
  PROJECT/visual/visual-generation-plan.json --in-place
python3 scripts/validate_visual_generation_plan.py \
  PROJECT/visual/visual-generation-plan.json \
  --expected-pages 6
```

每页计划要有：`core_logic`、不同于其他页的视觉框架、focal point、reading path、命名区域、容量、反模板规则、至少三段规划储备内容、正式文字、来源和可选 `keyword_emphasis`。

### 7.2 逐页调用宿主 ImageGen

Prompt 物化后，使用当前宿主可用的原生图像生成工具逐页调用。每页必须记录：

- 原生生成源图和项目副本；
- Prompt 路径与 SHA-256；
- 生成工具/模型、尺寸、比例和尝试次数；
- 生成失败或重试触发原因；
- 正式文字白名单和重点词颜色映射。

图片中的文字需要真实可读。模型擅自增加的说明、数字、机构名、日期和 Logo 都是缺陷，不是“设计发挥”。如果第 3 页失败，只重试第 3 页，最多按项目策略重试 2–3 次，不能为了方便重生成整套。

### 7.3 验证和生成图片型 PPTX

```bash
python3 scripts/run_visual_pipeline.py \
  PROJECT/visual/visual-generation-plan.json \
  --expected-pages 6 \
  --manifest PROJECT/visual/visual-generation-manifest.json \
  --strip PROJECT/qa/visual-deck-strip.png \
  --image-pptx PROJECT/deliverables/image-only.pptx \
  --report PROJECT/qa/visual-pipeline.json
```

如果计划声明了视觉断言，流水线会继续检查 OCR 文本、重点词词框内的目标色和页面最低墨迹比例。目标色只出现在页面别处，不能算重点词通过。

A5 必须同时检查：

- deck strip 是否覆盖恰好全部页面；
- 整套色彩、密度、标题位置、边距和阅读节奏是否一致；
- 页面之间是否意外重复同一框架；
- 每张原图上的真实文字、细节和重点色是否正确。

Strip 是总览，不替代逐页原图检查。

## 8. B0–B9：图片/内容到可编辑 PPTX

如果是 `reference-reconstruction`，不要把 A 的图片生成当成替代参考图的方式。固定参考路线直接进入可编辑重建；必要时只为缺失的图标/装饰生成独立资产，并保留资产来源证据。

### 8.1 组成 PPTX

当 `PROJECT/editable/layout.json`、对象清单和资产清单准备好后：

```bash
python3 ai-ppt-editable/scripts/compose_pptx.py \
  PROJECT/editable/layout.json \
  PROJECT/deliverables/final.pptx \
  --preview-dir PROJECT/qa/preview \
  --font-dir PROJECT/project-fonts \
  --embed-fonts \
  --embedding-report PROJECT/qa/font-embedding.json \
  --strict-input
```

### 8.2 运行技术检查

常用检查包括：

```bash
python3 ai-ppt-editable/scripts/inspect_pptx.py \
  PROJECT/deliverables/final.pptx \
  --report PROJECT/qa/editable-inspection.json

python3 scripts/render_pptx.py \
  PROJECT/deliverables/final.pptx \
  --output-dir PROJECT/qa/rendered \
  --font-dir PROJECT/project-fonts \
  --page-cache-dir PROJECT/.pipeline-cache/render-pages \
  --report PROJECT/qa/render-report.json
```

随后根据项目启用对象、资产、字体、文字版式、图表、面板、manifest registry、视觉对比和报告包门禁。根验证器默认从 `PROJECT/slide-object-manifest.json`、`PROJECT/text-layout-manifest.json` 和 `PROJECT/manifest-registry.json` 读取这些清单；如果你把它们放在 `editable/` 下，运行时显式传入对应的 `--object-manifest`、`--text-manifest` 和 `--manifest-registry`。不要只看 PPTX 能否打开；还要看：

- 标题/正文是否真的是可编辑文字；
- 重点色、字号、换行和文字边界是否保留；
- 卡片和语义模块能否独立移动；
- 图表和表格是否有数据/来源证据；
- 图标、插画、艺术字是否被错误 OCR 成普通正文；
- 最终渲染是否发生字体回退、溢出、裁切或 z-order 变化。

## 9. Super：串起 A 和 B

当以下文件准备齐后，使用 Super 的 full 模式：

- `route-decision.json`；
- `workflow-state.json`；
- `visual-generation-plan.json` 和 `visual-generation-manifest.json`（仅 `visual-creation`）；
- `editable/layout.json`；
- `slide-object-manifest.json`、`text-layout-manifest.json`、`manifest-registry.json`（启用严格 QA 时）；
- 项目字体和参考页（按路由需要）。

```bash
python3 scripts/run_super_pipeline.py PROJECT \
  --mode full \
  --route-decision PROJECT/route-decision.json \
  --workflow-state PROJECT/workflow-state.json \
  --require-workflow-state \
  --visual-plan PROJECT/visual/visual-generation-plan.json \
  --visual-manifest PROJECT/visual/visual-generation-manifest.json \
  --editable-layout PROJECT/editable/layout.json \
  --output-deck PROJECT/deliverables/final.pptx \
  --expected-pages 6 \
  --font-dir PROJECT/project-fonts \
  --strict-qa \
  --execution-mode dag \
  --parallel-workers 4 \
  --report PROJECT/qa/super-pipeline.json
```

不同路由的参数：

- `visual-creation`：传入视觉计划和 manifest；A 阶段验证后进入 B。
- `reference-reconstruction`：不传视觉计划/manifest；传入 route 中的参考页 roster，由 B 直接还原。
- `native-authoring`：不传视觉计划/manifest；传入 native content manifest 和可编辑布局。

`--mode handoff` 只适合快速诊断已有 A→B 交接，不是发布门禁。`--mode full` 会运行环境、路由、状态、A 证据、B 组成、B 技术 QA 和最终 handoff。

## 10. 运行根验证流水线

`run_pipeline.py` 是“围绕已经做好的 PPTX 执行确定性 QA”的入口，不负责替你写大纲、调用模型或修改正式文字：

```bash
python3 scripts/run_pipeline.py PROJECT \
  --deck PROJECT/deliverables/final.pptx \
  --expected-pages 6 \
  --route-decision PROJECT/route-decision.json \
  --require-route \
  --workflow-state PROJECT/workflow-state.json \
  --require-workflow-state \
  --font-dir PROJECT/project-fonts \
  --require-cjk \
  --require-editability \
  --require-object-manifest \
  --require-manifest-registry \
  --require-text-model \
  --execution-mode dag \
  --parallel-workers 4 \
  --output-dir PROJECT/qa/pipeline-run
```

如果有参考页，加 `--reference-dir PROJECT/reference`；如果是图片生成路线，加 `--visual-generation-plan`、`--visual-generation-manifest` 和 `--require-visual-generation`。

### 发布模式

发布前加入真实的 handoff、人工签核、质量分数和字体嵌入门禁：

```bash
python3 scripts/run_pipeline.py PROJECT \
  --deck PROJECT/deliverables/final.pptx \
  --expected-pages 6 \
  --route-decision PROJECT/route-decision.json \
  --require-route \
  --workflow-state PROJECT/workflow-state.json \
  --require-workflow-state \
  --handoff PROJECT/handoff.json \
  --human-signoff PROJECT/qa/human-closeout.json \
  --font-dir PROJECT/project-fonts \
  --require-cjk \
  --require-embedded-fonts \
  --require-editability \
  --require-object-manifest \
  --require-manifest-registry \
  --release \
  --quality-score 90 \
  --execution-mode dag \
  --parallel-workers 4 \
  --output-dir PROJECT/qa/release-run
```

只有 `release_eligible: true` 才能进入交付候选；`pipeline-result.json.valid` 只说明技术流水线结果，不代表人工签核或最终发布。

## 11. 增量运行和缓存

### 11.1 只检查受影响页面

文字或局部布局修改时：

```bash
python3 scripts/run_pipeline.py PROJECT \
  --deck PROJECT/deliverables/final.pptx \
  --expected-pages 6 \
  --execution-mode dag \
  --parallel-workers 4 \
  --affected-pages 2,5-6 \
  --affected-region hero=80,120,640,260 \
  --page-cache-dir PROJECT/.pipeline-cache/render-pages \
  --output-dir PROJECT/qa/incremental-run
```

### 11.2 什么时候缓存会失效

| 修改 | 需要重跑 | 可以保留 |
|---|---|---|
| 单页 Prompt/图片 | 该 A 页、deck strip、对应 B 页 | 其他已批准页 |
| 单个文字框或布局对象 | 对应 B 页、渲染和页级 QA | 其他页面 |
| 来源/大纲/正式文案 | 受影响叙事和所有受影响页 | 无关来源证据 |
| 路由/设计系统 | 所有下游视觉和可编辑产物 | 来源清单、旧版本用于对比 |
| 字体/渲染器/主题 | 全量渲染和字体门禁 | 语义计划和对象清单 |

缓存是正确性优化，不是免检。发布前仍要执行一次不带 `--affected-pages` 的全量验证；需要清洁运行时使用 `--no-cache`。

## 12. 中断、失败和恢复

### 状态或 handoff 失败

先执行：

```bash
python3 scripts/validate_workflow_state.py PROJECT/workflow-state.json \
  --project-root PROJECT --expected-pages 6 --strict \
  --report PROJECT/qa/workflow-state-validation.json
python3 scripts/validate_handoff.py PROJECT/handoff.json \
  --report PROJECT/qa/handoff-validation.json
```

修复缺失路径、旧哈希、审批或阻塞项后再继续。不要从聊天记录猜测上次完成到哪一页。

### 图片生成失败

- 只重试失败页；保留成功页和旧尝试记录；
- 修改该页 Prompt 或参考策略，记录 retry trigger；
- 达到上限后进入 `revision-required`/`blocked`，不要静默交付低质量图；
- OCR/视觉工具不可用时，记录 `unavailable` 并转人工复核，不得假装通过。

### 可编辑还原失败

- 先看完整原图、source bbox、object manifest 和渲染页；
- 修复拥有问题的对象/资产/文字框，不要在下游用覆盖图掩盖；
- 只重跑受影响的 B 阶段和门禁；
- 无法验证的字、数、Logo、图表数据或几何标记 `manual_required`。

### 字体或渲染失败

确认 `font-report.json`、`font-asset-validation.json`、渲染报告和最终 PPTX OOXML 证据一致。侧载字体文件不等于 PPTX 已嵌入字体；严格交付必须同时满足声明、解析、渲染可见性，并按要求验证嵌入关系。

## 13. 最终交付检查表

### 内容和权威

- [ ] 目标、受众、页数、比例和交付格式明确；
- [ ] 大纲已批准，正式文字和数据有来源；
- [ ] 路由已决定且不为 `needs_user`/`blocked`；
- [ ] 参考图没有越权提供文字、数据、Logo 或品牌权威。

### 图片视觉稿

- [ ] 每页有计划、完整 Prompt、原生源图、项目副本和哈希；
- [ ] 重点词 OCR 可读，颜色落在对应文字框内；
- [ ] 失败只按页重试；
- [ ] deck strip 覆盖全部页面，并且每页已看原图。

### 可编辑 PPTX

- [ ] 正文/标题/标签是原生文本；
- [ ] 图标、插画、面板和复杂艺术元素有独立来源证据；
- [ ] 图表/表格数据可追溯；
- [ ] 没有用整页截图冒充可编辑；
- [ ] 页面渲染无空白、溢出、裁切、字体回退和 z-order 错乱。

### 交付与恢复

- [ ] workflow state、handoff、manifest 和报告哈希一致；
- [ ] 技术 QA 已通过，人工 closeout 已真实记录；
- [ ] `release_eligible` 为 `true`（若要求发布）；
- [ ] 仍有 blocker、placeholder 或 `待验证` 内容时，已在交付报告中明确列出。

详细模块/工具/缓存矩阵见 [`references/operations-matrix.md`](../references/operations-matrix.md)；技能边界见 [`references/three-skill-architecture.md`](../references/three-skill-architecture.md)。
