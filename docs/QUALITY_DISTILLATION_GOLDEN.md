# Quality, Distillation and Golden Baselines

本文档描述 `ai-ppt-plus` 如何定义质量、如何阻止“视觉变好但语义变坏”的回归，以及如何把稳定结果转化为可复用 Distillation 数据和 Golden 基线。

## 1. 为什么不能只看视觉相似度

图片转 PPTX 的常见误区是只优化 pixel similarity。

这会导致：

- 表格被截图替代；
- 文本被栅格化；
- 图表失去 workbook data；
- 图标与插画被合并进背景；
- 未授权对象被移动；
- 视觉接近但内容/语义错误。

因此本系统把质量拆成多个独立维度。

## 2. 质量维度

### 2.1 Visual fidelity

主要证据：

- pixel fidelity score；
- blurred layout SSIM；
- critical region metrics；
- renderer comparison。

视觉只是一条轴，不能单独放行。

### 2.2 Native editability

必须证明：

- 没有 full-slide raster 冒充编辑性；
- 文本是原生文本对象；
- table/chart/group 保持原生语义；
- 独立 asset 可移动；
- mutation smoke test 可执行。

### 2.3 Semantic accuracy

高质量候选默认需要：

```text
semantic_accuracy = 1.0
```

并且不能只依赖汇总数字。

必须存在底层 semantic audit：

```json
{
  "valid": true,
  "accuracy": 1.0,
  "error_count": 0,
  "warning_count": 0,
  "expected_object_count": 8,
  "audited_object_count": 8
}
```

完整对象覆盖要求：

```text
audited_object_count == expected_object_count
```

## 3. DifferenceGraph Severity

统一严重度：

- P0：结构/语义不可接受错误；
- P1：关键视觉或对象错误；
- P2：局部质量偏差；
- P3：低风险优化。

Quality Gate 默认不允许 P0/P1 未解决后宣称通过。

## 4. Deterministic Evidence 优先级

Deterministic evidence 具有不可被模型覆盖的地位。

例如：

- semantic audit 报 P0 → Astra 不能通过文字解释消除；
- native editability fail → 高 pixel score 不能放行；
- Object Drift Guard fail → 视觉提升不能放行。

Astra 可以补充 visual findings，但不能删除 deterministic blockers。

## 5. Diagnostic-only Visual Finding

全页 visual metric 失败时，系统可以产生：

```text
slide:<n>:visual
```

这类 finding：

- 保留在 DifferenceGraph；
- 可以阻止 Quality Gate；
- 不会直接生成猜测性的对象坐标 patch；
- 不会冻结其他高置信度 object-local repair。

这样避免“因为整页差异大，就随机移动元素”。

## 6. Object Drift Guard

### 6.1 为什么需要

一个 repair 只应该改变目标对象。

如果修标题时正文、图标、表格也发生变化，即使视觉提升，也属于不可接受的 side effect。

### 6.2 Fingerprint

每个对象计算：

- geometry；
- text；
- style；
- asset；
- semantic；
- overall hash。

### 6.3 Allowed IDs

Normal repair：

```text
repair-execution-report.applied[].object_id
```

Asset resume：

```text
asset-resolution-report.resolved[].object_id
```

### 6.4 Fail-closed

以下对象不能自动加入 allowlist：

- only proposed；
- skipped；
- deferred；
- historic generated assets；
- missing execution evidence。

缺 report 时：

```text
allowed IDs = ∅
```

## 7. Regression Decision

每轮 iteration 与上一 accepted baseline 比较。

rollback 条件：

### visual regression

```text
current_pixel < previous_pixel - tolerance
```

### blocker regression

```text
current_blocking_count > previous_blocking_count
```

### native editability regression

```text
previous=true && current!=true
```

### semantic regression

```text
previous.semantic_accuracy == 1.0
&& current.semantic_accuracy != 1.0
```

### unauthorized drift

```text
object_drift.valid == false
```

## 8. accepted-state

每个 case 只允许“已接受状态”成为下一轮基础。

```text
candidate
  ↓ iteration 1
accepted-state #1
  ↓ iteration 2
accepted-state #2
  ↓ iteration 3
...
```

被 rollback 的 iteration 不会成为 source。

### source resolution priority

```text
accepted-state.json
 → accepted iteration history
 → original candidate
```

### Lineage

每轮记录：

- source accepted iteration；
- source layout path。

这两项随后进入 Distillation Record 和 Golden manifest。

## 9. Distillation Record

Distillation 的目标不是简单保存“成功案例”，而是保存一次修复的因果证据。

记录内容包括：

### Identity

- case_id
- iteration
- status
- accepted

### Source lineage

- source_accepted_iteration
- source_layout

### Repair

- allowed_object_ids
- repair_action_count
- repair_engine_counts

### Quality

- pixel_fidelity_score
- pixel_fidelity_delta
- blocking_count
- blocking_delta
- native_editability_valid
- semantic_accuracy
- semantic_audit

### Drift

- unauthorized_object_drift_count
- drift_objects

### Rollback

- rollback
- rollback_reasons

### Asset lifecycle

