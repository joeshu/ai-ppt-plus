# Technical Architecture

本文档描述 `ai-ppt-plus` 当前主线架构、核心 IR、运行时边界和数据流。目标读者是维护者、扩展者和需要定位复杂回归问题的开发者。

## 1. 系统目标

`ai-ppt-plus` 的目标不是单纯生成 PPT 文件，而是构建一个可追溯、可编辑、可验证、可回滚的 PowerPoint 工程系统。

系统必须同时满足：

- 视觉接近目标；
- 原生对象语义正确；
- 文本、表格、图表可编辑；
- 复杂视觉资产独立；
- 修改范围受控；
- 多轮修复不会污染已接受结果；
- 结果可以形成回归样本和 Golden 基线。

## 2. 分层架构

```text
┌──────────────────────────────────────────────────────────────┐
│                     ai-ppt-plus Orchestrator                 │
│ source authority / outline / route / shared state / release │
└──────────────────────────────────────────────────────────────┘
                 │                           │
        visual-creation               editable/native route
                 │                           │
                 ▼                           ▼
┌──────────────────────────┐     ┌─────────────────────────────┐
│ ai-ppt-visual-gen        │     │ ai-ppt-editable             │
│ A1–A5 visual generation │     │ B0–B9 + Astra reconstruction│
└──────────────────────────┘     └─────────────────────────────┘
                 │                           │
                 ▼                           ▼
      native Image Generation      Deterministic PPTX Engine
                                             │
                                             ▼
                                   Render / Inspect / Audit
                                             │
                                             ▼
                                   DifferenceGraph + Repair
                                             │
                                   ┌─────────┴─────────┐
                                   ▼                   ▼
                              accepted-state      rollback
```

## 3. 职责边界

### 3.1 Orchestrator

负责：

- source inventory；
- content authority；
- outline contract；
- page route；
- design system；
- workflow state；
- worker handoff；
- aggregated QA；
- release eligibility。

不负责：

- 直接替代 visual worker 的生成逻辑；
- 直接替代 editable worker 的分层和 authoring；
- 伪造人工签核。

### 3.2 Visual Worker

负责：

- 页面视觉规划；
- 复杂 Prompt；
- 原生生图调用边界；
- 生成记录与源图留存；
- deck strip；
- image-only PPTX。

### 3.3 Editable Worker

负责：

- 参考页分层；
- native object planning；
- PageGraph；
- deterministic authoring；
- render / inspect / semantic/native audit；
- DifferenceGraph；
- repair execution；
- asset regeneration boundary；
- Object Drift Guard；
- accepted-state；
- distillation / golden evidence。

## 4. Astra Visual Reconstruction Engine

Astra 不是 PPTX writer，而是视觉理解和视觉 QA 层。

### 4.1 Provider-neutral contract

Astra contract 只定义输入输出结构，不绑定某个具体 provider。

两个主要任务：

- `visual-reconstruction` → `PageGraph`
- `visual-qa` → `DifferenceGraph`

系统要求输出严格 JSON，不能返回自由格式补丁直接进入执行层。

### 4.2 为什么 provider-neutral

这样可以：

- 替换 reasoning provider 而不动 PPTX engine；
- 做离线 mock / replay；
- 用相同 contract 做 CI；
- 将视觉理解和确定性执行解耦；
- 保持模型能力升级不破坏 authoring 稳定性。

## 5. PageGraph IR

PageGraph 是页面的规范化对象图。

### 5.1 Node types

- text
- shape
- table
- chart
- icon
- illustration
- image
- connector
- group
- background
- decoration

### 5.2 Relations

- contains
- belongs_to
- aligned_left/right/top/bottom
- aligned_center_x/y
- equal_width/height/gap
- connects_to
- overlaps
- anchors_to

### 5.3 Geometry contract

统一使用 normalized slide fraction：

```text
x, y, w, h ∈ [0, 1]
```

旧格式如果是 px：

```text
x_fraction = x_px / ref_width
w_fraction = w_px / ref_width
```

归一化只发生在 bridge 层。下游 Repair、Astra QA、authoring contract 不应混用 px、inch 和 fraction。

## 6. Manifest Bridge

现有 `layout.json` 和 slide object manifest 仍是 deterministic authoring 的正式输入。

