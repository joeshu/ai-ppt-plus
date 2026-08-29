# OOXML 字体嵌入适配器

## 适用范围

`python-pptx` 能把字体族名写进文字运行，但不能自行创建
PresentationML 的字体部件。中文交付因此不能把“任务字体目录可用”误报成
“字体已经随 PPTX 携带”。本项目使用 `scripts/embed_fonts.py` 作为确定性的
后处理适配器：先由 `compose_pptx.py` 生成 staging PPTX，再复制为最终文件并
写入 OOXML 字体关系和字体部件。

最终包至少应包含以下闭环：

1. `ppt/presentation.xml` 中的 `p:embeddedFontLst`、`embedTrueTypeFonts` 和
   `saveSubsetFonts` 声明；
2. `ppt/_rels/presentation.xml.rels` 中的字体关系；
3. `ppt/fonts/*.fntdata` 字体部件，内容类型为 `application/x-fontdata`；
4. `scripts/inspect_pptx.py` 对关系、部件和 EOT 封装进行复验；
5. 对最终文件重新渲染，而不是只渲染 staging 文件。

## 安全与可移植性约束

- 只接受单字体的 TTF/OTF SFNT 文件；TTC 必须先拆成获得许可的单字体文件。
- 读取 OS/2 `fsType`，命中 restricted-license 位时拒绝嵌入。
- 适配器默认嵌入完整字体，不做不可逆的子集化，以降低后续中文文本编辑时缺字
  的风险；文件体积和目标应用支持仍需人工确认。
- 字体清单必须声明文件、SHA-256、字体族和许可证来源；适配器不替用户推断
  许可证。
- EOT/OOXML 结构通过，不等于每个字形都覆盖，也不等于所有目标应用都一定
  采用该字体；最终人工审阅仍是独立步骤。

## 调用方式

```bash
python3 scripts/compose_pptx.py layout.json final.pptx \
  --font-dir project-fonts --embed-fonts \
  --embedding-report font-embedding.json
```

已有 staging 文件可直接后处理：

```bash
python3 scripts/embed_fonts.py staging.pptx final.pptx \
  --font-dir project-fonts --report font-embedding.json
python3 scripts/inspect_pptx.py final.pptx --report inspection.json
```

规范背景：[Microsoft Open XML `EmbeddedFont` reference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.embeddedfont?view=openxml-3.0.1)。