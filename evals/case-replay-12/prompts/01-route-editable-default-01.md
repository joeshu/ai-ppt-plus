生成一张 16:9 横版图片型演示幻灯片，目标约 2048×1152 像素。画面要适合会议室观看，四周保留安全边距，关键文字不要贴边；必须使用真实 raster 图像生成后端。

【整体风格】
统一遵循本 deck 的设计系统：deep-sea navy glass, restrained metallic red and electric blue；字体为Noto Sans CJK SC / clean executive sans-serif；图标为consistent fine-line enterprise icons；配色固定为：primary #061A35；accent-red #E60012；electric-blue #1687FF；silver #F4F7FB。
网格：12-column 16:9 executive grid with stable title baseline and safe margins。跨页固定元素：same title baseline, color system, evidence discipline and independent semantic regions; closure remains page-local。材质语言：luxurious through precise hierarchy, glass depth, fine linework, controlled glow and no decorative noise。信息密度与层级要清晰，重点数字最大，标题次之，正文可读，模块严格对齐。

【本页角色与叙事】
页面类型：dashboard
本页标题：「政企客户增长作战舱」
核心逻辑：「围绕‘政企客户增长作战舱’建立一条可核对、可移动、可回放的页面关系。」
视觉框架：dashboard：以语义对象和证据链构成复杂信息框架。使用该框架组织阅读路径，但不要把“视觉框架”这个元标签额外渲染到画面上。

【A1 生成上下文】
受众：「国企经营管理层、业务负责人和专业评审」
语言：「简体中文，必要时保留短英文标签」
演示场景：「高端管理层会议室单页评审」
本 deck 共 12 页；本页必须与整套 deck 共用同一套配色、字体层级和图标语言。

【生图前叙事审批闸门】
审批思路表：outline/PPT思路表.csv；叙事修订：R1-case-replay-12；审批状态：approved；正式文字权威：approved-outline-table。只按已批准的页序、核心思想和页面大纲组织画面；不要替用户重排故事、扩写结论或新增事实。

【整套连续生成锁】
会话 ID：case-replay-12-imagegen-session-R1
连续性策略：single-model-single-context
建议批量：6 页；风格锚点：design-system:case-replay-luxury-dense-v1
共享前置语：同一套案例使用同一模型、同一上下文和同一设计锁；只改变页面叙事框架，不改变材质、字级和视觉语言。
同一套 deck 必须在同一个图像模型和同一连续上下文中生成；页面差异只能来自已批准的叙事框架，不得更换字体气质、材质、光影、图标语言、标题基线或页面收束规则。

【商用级视觉质量标准】
质量档位：premium-commercial；视觉语言：luxury high-density executive information design with complex but legible semantic structure
必须具备：one unambiguous focal point per page；complex but readable layout；presentation-scale typography；precise alignment and layered material depth；semantic regions suitable for later native reconstruction。
可读性下限：标题约 56px、正文约 28px、图示标注约 22px；每页可见文字项目原则上不超过 30 项。
禁止：generic four-card template、neon HUD、fake charts、unapproved English labels、watermarks。
商用安全：不使用未授权 Logo；不使用水印；不仿冒名人、商标或品牌；外部素材必须有来源/授权记录。
豪华感来自信息层级、负空间、材料质感、光影深度、精确对齐和少量高价值装饰，不来自堆叠装饰、无意义英文标签或把页面填满。

【语言与标签规则】
中文 deck：默认只使用 approved outline/正式文字中的中文、数字和已批准英文；禁止自动添加 Why/What/How、STEP、英文副标题、英文装饰标签或双语微文案。

【A4 有界恢复策略】
最多每页 2 次；范围：single-slide；触发条件：image-generation failure、missing or garbled approved copy、collapsed reading path or unusable layout。只重试问题页，不重跑已通过页面。

【版式结构】
沿着“页眉标题区 → 主体视觉框架 → 模块/图表说明 → 页面结论/行动收束”的阅读路径构图；顶部建立标题、导语和短强调线，中部用 dashboard：以语义对象和证据链构成复杂信息框架 承载模块，保留清晰的焦点、留白、连接线和语义化微件。每个模块至少具备标题、要点、重点数字或标签层级；不要退化成无信息的通用卡片模板。

