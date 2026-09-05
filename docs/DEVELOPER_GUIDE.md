# Developer Guide

本文档面向维护 `ai-ppt-plus`、新增能力、修复回归和扩展工具链的开发者。

## 1. 开发原则

任何修改都应优先回答四个问题：

1. 责任属于 Orchestrator、Visual Worker 还是 Editable Worker？
2. 修改的是 reasoning contract、deterministic execution、evidence 还是 release gate？
3. 哪些已有 case 可能被影响？
4. 如何证明只修了目标问题，没有引入无关漂移？

不要直接用“视觉更像”作为完成标准。

## 2. 仓库关键区域

```text
scripts/                         # 根编排、验证、性能、distillation 工具
references/                      # 根架构和操作规范
assets/                          # schemas、policies、fonts、runtime contracts
docs/                            # 用户与开发者文档
evals/                           # 根级 replay / distillation cases

ai-ppt-visual-gen/
  scripts/ references/ assets/ tests/

ai-ppt-editable/
  reconstruction/               # Astra/repair/accepted-state/distillation/golden 核心
  scripts/                       # PPTX compose/render/inspect/audit
  references/
  assets/
  evals/
  tests/
```

## 3. Editable 核心模块

`ai-ppt-editable/reconstruction/`：

- `graph_ir.py`：PageGraph IR；
- `difference_graph.py`：DifferenceGraph；
- `astra_contract.py`：provider-neutral reconstruction / QA contract；
- `manifest_bridge.py`：legacy layout/object manifest → PageGraph；
- `repair_router.py`：whitelist/confidence/safety routing；
- `repair_executors.py`：Geometry/Typography/Asset/Semantic repair；
- `asset_orchestrator.py`：generated asset validation / bind；
- `asset_quality_qa.py`：Asset QA v2；
- `asset_retry_policy.py`：bounded native retry；
- `object_drift_guard.py`：stable fingerprint / unauthorized drift；
- `accepted_state.py`：accepted-state persistence / source resolution；
- `distillation_record.py`：iteration → distillation evidence；
- `distillation_selection.py`：positive/hard-negative/rejected；
- `golden_promotion.py`：immutable Golden gate；
- `quality_gate.py`：多轴 gate；
- `evidence_bridge.py`：deterministic evidence → DifferenceGraph。

## 4. Authoring 工具链

核心 deterministic scripts：

```text
compose_pptx.py
render_pptx.py
inspect_pptx.py
build_object_manifest.py
validate_native_editability.py
semantic_object_audit.py
compare_visual.py
```

标准顺序：

```text
layout.json
 → compose_pptx
 → editable.pptx
 → render_pptx
 → inspect
 → object manifest
 → native editability
 → semantic audit
 → visual comparison
```

修复逻辑应该改 authoring contract，不应该跳过这条链直接 patch PPTX XML。

## 5. 常用验证命令

### 5.1 Root package

```bash
python scripts/validate_skill_package.py --skill-dir .
python scripts/validate_routing_contract.py
python scripts/run_tests.py --parallel-workers 4 --report test-report.json
```

### 5.2 Visual worker

```bash
python ai-ppt-visual-gen/scripts/validate_skill_package.py --skill-dir ai-ppt-visual-gen
python ai-ppt-visual-gen/scripts/run_tests.py --parallel-workers 4 --report visual-skill-test-report.json
```

### 5.3 Editable worker

```bash
python ai-ppt-editable/scripts/validate_skill_package.py --skill-dir ai-ppt-editable
python ai-ppt-editable/scripts/validate_routing_contract.py
python ai-ppt-editable/scripts/run_tests.py --report editable-skill-test-report.json
```

### 5.4 Environment

```bash
python scripts/probe_environment.py --output environment-report.json
python scripts/validate_environment_contract.py \
  --report environment-report.json \
  --output environment-validation.json
python scripts/validate_runtime_mirror.py --report runtime-mirror-report.json
```

## 6. Astra 测试入口

推荐直接运行：

```bash
PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_reconstruction_engine.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_reconstruction_integration.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_astra_iteration_batch.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_asset_quality_qa.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_object_drift_guard.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_accepted_state.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_distillation_selection.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_golden_promotion.py

PYTHONPATH=ai-ppt-editable \
python ai-ppt-editable/tests/test_astra_provider_neutral_full_loop.py
```

## 7. 12-case replay

### Build Astra requests

```bash
python evals/case-replay-12/build_astra_closed_loop_batch.py \
  --output-dir .distillation/astra-closed-loop \
  --strict
```

### Real replay

```bash
python evals/case-replay-12/run_replay_suite.py \
  --output-dir .distillation/case-replay-12-runs \
  --strict
```

### QA ingestion

输入约定：

```text
batch/<case-id>/page-graph.json
batch/<case-id>/deterministic-difference-graph.json
responses/<case-id>.json
```

运行：

```bash
python evals/case-replay-12/ingest_astra_qa_batch.py ...
```

### Iteration

单 case：

```bash
python evals/case-replay-12/run_astra_iteration.py ...
```

batch：

```bash
python evals/case-replay-12/run_astra_iteration_batch.py ...
```

## 8. 开发一个新 Repair 类型时

