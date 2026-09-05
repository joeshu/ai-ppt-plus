# 图片转全元素可编辑高保真 PPTX 实施清单

目标：每个原图对象都有稳定来源、明确重建类型、最终对象和逐区域视觉证据；任何一项缺失都不能标记为高保真完成。

## P0：阻止错误结果通过

| ID | 任务 | 验收标准 | 状态 |
|---|---|---|---|
| RF-001 | 强制关键区域完整评分 | 原图清单声明的标题、数字、图标、细线等区域均有评分；缺一项即失败 | 已落实 |
| RF-002 | 修正最终对象类型识别 | 文本框、带字形状、连接线、表格、图表和图片按 OOXML 容器分类 | 已落实 |
| RF-003 | 素材多轴质量检查 | 独立素材同时输出轮廓、颜色、内部结构指标 | 已落实 |
| RF-004 | 扩大独立素材修复范围 | 图标、插画、装饰及复杂视觉面板均可进入修复入口 | 已落实 |
| RF-005 | 独立原图空间复核 | 第二次观察提供区域覆盖证据，存在未解释区域时阻断 | 已落实 |
| RF-006 | 统一视觉验收策略 | 布局、文字、素材、关键区域和全局指标使用单一版本化策略 | 已落实：`2026.09-rf006` 策略进入 QualityGate；reference-reconstruction 必须提交 layout/typography/asset 三轴分数 |

## P1：提升实际视觉还原质量

| ID | 任务 | 验收标准 | 状态 |
|---|---|---|---|
| RF-101 | 从截图生成文字目标规格 | 提取文字行、基线、字体候选、字号、行距、重点词及置信度 | 已落实：Astra `typography-target-observation` 专用截图观察合同输出文字目标证据，`text_target_spec` 负责绑定源图 Hash、校验完整性并确定性归一化 |
| RF-102 | 中文真实渲染校准 | 覆盖中文长句、中英数字混排、富文本重点词、换行和字体回退 | 已落实：CI 安装仓库内置 `Noto Sans CJK SC`，并加入 LibreOffice/PDF 中文混排、数字、富文本真实渲染回归；保持 `font_verified=true` 与 `overflow=false` |
| RF-103 | 页面差异自动路由 | 几何、文字、素材、层级和语义差异进入对应修复器 | 已落实：Astra QA Prompt/Schema → DifferenceGraph → RepairRouter 已贯通 geometry/typography/asset/hierarchy/semantic 五类差异 |
| RF-104 | 修复后防回退 | 锁定已通过对象，每轮重渲染并检查已通过区域未退化 | 已落实：主循环对非目标对象执行 object drift guard，并阻断已通过关键区域的后续退化 |
| RF-105 | 多页一致性 | 逐页修复后检查主题、字号层级、重复素材和跨页位置规则 | 已落实：multi-page consistency 已接入最终 COMPLETE 前 gate，对锁定角色文字及重复 logo/资产检查字号、字体、来源和位置一致性 |

## P2：真实交付验收

| ID | 任务 | 验收标准 | 状态 |
|---|---|---|---|
| RF-201 | 12 案例四证据回放 | 每例保存原图、PPTX 渲染、局部差异和实际对象树；candidate 同时满足版本化视觉门禁 | **进行中 / 视觉阻断**：四证据、隐藏 artifact 持久化和 strict visual validator 已落实；现有 12 个 native candidate 虽结构/语义/可编辑性通过，但视觉指标明显低于 `2026.09-rf006`（layout/pixel 0.94），进入逐案例参考图驱动重建修复，不得标记高保真通过 |
| RF-202 | WPS 桌面端验收 | 文件打开、排版、字体、溢出、编辑和截图证据绑定 PPTX Hash | 工程合同已落实、待真实桌面环境实测：独立 `desktop` host profile，必须绑定同一 PPTX Hash 与逐页截图 |
| RF-203 | iPhone WPS 验收 | 同一文件逐页截图并记录字体替换和换行差异 | 工程合同已落实、待真实 iPhone WPS 实测：独立 `ios` profile，并强制字体替换、换行差异复核 |
| RF-204 | 统一能力口径 | 工程门禁通过与视觉实证通过分别记录，文档不再混用 | 已落实到代码：capability-status 把 technical、automated visual fidelity、four-evidence、human review、desktop host、iOS host 分开记录；只有全部满足才 `release_eligible=true`。当前由于 RF-201 视觉门禁未通过，能力状态必须保持 blocked |

## RF-201 逐案例修复原则

1. 不降低 `2026.09-rf006` 阈值换取绿灯。
2. 不用整页截图、切片拼图或隐性背景图冒充可编辑高保真。
3. 先用 `case-visual-diagnostics.json` 定位颜色、亮度、密度和最差网格区域，再归因到 geometry / typography / asset / hierarchy。
4. 每个案例修复后必须重新：PPTX 合成 → LibreOffice 渲染 → visual fidelity gate → native editability → semantic audit → mutation smoke → four-evidence。
5. 12/12 均满足自动视觉门禁后，才进入人工视觉确认和 WPS 双端验收。

推进顺序：RF-001～RF-006 → RF-101～RF-105 → RF-201～RF-204。只有 engineering、visual human review 和真实 desktop/iOS host validation 均通过时，才允许标记最终高保真交付通过。
