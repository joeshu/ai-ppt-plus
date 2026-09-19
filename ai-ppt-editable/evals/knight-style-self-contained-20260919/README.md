# 降套管控：Knight-style 自包含流程实测

本案例用于验证 `ai-ppt-editable` 在**不运行 Knight、不做 A/B、无内置 0.90 数值门禁**条件下的独立执行能力。

## Reference

- Source: `WecomSave_a796a229d41950dfd301669d8858a906(2).jpeg`
- Canvas: 1536 × 864 (16:9)
- SHA-256: `036a0c6877bd9fd25541fcb38313a67d2bfef14c911f673f0e5c1a8d9be8ec99`

## Execution contract

本轮按最新 Knight-style 自包含合同执行：

1. input freeze
2. visual inventory
3. `native_editable` / `imagegen_asset` 分类
4. ImageGen 独立透明资产
5. true text slot + text-fit
6. editable PPTX authoring
7. physical z-order pass
8. fresh render QA
9. same-coordinate local-crop QA
10. object-level repair + re-render
11. final validation

不依赖外部 Knight runtime；视觉指标仅作为诊断与 repair prioritization。

## Object-level repair result

在 fresh render 后，优先修复右侧高价值责任对象：

- 将错误的大图标对象替换为独立透明的“日历 + 喇叭” ImageGen 资产；
- 将右侧 checklist 的蓝灰 checkbox glyph 替换为红色原生勾选框；
- 试验顶部手写口号 ImageGen 资产后，因视觉回退而拒绝该 patch，保留更稳 incumbent；
- 每次接受/拒绝均以 fresh render 结果判断，而不是追逐单一 SSIM 数值。

## r5 artifact hashes

- PPTX SHA-256: `ab54e51ff2b754a23a471fdb42631b259c7facf380c7e65a60263dddcce8eda9`
- Render SHA-256: `0fbd86d9abd29b236f2f29a26e4ec947ef32a190d1518d94c3114f1dd25b2cbc`
- Calendar/megaphone asset SHA-256: `adb1ea29a2e50a5a13d61d3806040ae150d862ede7377d125030bf7c104cc922`

Binary PPTX/render/reference are retained as run artifacts; this directory records the reproducible authoring/repair evidence and immutable hashes.