必须按以下顺序：

1. 明确 DifferenceGraph domain；
2. 增加/确认 whitelist key；
3. 增加 Router contract test；
4. 增加 executor validation；
5. 增加 negative test；
6. 增加 drift scope test；
7. 加入至少一个相关 replay case；
8. 确认 Distillation Record 能记录该修复；
9. 跑完整 CI。

不要只在 executor 里加一个字段然后结束。

## 9. 新增模型输出字段时

模型输出字段分两类：

### Evidence-only

如自由文本 explanation / reason。

这些字段：

- 可以记录；
- 不应直接控制执行。

### Machine-control

如：

- issue_codes；
- proposed_patch；
- confidence；
- object_id；
- target_type。

这些字段必须：

- enum/schema 限制；
- object ID 校验；
- confidence gate；
- whitelist；
- fail-closed。

## 10. Asset Generation 扩展规则

新增 asset kind 时，必须明确：

- source authority；
- background mode；
- structural validation；
- visual QA thresholds；
- issue code mapping；
- retry behavior；
- user choice at retry exhaustion；
- bind 时允许修改的字段。

默认 bind 只能更新：

- file；
- source_sha256；
- background_mode；
- generation_provenance。

几何必须保持不变。

## 11. Debugging 顺序

当最终 PPTX 与参考差异大时，按责任层定位：

### Step 1: 输入/分层错误？

检查：

- PageGraph；
- object IDs；
- semantic types；
- layout units。

### Step 2: Router 错误？

检查：

- merged DifferenceGraph；
- confidence；
- deferred；
- rejected patch keys。

### Step 3: Executor 错误？

检查：

- repair-execution-report.json；
- applied / skipped / regeneration_requests。

### Step 4: Authoring 错误？

检查：

- layout.json；
- inspect.json；
- native-editability.json；
- semantic-audit.json。

### Step 5: Renderer / font 错误？

检查：

- render-report.json；
- environment report；
- font fallback / embedding。

### Step 6: Asset 错误？

检查：

- asset structural validation；
- Asset QA v2；
- issue_codes；
- retry history。

### Step 7: 无关对象被改？

检查：

- object-drift-report.json；
- drift_allowed_object_ids。

## 12. 不要用错误层修问题

例：

- 字号不对 → TypographyRepair，不要重新生整张图；
- 卡片位置不对 → GeometryRepair，不要改 prompt；
- 图标样式不对 → Asset generation / Asset QA，不要用 native shape 粗画；
- 表格不是原生表格 → Semantic/native authoring，不要截图覆盖；
- WPS 字体差异 → font/render layer，不要修改内容文案。

## 13. Accepted-state Debugging

如果 iteration 2 又从 candidate 开始：

检查：

```text
<output>/<case-id>/accepted-state.json
```

并确认：

- accepted_iteration < current iteration；
- layout path 存在；
- 前轮 iteration-record accepted=true；
- status 不是 rolled-back。

## 14. Object Drift Debugging

Normal repair 的 allowed IDs 必须来自：

```text
repair-execution-report.applied[]
```

Asset resume 必须来自：

```text
asset-resolution-report.resolved[]
```

如果代码开始从 DifferenceGraph proposed_patch 推导 allowlist，应视为回归。

## 15. Distillation Debugging

Positive 样本必须显式拥有：

- accepted=true；
- human_approved=true；
- native_editability_valid=true；
- semantic_accuracy=1.0；
- semantic audit；
- zero drift；
- no rollback；
- no unresolved user-choice；
- source lineage。

缺证据时应进入 rejected，而不是默认 true。

## 16. Golden Debugging

如果本应晋升却被拒绝，按 evaluation reasons 检查：

- visual threshold；
- native editability；
- semantic audit；
- object coverage；
- blockers；
- drift；
- human approval；
- source lineage；
- stable streak。

不要绕过 gate 手工改 Golden manifest。

## 17. CI 结构

CI 的主 job `contract-and-regression` 包含：

1. checkout / Python；
2. deterministic rendering deps；
3. SVG dependency；
4. Python compile；
5. self-contained package/routing；
6. environment/runtime mirror；
7. worker smoke tests；
8. Astra contract tests；
9. 12-case Astra closed-loop batch；
10. schema/DAG/package/golden regressions；
11. social-channel real PPTX replay；
12. 12-case visual/native-editability replay；
13. distillation matrix；
14. strict P2 guards；
15. whitespace；
16. reports upload。

## 18. PR 建议

优先小 PR：

```text
1 个责任问题
+ 对应实现
+ 对应测试
+ 对应 replay/evidence
```

避免将大量无关 repair、docs、CI、fixtures 一次塞进同一个 PR。

## 19. Performance

优先优化：

- page-level cache；
- render cache；
- incremental affected pages；
- parallel validation；
- accepted-state continuation；
- 不重复生图；
- 不重复 author/render 未受影响页。

不要为了速度跳过 semantic/native/object drift gate。

## 20. 完成定义

开发任务只有同时满足以下条件才算完成：

```text
implementation correct
+ unit/contract test
+ regression test
+ relevant replay
+ no unrelated drift
+ CI green
+ documentation updated when contract changes
```
