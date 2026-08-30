# ai-ppt-plus

一个面向 Codex / ChatGPT Skills 的 PowerPoint 工程化技能包：先治理来源和叙事，再选择视觉路线，最后生成、还原、渲染、校验并交付 PPT。

本仓库不是一个“输入一句话就由 Python 独立完成文生图”的黑盒 CLI。技能负责决策和编排；仓库脚本负责确定性处理、证据留存、质量门禁和报告。原生 ImageGen 由宿主运行时提供，不能用代码画图冒充生成事件。

## 先选哪个技能

| 你的目标 | 使用技能 | 输出 | 不负责什么 |
|---|---|---|---|
| 只要好看的图片版 PPT | `ai-ppt-visual-gen`（GordenImagePPTGen） | 每页 PNG、Prompt、生成证据、deck strip、图片型 PPTX | 不生成可编辑 PPTX，不负责整套发布 |
| 把截图/图片/PDF 页还原为可编辑 PPTX | `ai-ppt-editable`（GordenImage2PPTX） | 可编辑 PPTX、原生文字/对象、资产与技术 QA | 不重写叙事，不把整页截图伪装成可编辑 |
| 没有指定，或既要好看又要可编辑 | `ai-ppt-plus`（Super） | 图片视觉中间态 + 可编辑 PPTX + 完整证据包 | 不越权改写已批准内容，不伪造人工签核 |

三者是三个可独立安装的自包含目录：

```text
ai-ppt-plus/                 # 总编排技能
├── scripts/ references/ assets/
├── ai-ppt-visual-gen/       # A1–A5：图片版 PPT
│   ├── scripts/ references/ assets/ tests/
└── ai-ppt-editable/         # B0–B9：图片/内容到可编辑 PPTX
    ├── scripts/ references/ assets/ tests/
```

## 在支持 Skills 的客户端中使用

通常不需要手动拼脚本，直接描述目标即可：

```text
请使用 ai-ppt-plus，把 source/ 下的材料做成一份 8 页中文管理层汇报。
受众是集团高管，16:9，科技商务风；先给我确认大纲和视觉方向，
确认后生成图片视觉稿，再还原成可编辑 PPTX，最后给出逐页 QA 和交付报告。
```

只要图片版：

```text
请使用 ai-ppt-visual-gen，把这份大纲生成 6 页高信息密度图片版 PPT。
每页保留真实文字、Prompt、源图、副本、哈希和 deck strip；重点词“增长率”使用橙色。
```

只做图片转可编辑：

```text
请使用 ai-ppt-editable，把 reference/slide-1.png 到 slide-6.png 还原为可编辑 PPTX。
保持原版布局、层级、颜色和 z-order；正文恢复为原生文字，图标和插画保持独立可移动。
```

## 五分钟安装与自检

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

`probe_environment.py` 会如实报告 Python 包、LibreOffice/Poppler、OCR、字体和 PPTX 后端能力；它退出成功不等于所有能力都可用，要查看 JSON 中各项 `available`。图片生成仍需要宿主可发现的原生图像生成工具。

中文项目可使用仓库内的 `assets/fonts/NotoSansSC-Regular.ttf` 作为本地回退字体：

```bash
mkdir -p PROJECT/project-fonts PROJECT/qa
cp assets/fonts/NotoSansSC-Regular.ttf PROJECT/project-fonts/
cp assets/fonts/font-manifest.json PROJECT/project-fonts/
python3 scripts/validate_font_asset.py \
  --font-dir PROJECT/project-fonts \
  --require-cjk \
  --report PROJECT/qa/font-asset-validation.json
```

## 三条实际工作路径

### 1. Super：先出图，再转可编辑

`ai-ppt-plus` 负责来源、brief、大纲、路由、设计系统、交接、QA 和发布；两个子技能分别负责 A 和 B。完成 A 的图片生成证据和 B 的布局输入后，可以执行确定性串联：

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

这个命令会校验包和环境，校验路由与状态，验证 A 的图片证据，组成 B 的 PPTX，执行技术 QA，并生成 handoff。原生 ImageGen 必须在 A 阶段由宿主运行时调用；该协调器不会伪造图片。

### 2. Visual：只生成图片版 PPT

在 `ai-ppt-visual-gen/` 中准备 `visual-generation-plan.json`，然后：

```bash
cd ai-ppt-visual-gen
python3 scripts/materialize_visual_generation_prompts.py \
  visual-generation-plan.json --in-place
python3 scripts/validate_visual_generation_plan.py \
  visual-generation-plan.json --expected-pages 6
```

接着由宿主的原生 ImageGen 按页生成图片，并把每页的源图、副本、Prompt、模型/工具和哈希写入 `visual-generation-manifest.json`。最后执行：

```bash
python3 scripts/run_visual_pipeline.py visual-generation-plan.json \
  --expected-pages 6 \
  --manifest visual-generation-manifest.json \
  --strip qa/visual-deck-strip.png \
  --image-pptx deliverables/image-only.pptx \
  --report qa/visual-pipeline.json
```

图片型 PPTX 是“一页一张全幅图片”，不能宣称为可编辑 PPTX。

