# ai-ppt-plus

可编辑、可渲染、可验证的 PowerPoint 工程化生成技能。

## 能力

- 从 PDF、DOCX、Excel、Markdown、图片和已有 PPTX 组织演示文稿
- 区分视觉中间态生成与参考图重建
- 图片到可编辑 PPTX 的对象拆解与还原
- 图标、装饰、艺术字的提取、去底、切分和定位校验
- L0-L5 编辑性等级与项目级质量门禁
- 声明字体、解析字体、最终渲染可见性的字体三重证据门禁
- `python-pptx` 后处理嵌入 OOXML 字体与 `.fntdata` 部件
- 渲染、视觉对比、报告注册和交付前复验
- 统一 Manifest Registry：关联页面、区域、对象、资产与 QA 门禁，并校验最终 deck 哈希
- TextSpec/TextRunSpec 文本版式契约：统一内容、字体、字号、Run、换行与源坐标校验
- R13 等回归案例的不可变基线归档与 SHA-256 校验
- DAG 流水线、内容哈希缓存、页面级增量渲染、受影响区域 QA 与并行检查
- Schema、任意 N/不规则区域、字体缺失、PPTX 解包和 Golden Render 回归，以及 GitHub Actions CI
- 统一技术/人工/交付报告协议与项目级 `review.html` 审阅页
- `ai-ppt-plus`、`ai-ppt-visual-gen`、`ai-ppt-editable` 三个独立技能入口及机器可读职责路由

## 三技能入口

| 技能 | 独立用途 | 在全流程中的职责 |
|---|---|---|
| `ai-ppt-plus` | 多源材料到完整演示项目 | 叙事、路线、设计权威、跨技能 QA 与交付门禁 |
| `ai-ppt-visual-gen` | 图片版 PPT、视觉中间稿 | A1–A5 文生图、单页重试、生成源留存、deck strip |
| `ai-ppt-editable` | 参考图/内容到可编辑 PPTX | 对象拆解、PPTX 创作、渲染与技术 QA |

三个入口共享同一套 `scripts/`、`assets/`、`references/`，不复制后段
图转 PPTX 实现。详细边界见
[`references/three-skill-architecture.md`](references/three-skill-architecture.md)。

默认运行 DAG 流水线；局部修复可只验证受影响页面和区域：

```bash
python3 scripts/run_pipeline.py PROJECT --deck deck.pptx --expected-pages 6 \
  --affected-pages 2,5-6 --affected-region hero=80,120,640,260
```

在 DAG 模式下，渲染器默认把已验证的页面 PNG 保存在
`.pipeline-cache/render-pages/`。每页缓存键包含该页 OOXML 关系闭包、主题/母版/
版式、页面顺序、DPI 和任务字体目录指纹；完整命中时可跳过 LibreOffice 和
Poppler，部分命中时只重新栅格化缺失页。只要有一页变化，LibreOffice 仍可能
需要重新转换整份 PPTX，但未变化页和下游页面级 QA 不会重复生成。可用
`--page-cache-dir PATH` 指定缓存位置，`--no-cache` 会同时关闭流水线和页面缓存。

每次运行会在输出目录生成 `pipeline-result.json`、`project-report.json`、
`report-bundle-preflight.json`、`report-bundle-validation.json` 和 `review.html`。
报告包门禁会核对 PPTX、最终结果、索引、聚合报告、审阅页和子报告的 SHA-256
及增量范围；技术通过、人工待审和可交付状态彼此独立；增量运行仍需在发布前
执行一次全量验证。

主规范见 [`SKILL.md`](SKILL.md)。