Manifest Bridge 的职责：

```text
legacy layout / object manifest
            │
            ▼
   normalize geometry/types
            │
            ▼
         PageGraph
```

它同时保留：

- TextSpec / rich-text runs；
- table/chart snapshot；
- native_required；
- provenance；
- source hash；
- asset policy。

## 7. DifferenceGraph

DifferenceGraph 是统一的 QA/repair 中间表示。

```json
{
  "id": "typography:title",
  "object_id": "title",
  "domain": "typography",
  "severity": "P2",
  "confidence": 0.96,
  "metrics": {},
  "evidence": {},
  "proposed_patch": {
    "font_size": 30
  }
}
```

### Domains

#### geometry

允许：

- x/y/w/h
- rotation
- crop
- radius
- padding

关系型 `gap` 需要 relation-aware 修复，不能无依据地改单一对象。

#### typography

允许：

- font
- font_size
- bold/italic
- color
- spacing
- margin
- autofit
- runs

#### asset

允许：

- scale
- crop
- rotation
- opacity
- regenerate
- generation_prompt
- background_mode

#### semantic

允许：

- native_required
- table_data
- chart_data
- group_children
- connector_targets

跨类型转换默认 fail-closed。

## 8. Repair Router

Repair Router 是模型输出进入执行层前的安全边界。

默认规则：

- 只允许 domain 对应的白名单字段；
- confidence 低于阈值 → deferred；
- rejected patch key → deferred；
- P0 semantic mutation → fail-closed；
- page-level pixel diagnostic 不执行猜测性 geometry patch。

模型能“建议”，不能“直接执行”。

## 9. Deterministic Repair Executors

执行器只修改 authoring deck contract，不直接修改 OOXML。

### GeometryRepair

- 数值有限性检查；
- slide bounds 检查；
- fraction/inch contract 处理；
- crop/radius/padding 校验。

### TypographyRepair

只允许 native text object。

更新 runs 时：

```text
runs[] → text recompute
```

避免 manifest 与真实文本不一致。

### AssetRepair

只允许独立 asset object。

- scale around center；
- crop；
- rotation；
- opacity；
- background mode；
- brand lockup crop protection。

### SemanticRepair

只允许在当前 native 类型内部修复。

例如：

- table_data 只能修 native table；
- chart_data 只能修 native chart；
- group_children 只能修 native group。

## 10. EXTERNAL_ASSET 状态

资产 `regenerate=true` 不由 deterministic executor 实际生图。

执行器生成：

```json
{
  "object_id": "hero-icon",
  "generation_prompt": "...",
  "background_mode": "transparent",
  "preserve_geometry": {
    "x": 0.68,
    "y": 0.18,
    "w": 0.16,
    "h": 0.16
  }
}
```

随后状态进入：

```text
EXTERNAL_ASSET
```

只有外部原生生图完成并验证后才能 resume。

## 11. Asset Orchestrator

外部生成结果要经过两级门禁。

### Gate 1: deterministic validation

- object_id match；
- file exists；
- PNG；
- width/height > 0；
- SHA256；
- transparent alpha；
- green/red key-color corners；
- background mode match。

### Gate 2: Asset QA v2

核心字段：

```json
{
  "score": 0.95,
  "structure_score": 0.96,
  "style_score": 0.93,
  "confidence": 0.94,
  "issue_codes": [],
  "approved": true
}
```

只有结构验证和视觉 QA 都通过才能绑定。

## 12. Asset Retry Policy

自动重试只由受控 `issue_codes` 驱动。

例如：

```text
silhouette_mismatch
 → silhouette + structure directives

color_mismatch
 → color directive

gradient_flow_mismatch
 → color + composition directives
```

自由文本 reasons 不参与 retry control。

低 confidence QA：

- 不接受；
- 不自动消耗 retry budget。

默认最大 native attempts = 3。

之后输出 user choice：

- continue-native-generation
- crop-matting-fallback

## 13. Rendering 与 Deterministic Evidence

单轮 iteration 的执行链：

```text
layout
 → compose_pptx.py
 → editable.pptx
 → render_pptx.py
 → render
 → inspect_pptx.py
 → build_object_manifest.py
 → validate_native_editability.py
 → semantic_object_audit.py
 → compare_visual.py
 → evidence bundle
```