【区域蓝图（必须按区域分配容量）】
主焦点：「政企客户增长作战舱的主关系与结果区域」
阅读路径：「标题与结论 → 主框架 → 证据面板/表格 → 结果或门禁」
区域与容量：
- header：标题、结论和页级识别（top；一个标题与一个短结论）
- primary-framework：承载页面主关系（center；主要节点、连接线、面板或图表）
- evidence-rail：承载可核对数据和辅助说明（right-or-bottom；两到三组证据）
- closure：结果、风险或下一步（page-local；一个短收束，不固定成横幅）
反模板护栏：
- 不得把页面做成无语义的等尺寸卡片墙
- 不得用第二套编号重复同一条关系
- 表格、面板和正文必须保留明确视觉边界
区域蓝图优先约束空间关系：主焦点必须比装饰更突出，阅读路径必须可见，区域必须容纳下方全部正式文字；不要把所有内容压缩成等宽等高的孤立卡片。

【页面收束策略】
将结论融入主框架或右侧结果舱；不强制使用全宽底栏。
结论文案是内容字段，不是固定组件；除非本页策略明确要求，否则不要生成与其它页面相同的全宽底栏、深色横幅或重复页脚。

【关系表达防重复】
同一主关系只保留一套主视觉编码：是。
避免把同一结论再做成第二套摘要/节点/编号：是。
允许的次级元素：只增加新的决策线索或证据，不重复主关系、结论或步骤。。
禁止模式：同一关系使用两套编号、重复结论栏、表格与图片重复承载同一数据。

【重点词着色语义（必须保留）】
执行规则：
- 只对批准文字中的关键词做行内强调，不新增或改写正式文字。
逐词颜色映射：
- 「重点项目进展TOP5」 → #E60012；范围：page conclusion or action close；处理：inline emphasis
页面结论或行动收束若列出重点词，必须在原有语句内保留重点词颜色，不得把整句统一成单色；不得把重点词改写成额外标签或数据。

【生成后视觉断言（必须回读）】
这些是生成后回读断言，不是新增页面文字；生成完成后必须逐页检查并记录结果。
回读范围：唯一渲染清单中的全部文字；缺失、改写、合并或重复均视为失败。
OCR 必须识别到：「政企客户增长作战舱」
OCR 不得识别到：「placeholder」、「Lorem」、「待补充」、「示意文字」
整页非背景墨迹比例至少为：0.01。

【视觉生成描述】
生成一张16:9单页高端国企经营管理PPT视觉稿，主题是‘政企客户增长作战舱’。深海蓝黑底色，联通红和电光蓝作为主强调色，豪华但克制，信息密度高，复杂网格排版，适合管理层会议室远距离阅读。顶部是大标题‘政企客户增长作战舱’，左上角红色Q3标签；上方三张独立KPI卡写‘目标 28.6亿元’、‘路径 18.7亿元’、‘结果 17.3亿元’，每张卡带微型柱状趋势。中部左侧是五步发光箭头流程：01目标洞察、02线索获取、03商机转化、04合同签约、05交付增值；右侧是多环完成率指标。底部左右各一张高密度原生表格，左表标题‘行业增长TOP5’，右表标题‘重点项目进展TOP5’，表头和进度条清晰。使用精细边框、玻璃面板、局部光晕、细线地图纹理和统一线性图标；所有文本清楚、准确、不要水印、不要手机框、不要整页照片。
以上段落只描述画面、材质、光照和视觉流向；它不是完整出图指令，必须与下面的正式文字合并执行。

【页面内容结构】
导语槽：1 条
模块 1：子标签、标题、重点数字、标签、要点 2 条
模块 2：子标签、标题、重点数字、标签、要点 2 条
模块 3：子标签、标题、重点数字、标签、要点 2 条
模块 4：子标签、标题、重点数字、标签、要点 2 条
页面收束槽：1 条，位置遵循本页 closure_treatment

【A2 内容厚度储备（仅用于容量规划）】
A2 已准备 3 段详细内容储备；它们只用于理解信息厚度与模块容量，不得原样渲染，也不得从中新增页面文字。
不要把内容储备段落原样排版；页面只能渲染下方白名单中的正式文字和获批图示标注。