### 3. Editable：只把图片转成可编辑 PPTX

先按 `ai-ppt-editable/SKILL.md` 完成 B0–B9 的来源查看、背景/框架/图标/文字分层、对象清单和布局计划，再组成 PPTX：

```bash
cd ai-ppt-editable
python3 scripts/compose_pptx.py PROJECT/editable/layout.json \
  PROJECT/deliverables/final.pptx \
  --preview-dir PROJECT/qa/preview \
  --font-dir PROJECT/project-fonts \
  --embed-fonts \
  --embedding-report PROJECT/qa/font-embedding.json \
  --strict-input
```

正文、标题、标签和数字应是原生文字；图标、插画和复杂艺术元素应是有来源记录的独立可移动资产；整页截图只能作为明确标注的图片型 fallback，不能冒充编辑性。

## 项目目录建议

```text
PROJECT/
├── source/                 # 原始 PDF/DOCX/XLSX/图片/PPTX/Markdown
├── brief/                  # deck brief、source inventory
├── outline/                # 已批准大纲与正式文字权威
├── design/                 # design-system.yaml
├── route-decision.json     # visual-creation / reference-reconstruction / native-authoring
├── workflow-state.json     # 可恢复状态、审批、阻塞和产物哈希
├── visual/                 # A1–A5 计划、Prompt、图片、manifest、strip
├── editable/               # B0–B9 layout 和资产工作区
├── slide-object-manifest.json
├── text-layout-manifest.json
├── manifest-registry.json  # 跨清单索引（严格 QA 时使用）
├── project-fonts/          # 任务专用、已授权字体
├── deliverables/           # final.pptx 或 image-only.pptx
└── qa/                     # render、QA、handoff、review.html、交付报告
```

## 三种路由怎么选

| 路由 | 什么时候用 | 视觉权威 | 正式文字权威 |
|---|---|---|---|
| `visual-creation` | 没有固定参考图，要生成新的视觉表达 | A1–A5 生成图，经人工确认后锁定 | 已批准大纲/正式内容 |
| `reference-reconstruction` | 用户给了截图、图片页或 PDF 页，要求复刻 | 用户/批准的参考页 | 用户转录或已批准文案 |
| `native-authoring` | 结构化内容、图表或表格优先，直接做原生对象 | 已批准设计系统 | 已批准结构化内容/数据 |

参考图只学习声明的内容：`layout-only` 学构图、层级、密度和阅读路径；`layout-and-style` 额外学习色彩、表面、字体气质和图标语言。参考图里的文字、数字、Logo 和未批准品牌内容不能自动成为正式内容。

## 质量与效率

- A1–A5：内容厚度、视觉框架、完整 Prompt、逐页生成、单页重试、源图留存、OCR/重点词颜色校验、deck strip 复核。
- B0–B9：背景、框架、图标、文字和对象层分离；保持原生文字、可移动资产、比例、z-order 和来源证据。
- O0–O5：状态恢复、路由/交接、跨技能 manifest、技术 QA、人工复核和发布门禁。
- DAG 执行支持内容哈希缓存、页面级渲染缓存、受影响页/区域校验、并行检查，并记录 wall time、cache hit/miss 和 critical path。
- 长任务中断后先校验 `workflow-state.json`、handoff、manifest 和哈希，只重跑失败阶段及其受影响后代。

增量验证示例：

```bash
python3 scripts/run_pipeline.py PROJECT \
  --deck PROJECT/deliverables/final.pptx \
  --expected-pages 6 \
  --workflow-state PROJECT/workflow-state.json \
  --require-workflow-state \
  --execution-mode dag \
  --parallel-workers 4 \
  --affected-pages 2,5-6 \
  --affected-region hero=80,120,640,260
```

发布前必须取消受影响范围限制，执行一次全量渲染、字体/对象/资产/报告门禁和人工 closeout。技术通过不等于人工确认，图片型 PPTX 也不等于可编辑 PPTX。

## 文档入口

- [完整使用教程：从主题/材料到发布](docs/TUTORIAL.md)
- [三技能架构与职责](references/three-skill-architecture.md)
- [O0–O5 / A1–A5 / B0–B9 模块、工具与缓存矩阵](references/operations-matrix.md)
- [路由与共享契约](references/skill-routing.md)
- [性能、缓存和增量运行](references/pipeline-performance.md)
- [根技能规范](SKILL.md)
- [图片版技能规范](ai-ppt-visual-gen/SKILL.md)
- [可编辑技能规范](ai-ppt-editable/SKILL.md)

## 开发者回归

```bash
python3 scripts/run_tests.py --parallel-workers 4
(cd ai-ppt-visual-gen && python3 scripts/run_tests.py --parallel-workers 2)
(cd ai-ppt-editable && python3 scripts/run_tests.py --parallel-workers 1)
python3 scripts/validate_skill_package.py --skill-dir .
python3 scripts/validate_runtime_mirror.py
python3 scripts/validate_routing_contract.py
```

发生失败时，先看对应 run 目录的 stdout/stderr、`workflow-state-validation.json`、`handoff-validation.json` 和 `review.html`，不要直接删除缓存或覆盖原始输入。
