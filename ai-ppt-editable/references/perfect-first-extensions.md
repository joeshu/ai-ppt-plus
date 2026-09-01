# 完美第一版外围增强契约

## 目的

`完美第一版`是本技能的冻结核心：背景/框架/图标分层、原生对象写入、渲染和既有 QA 算法保持同步。外围增强只负责把独立证据接入核心，并把“看起来像成功”的情况变成可阻断的契约；它不是另一套简化引擎。

入口是 `scripts/perfect_first_adapter.py`。`compose_pptx.py` 在组件展开后、调用同步 authoring backend 前运行它；`run_pipeline.py` 在有 `layout.json` 时运行同一份 contract preflight。这样组合器与流水线不会各自解释一遍同一份证据。

## 五个增强面

### 原生图表

`chart-reconstruction.json` 是独立数据权威。只有 `representation: native_chart` 且 `source_data_status: verified` 的记录会被合并进 `layout.json` 的 `charts[]`，包括类别、系列、颜色、标题、数据标签、数据源和数据快照哈希。含 `null` 的未完结系列不得晋级原生图表。

`static_line_primitives`、`svg`、`raster_fallback` 不会被静默改写为 native chart。若布局里仍有同 ID 的 `charts[]`，必须同时提供 `primitive_specs` 或明确资产，否则直接阻断，避免把视觉转录冒充成可编辑数据图表。

```bash
python3 scripts/compose_pptx.py layout.json deck.pptx \
  --chart-manifest chart-reconstruction.json \
  --strict-input --adapter-report build/perfect-first.json
```

### 渐变复刻

简单、可确定表达的渐变保留为原生 `a:gradFill`，适配层统一 `#RGB/#RRGGBB/#RRGGBBAA`、百分比/小数停靠点和角度，减少不同输入格式造成的色带、透明度和方向漂移。

复杂的背景光晕、框架波纹和独立元素仍按 B2/B3/B4 资产路由。`gradient-visual-manifest.json` 校验角色—路由、透明度、嵌入和渲染可见证据；不会为了“可编辑”而把复杂渐变压扁成一个颜色近似的矩形。

### 字体校准

适配层把 `font_family`、`font_color`、`size_pt`、`content` 和 `bbox` 规范化为完美核心接受的 `font`、`color`、`size`、`text`、坐标字段，并递归处理 run 的局部样式。它还输出布局绑定的字体契约，记录每个文本对象的字体、字号、颜色、粗体和内容覆盖。

这份契约是机器前置检查，不替代 `typography-calibration.json` 的参考图墨迹框测量，也不把“本机可渲染”误报成“PPTX 已嵌入”。字体资产、渲染和嵌入仍由原有字体 gates 负责。

### 对象级验收

`build_object_manifest.py` 为每个有坐标的对象记录 `declared_geometry`，并在根部声明 `object-geometry-contract/v1`。`inspect_editable_objects.py` 可递归识别组内对象，按规范化 x/y/w/h 对比 PPTX 实际 shape box，并按 `object_type` 对比 native text/shape/table/chart/group/picture。

```bash
python3 scripts/inspect_editable_objects.py deck.pptx \
  --object-manifest slide-object-manifest.json \
  --require-types --require-geometry --geometry-tolerance 0.02 \
  --report build/editable-object-audit.json
```

几何或类型失败属于对象责任层的问题：修复 layout、对象或资源归属，不通过降低阈值或添加整页图片绕过。

### 案例自动入库

`prepare_case.py` 仍只接受用户提供的图片/PPTX；可选地把候选 PPTX 的新鲜 score 和 QA reports 一起复制到内容寻址的 case 目录，并保存哈希与概要。它不会自动批准。

人工确认后可用一条显式命令完成“批准 → 导出 JSONL → CPU 检索索引”：

```bash
python3 scripts/ingest_approved_case.py \
  --registry datasets/ai-ppt-editable/cases.json \
  --case-id CASE_ID --candidate-id CANDIDATE_ID \
  --approved-by reviewer --approval-note "已核对视觉、文字和可编辑性" \
  --human-confirmed
```

这条命令保留人工确认边界，不训练或晋升模型权重。GitHub Actions 的定时/手动 workflow 仍以 `run_training_cycle.py` 为无人值守驱动；有 GPU 的外部 trainer 只能通过显式 `AI_PPT_TRAINER_COMMAND` 接入。没有 GPU 时，自动产出的是可追溯数据集与 CPU 精确检索索引，不冒充视觉模型训练。

## 回归闭环

每一轮改进都保存输入/候选/报告/哈希，依次运行：

1. perfect-first contract preflight；
2. 完美第一版 authoring backend；
3. render + visual comparison；
4. object type/geometry + semantic audit；
5. 人工确认后才进入 ingestion/retrieval。

失败按责任层分类：图表数据、渐变资产、字体/文本、对象几何或案例证据。修复后只重跑受影响区域，再做一次全页回归；最多三轮自动修复，未解决项保持 `manual_required`。