【页面文字唯一渲染清单（逐字照排，每条最多出现一次）】
以下是唯一允许排版的可见文字，必须原样保留，包含中文标点、数字、大小写和专名；不得改写、删减、翻译、补充事实，也不得把同一条文字复制到第二个模块、摘要、编号或页脚：
- 「政企客户增长作战舱」
- 「目标」
- 「路径」
- 「结果」
- 「Q3」
- 「目标洞察」
- 「线索获取」
- 「商机转化」
- 「合同签约」
- 「交付增值」
- 「行业增长TOP5」
- 「重点项目进展TOP5」
- 「28.6」
- 「亿元」
- 「18.7」
- 「17.3」
- 「5」

【正式文字来源锚点（只用于审计，不是第二份排版清单）】
以下来源只用于核对唯一渲染清单的权威性；不要把它们另排一遍，也不要把结构字段和正式文字分别渲染：
- [title] id=case-01-text-01；来源：case-suite.json#cases[0].formal_text[0]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-02；来源：case-suite.json#cases[0].formal_text[1]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-03；来源：case-suite.json#cases[0].formal_text[2]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-04；来源：case-suite.json#cases[0].formal_text[3]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-05；来源：case-suite.json#cases[0].formal_text[4]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-06；来源：case-suite.json#cases[0].formal_text[5]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-07；来源：case-suite.json#cases[0].formal_text[6]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-08；来源：case-suite.json#cases[0].formal_text[7]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-09；来源：case-suite.json#cases[0].formal_text[8]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-10；来源：case-suite.json#cases[0].formal_text[9]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-11；来源：case-suite.json#cases[0].formal_text[10]；文本已纳入唯一渲染清单，只用于校对，不得再次排版
- [copy] id=case-01-text-12；来源：case-suite.json#cases[0].formal_text[11]；文本已纳入唯一渲染清单，只用于校对，不得再次排版

【批准的图示标注】
仅允许以下明确批准的图示标注作为关系层文字：
- 「目标」；用途：标记主关系中的一个批准节点；范围：primary framework；批准依据：user-directed case suite；来源：case-suite.json#cases[0].formal_text
这些词不是经营数据，也不是新增事实；只能放在声明的图示范围内，不得扩写成新的说明句。

【文字白名单（强约束）】
画面中只能出现【页面文字唯一渲染清单】和【批准的图示标注】中的文字；【正式文字来源锚点】不增加新的可见文字。每条批准文字最多出现一次，除非 copy_contract 明确允许重复；不得新增任何中文或英文标签、图表坐标、装饰性短句、虚构指标、伪数据或参考图文字。若需要表达关系，优先使用图标、连接线、箭头、节点和色彩；只有已批准的图示标注可以作为关系层文字。所有英文缩写也必须已经出现在上述正式文字或批准的图示标注中。

【图标与装饰】
图标语义：three_independent_kpi_cards、five_process_nodes、two_native_tables、native_text、native_route_metadata
背景纹理：深海蓝网格、细线和克制光晕
使用少量精致、语义明确、笔画统一的商务图标、连接线、箭头、进度或节点微件提升信息表达；优先用结构、材质、负空间和光影建立高级感，禁止随机图标拼贴或无意义英文标签；装饰不得抢夺核心文字焦点。

【字体与可读性】
重点数字 > 主标题 > 模块标题 > 子标签 > 正文要点。标题约为正文 2.5–3 倍，重点数字再放大；正文不要小到会议室不可读，单卡正文控制在 2–4 行，保持高对比与统一字重。
中文页面禁止通过缩小字号塞入更多内容；宁可合并、删减或拆页，也不要形成密集小字墙。

【参考图隔离规则】
无外部参考图；不得引入未经批准的文字、配色或品牌元素。

【生成硬约束】
不得编造任何数据、日期、机构、地名或专名；不得使用 SVG、HTML、Canvas、Pillow、ImageMagick 或其它代码绘图冒充 raster 出图；不得用代码补字或盖字，文字错漏只能修改本提示词后重新生成。不得加入页码、logo、水印或未批准的品牌元素。除非它本身就是批准文案，不得出现 placeholder、Lorem、待补充、示意文字、空白项目符号或用省略号代替正文。避免：placeholder text、invented numbers、watermark、random icon collage、full-slide screenshot skin。成品必须是包含全部上述真实文字的完整图片型幻灯片，不是占位模板、空卡片或无字背景。