- asset_retry_count
- asset_user_choice_required_count
- asset_resolved_count

### Human / artifacts

- human_approved
- artifacts

## 10. Distillation Selection

分类：

```text
positive
hard_negative
rejected
```

### Positive

必须显式满足：

- accepted = true；
- human_approved = true；
- native_editability_valid = true；
- semantic_accuracy = 1.0；
- no unauthorized drift；
- no rollback；
- no unresolved asset user choice；
- source lineage complete；
- visual policy satisfied。

### Hard Negative

用于保存明确失败但具有训练价值的样本，例如：

- semantic failure；
- native editability failure；
- drift regression；
- rollback。

### Rejected

证据不足的样本：

- missing semantic evidence；
- missing native evidence；
- missing source lineage；
- incomplete record。

原则：

```text
missing evidence ≠ success
```

## 11. Asset Retry Evidence

Native image generation 默认最多 3 次自动 attempt。

每次失败保存：

- score；
- structure score；
- style score；
- confidence；
- issue_codes；
- reasons；
- generation prompt lineage。

达到最大次数：

```text
status = user-choice-required
```

明确选择：

- continue-native-generation；
- crop-matting-fallback。

不能自动 fallback。

## 12. Golden Promotion Gate

Golden baseline 是比 positive distillation 更严格的状态。

默认要求：

### Visual

```text
pixel_fidelity_score >= 0.94
```

### Semantic

```text
semantic_accuracy == 1.0
semantic_audit.valid == true
semantic_audit.error_count == 0
semantic_audit.accuracy == 1.0
expected_object_count == audited_object_count
```

### Structure

```text
native_editability_valid == true
blocking_count == 0
unauthorized_object_drift_count == 0
```

### Process

```text
accepted == true
rollback == false
human_approved == true
source lineage complete
```

### Stability

默认需要：

```text
2 consecutive stable iterations
```

## 13. 为什么需要 Stable Streak

单次高分可能是偶然。

两轮稳定意味着：

- 下一轮从 accepted-state 继续时没有再次破坏；
- evidence chain 持续完整；
- repair 收敛而不是震荡。

任何不合格的中间轮次会重置 streak。

## 14. Golden Manifest

Golden manifest 是 immutable versioned record。

```json
{
  "version": "astra-golden-v3",
  "case_id": "case-1",
  "source_iteration": 4,
  "source_lineage": {},
  "artifacts": {},
  "semantic_evidence": {},
  "previous_golden": {},
  "rollback_to_version": "astra-golden-v2",
  "immutable": true
}
```

不允许用同一个 version 覆盖旧 Golden。

## 15. Golden 与完美第一版

“完美第一版”是人工认可的历史强基线。

Astra Golden 不应通过简单覆盖它来取代，而应该：

- 版本化晋升；
- 保留 previous golden；
- 可 rollback；
- 用 replay evidence 证明改进；
- 保持核心 deterministic authoring contract。

## 16. 12-case Regression 与 Distillation

12-case suite 提供横向覆盖。

Distillation 提供纵向 iteration 历史。

两者结合：

```text
12-case breadth
     +
iteration depth
     =
safer convergence
```

单一 case 的改善不能证明技能整体没有退化。

## 17. Performance Report

Distillation summary 可聚合进：

```text
performance-report.json
```

典型字段：

- record_count；
- accepted_count；
- rollback_count；
- object_drift_rollback_count；
- asset_retry_count；
- repair_action_count；
- native_editability_failure_count；
- semantic_perfect_count；
- semantic_evidence_complete_count；
- source_lineage_complete_count；
- mean_pixel_fidelity_score；
- mean_semantic_accuracy。

## 18. Human Approval 的位置

Human approval 不替代 deterministic QA。

正确关系：

```text
deterministic gates
   + model visual QA
   + human approval
   = release / golden eligibility
```

人工不能把 semantic error 手工改成通过。

## 19. 发布门禁与 Golden 门禁的区别

Release gate 面向一次交付：

- 当前 deck 是否可交付。

Golden gate 面向未来长期基线：

- 当前结果是否足够稳定，可作为后续回归和蒸馏的权威基准。

因此 Golden 更严格。

## 20. 推荐验收顺序

每个重要修复按以下顺序：

```text
1. unit / contract test
2. targeted case replay
3. object/native/semantic audit
4. visual comparison
5. drift guard
6. accepted / rollback decision
7. 12-case replay
8. distillation classification
9. human approval
10. golden promotion (if eligible)
```

## 21. 常见错误

### 错误：视觉提升就接受

正确：同时检查 semantic/native/drift。

### 错误：模型提出 patch 就允许对象变化

正确：只允许实际 `applied[]`。

### 错误：缺字段默认 true

正确：missing evidence fail-closed。

### 错误：失败三次后自动裁剪

正确：必须用户显式选择 fallback。

### 错误：新的 Golden 覆盖旧文件

正确：immutable version + rollback pointer。

## 22. 最终原则

本系统对质量的定义不是：

> “生成出来看着不错。”

而是：

> “视觉、原生语义、对象边界、来源、回滚和证据链同时成立，并且这种正确性能够在下一轮和其他 case 中继续保持。”