Astra Visual QA 与 deterministic evidence 是并行证据来源，不能互相覆盖。

## 14. Evidence Bridge

Evidence Bridge 将 deterministic outputs 转成 DifferenceGraph finding。

典型例子：

- visual SSIM 低 → page-level geometry diagnostic；
- semantic audit error → P0 semantic finding；
- native structure warning → structured finding。

全局 pixel failure 不会自动生成对象级 x/y/w/h patch。

## 15. Object Drift Guard

Object Drift Guard 用 stable object ID 计算 fingerprint。

Tracked collections：

- texts
- shapes
- tables
- charts
- icons
- groups
- panels

Fingerprint domains：

- geometry
- text
- style
- asset
- semantic
- overall

### Allowed mutation source

Normal repair：

```text
repair-execution-report.applied[].object_id
```

Asset resume：

```text
asset-resolution-report.resolved[].object_id
```

不是来自 model proposed patch。

## 16. Iteration State Machine

```text
UNDERSTAND
    ↓
AUTHOR
    ↓
RENDER
    ↓
QA
    ↓
REPAIR
    ├──→ EXTERNAL_ASSET → resume
    ↓
GATE
    ├──→ COMPLETE
    └──→ BLOCKED / rollback
```

默认 repair loop 有上限，避免无限修复。

## 17. accepted-state

`accepted-state.json` 表示“上一轮已经通过 regression guard 的确定性状态”。

关键字段：

- case_id
- accepted_iteration
- layout
- pptx
- pixel_fidelity_score
- semantic_accuracy
- blocking_count
- native_editability_valid

下一轮 source resolution：

```text
accepted-state
  > accepted history
  > candidate
```

## 18. Regression Decision

rollback 条件包括：

- visual score decrease；
- blocking count increase；
- native editability regression；
- semantic accuracy regression；
- unauthorized drift。

rollback 后保留上一 accepted layout。

## 19. Distillation Data Flow

```text
iteration-record
   + asset-resolution
   + human approval
          │
          ▼
Distillation Record
          │
          ├─ positive
          ├─ hard_negative
          └─ rejected
          │
          ▼
Golden Promotion Gate
```

Distillation Record 需要保留 source lineage：

- source_accepted_iteration
- source_layout

这使样本可复现，而不是只知道“最后结果很好”。

## 20. Golden Promotion

Golden 是版本化不可变基线。

Promotion 需要：

- visual threshold；
- native editability；
- semantic accuracy = 1.0；
- semantic audit complete；
- zero blockers；
- zero drift；
- human approval；
- source lineage；
- stable streak。

Golden manifest 保留：

- version；
- previous_golden；
- rollback_to_version；
- source_iteration；
- source_lineage；
- artifacts；
- semantic_evidence；
- promotion_evidence。

## 21. 12-case Regression Matrix

真实 12-case suite 用于防止只修一个示例后破坏其他能力。

覆盖：

- routing；
- shapes；
- tables；
- rich-text；
- fonts；
- charts；
- assets；
- irregular frameworks；
- multi-slide；
- fallback；
- portability；
- idempotency/cache。

Strict replay：

```bash
python evals/case-replay-12/run_replay_suite.py --strict
```

## 22. Provider-neutral Full-loop Test

`test_astra_provider_neutral_full_loop.py` 是控制平面集成测试。

它不重新实现 PPTX writer，而是验证模块之间的数据和状态连续性：

```text
DifferenceGraph
 → Router
 → Repair Executor
 → EXTERNAL_ASSET
 → Asset Validation
 → Asset QA v2
 → Bind
 → Accepted State
 → Next Source Resolution
 → Distillation
 → Golden
```

## 23. 为什么保留 deterministic backend

视觉模型擅长：

- 理解视觉；
- 判断差异；
- 提出局部修复方向。

它不擅长稳定保证：

- OOXML 正确性；
- native table/chart semantics；
- exact object mutation scope；
- font/runs consistency；
- deterministic reproducibility。

因此架构选择：

```text
AI = reasoner / QA judge
Deterministic engine = writer / executor / auditor
```

这是当前系统最重要的技术边界。
