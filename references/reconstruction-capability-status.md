# Reconstruction capability status

本项目严格区分三类证据，禁止混用“通过”一词：

1. **engineering gate passed**：结构、原生编辑性、语义对象、自动视觉指标、回归测试通过。它不能证明 PowerPoint/WPS 中的最终视觉效果已经人工确认。
2. **visual evidence confirmed**：原图、PPTX 渲染、视觉差异图和实际对象树四证据齐全，并经过人工逐页视觉确认。
3. **host validation passed**：同一 PPTX Hash 在实际 PowerPoint/WPS 主机中完成打开、字体、排版、溢出、编辑性和逐页截图验证。

只有三类证据同时通过时，`release_eligible=true`，才允许使用“validated editable high-fidelity reconstruction delivery”能力口径。

自动化状态由 `scripts/build_reconstruction_capability_status.py` 生成。LibreOffice/PDF 渲染属于 engineering evidence，不可替代 PowerPoint/WPS host validation。
