---
name: guanvis
description: 当用户要新建、修改、组装观远 BI / Guandata 的 Card（图表/报表卡片）、用指标平台指标创建的指标卡片、文本卡片、图片卡片、筛选器（selector，含日历/时间宏/区间/离散值）或仪表板（Page），或给出 Card ID、数据集 ID、指标 ID、card.js/page.js、图表类型关键词（柱状/折线/饼/KPI/表格/漏斗/地图/散点等 30+ 种）时，优先使用这个 skill。即使用户只说"做个销售仪表板""用这个指标做张卡片""加个 KPI 卡片""新建一个区域筛选器联动所有图""帮我改一下这个图的图例""把这几个 card 拼成一个 page""加一个本月/近 7 天的快捷日期筛选"，也要主动使用。它通过 AI 编写简洁的 JS 脚本（card_*.js / selector_*.js / page.js）定义卡片、筛选器和页面布局，再 pack/publish 上传到目标 BI。认证复用 guancli 共享配置。只想查现有 Card/Page 内容走 guancli。
compatibility: "Requires Node.js 14+. Install via npm link (local) or npm install -g @guandata/guanvis (from internal Nexus registry). CLI command: guanvis."
---

# guanvis

这是一个执行型 skill，用于通过 AI 生成的 JS 脚本创建 BI Card 和 Page 资源。

- AI 生成 `card_*.js` 定义各个 Card 图表；`page.js` 将多个 Card 组装成仪表板。
- `schema.js` 由 `init` 命令自动生成，定义数据集字段信息（不允许 AI 修改）；指标卡片使用 `metric-init` 生成 `metrics.js`。
- 框架内置验证规则，在 pack/publish 时检查字段数量、zone 兼容性、必填字段等。
- 认证通过 `guancli` 共享配置自动获取。

## Harness 化工作法

把可视化生成当作源文件驱动的构建流程：本地 JS DSL 是可编辑事实源，payload、ZIP、线上 Card/Page 都是从源文件生成的派生产物。

- `schema.js` 是由 `init` 生成的数据集事实快照，不手改；数据集字段变化时重新运行 `init`。`metrics.js` 是由 `metric-init` 生成的指标事实快照，不手改；指标口径、适用维度或格式变化时重新运行 `metric-init`。
- `card_*.js`、`selector_*.js`、`page.js` 是可编辑源文件；`*_package.zip`、preview JSON、publish 后线上资源都是派生产物。
- Card/Page 描述也是 JS 源文件的一部分：新建看板或改版时，在 `card_*.js` / `page.js` 中写 `.setDescription(...)`，再通过 `preview`/`pack`/`publish` 从 JS 源文件生成并发布资源。
- 写脚本前先形成 dashboard contract：目标用户、业务问题、使用的数据集、核心指标、维度拆解、筛选器、页面结构和验证方式。
- 每次生成都针对明确目录或明确子目录；不要把 unrelated 示例、旧包或临时 ZIP 混入同一个发布目标。
- Card/Page/Selector 的 `.setId(...)` 建议使用 `guanvis genid` 生成；如果生成或填写的 24 位 ID 以数字开头，重新生成一组，避免 BI 前端把 ID 拼成 CSS selector（如 `#5bef...`）时触发 `querySelector` 语法错误。
- 先 `preview/pack` 做本地结构验证，再 `publish/upload`；修改已发布资源前先判断变更类型：仅修复 Card/Page 描述时应保留原资源 ID，使用 `card/page set-description` 并同步维护 JS 中的 `.setDescription(...)`；调整图表、布局、筛选器、字段等看板内容时，按线上仪表板更新策略处理。
- **资源包安全红线**：Agent 只编辑 DSL 源文件；资源包 ZIP 是 `guanvis pack/publish` 的派生产物，不手工生成、解包修改或重打包。`guanvis upload` 只允许上传 `guanvis pack` 原样生成的 ZIP。若用户要求批量重绑资源、迁移已有页面或复用线上页面结构，先停下来说明风险并确认方案，不要直接改 ZIP。
- 发布后优先用 `guancli page get/card get` 回读结构与配置。只有在明确需要视觉质量判断、且当前大模型支持图像理解时，才使用 `guanvis screenshot <pageId>` 生成 PNG 并交给模型分析；不要把截图作为默认闭环步骤，因为图像理解会额外消耗 token/费用。

## AI Quick Reference（速查，详细说明见按需参考资料）

1. **工厂函数**：数据集图表用 `createCard()`；指标平台指标卡片用 `createMetricChart()`；筛选器/文本/图片/杜邦/Tab/页面用 `createSelector()` / `createTextCard()` / `createImageCard()` / `createDuPontChart()` / `createAreaTitle()` / `createCardGroup()` / `createTab()` / `createPage()`，不要 `new XxxBuilder()`
2. **注册函数**：`registerCard(card.build())` / `registerMetricChart(card.build())` / `registerSelector(sel.build())` / `registerTextCard(text.build())` / `registerImageCard(image.build())` / `registerDuPontChart(dupont.build())` / `registerPage(page.build())`
3. **字段引用**：单数据集用 `f("字段名")`，多数据集用 `field(DS, "字段名")`
4. **zone maxCount**：`BASIC_COLUMN/BAR/LINE` metric=1；`GROUPED_*/STACKED_*` metric=∞；`KPI_CARD` metric=1；组合图 `*_WITH_LINE` row=1
5. **column vs colorBy**：column 放维度（按类别分组着色），colorBy 放度量（按值渐变着色）
6. **原生聚合优先**：`SUM`/`AVG`/`COUNT`/`COUNT_DISTINCT`/`MIN`/`MAX` 等单字段聚合用 `f("字段", { aggrType: AggrType.XXX })`，不要用 `calcField()` 手写 SQL 聚合函数；去重计数用 `AggrType.COUNT_DISTINCT`，不要写 `COUNT_DISTINCT([字段])`
7. **calcField 命名**：不能与数据集物理字段同名，否则 BI 默认取数据集字段
8. **calcField 类型**：`aggregation`（默认）公式必须含聚合函数；纯算术用 `{ calculationType: "normal" }`；窗口函数用 `{ calculationType: "window" }`
9. **明细/滚动表 calcField**：`DETAIL_TABLE` / `SCROLL_TABLE` 只做逐行展示；如需行级计算，必须写 `{ calculationType: "normal" }`，且不要写任何 SQL 聚合函数或窗口函数。汇总需求改用非明细图表 `aggrType` / aggregation calcField，或 ETL 预计算
10. **联动/下钻**：筛选器联动图表必须调用 `.linkToAll()` 或 `.linkTo(cardIndex)`；筛选器级联筛选器用 `.linkToSelector(selectorId, targetFieldName?)`，目标为 ALL/空默认值时会自动启用 FIRST_PICK + firstPickLink，固定默认值会保留；普通图表卡片联动普通图表用 `card.linkTo(layoutCardIndex, { fields: [{ source, target }] })`；固定路径下钻用 `registerDrillPath(parentCardIndex, [child.build()], { position: DrillPathPosition.BOTTOM })`；详细规则见 `references/builder-reference.md`
11. **selector 类型选择**：离散值（区域/类别）→ `DS_ELEMENTS`（默认）；连续数值（利润率/金额）→ `.setSelectorType(SelectorType.DS_INTERVAL)`；日期 → `CALENDAR`；快捷日期区间（本月/近7天等）→ `.setTimeMacroOptions(options)`
12. **同环比默认**：用户说同比/环比/同环比/年同比/月环比且未指定输出值时，默认用增长率；未指定模式时默认按日期筛选模式（`ComparativeMode.FILTER_BASED`），普通模式需显式指定 `ComparativeMode.NORMAL`。如果日期字段已经是预聚合周期字段（如 `周开始日期` / `月开始日期`），必须把日期字段声明为 `f("周开始日期", { granularity: Granularity.NONE })`，builder 会生成不带筛选窗口和 `mode` 的同环比，避免按 DAY 筛选窗口计算为空
13. **placeCard 入参**：数字 index 按 `registerCard` / `registerMetricChart` / `registerTextCard` / `registerImageCard` / `registerCustomChart` / `registerDuPontChart` 等可布局资源的注册顺序累加，文件按文件名排序加载。**registerSelector 不参与 card index 计数**；要把 selector 放进画布或者布局组件时，使用 selector 字符串 ID，如 `placeCard("selectorId", x, y, w, h)` 或 `addFullWidthCard("selectorId", h)`。
14. **publish 环境**：认证由底层 CLI 负责——guancli 需先 `guancli auth use <profile>`，guancli-lite 需设置环境变量
15. **更新线上仪表板**：已发布过或线上正在使用的仪表板，若调整图表、布局、筛选器、字段等看板内容，默认创建新版本仪表板，不覆盖原仪表板；新版本使用新的 Page/Card/Selector ID，名称追加版本号（如 `销售仪表板 v2` / `销售仪表板 20260430`），保留多个版本。只有用户明确要求覆盖时，才复用原 ID；遇到覆盖提示时，Agent 必须先向用户说明将覆盖哪些线上资源并取得明确确认，确认前不得自行加 `--allow-overwrite`
16. **描述维护**：仅修复已发布 Card/Page 的描述时，保留原资源 ID，使用 `guanvis card/page set-description` 更新线上描述；如果本地有对应 JS 工程，也同步更新 `.setDescription(...)`，让源文件与线上描述一致
17. **主题切换**：用户描述风格（深色科技风/科技蓝/蓝色简约等）→ 在工程目录里 `guanvis theme preference --keywords "..." --sync`（`[dir]` 可省，默认当前目录）；不要选择租户默认的“浅色”/“深色”主题，找不到合适主题时保持/清空偏好，让 preview/pack/publish 自动使用内置“简约”兜底。普通数据集图表与指标平台 MetricChart 都会自动应用主题视觉配置；改版未提风格时 `.applied.json` 会自动继承上次主题，preview/pack/publish 不需要重复指定。**多子目录工程**：每个子目录是独立工程，主题要在子目录里配置 + preview/pack/publish 也必须 `cd` 进对应子目录运行（在根目录直接跑会被命令显式拒绝并给出 cd 提示）；详见 `references/theme.md`
18. **设计规则**：`preview`/`pack`/`publish` 会自动应用内置设计规则；需要自定义静态卡片默认规则或主题已开放配置时，在工程目录新建 `design-rule.json`，不要手改 `themes/<themeId>.json`；详见 `references/theme.md`
19. **图表选型**：用户说“指标卡片”时先区分语义：如果是数据集字段做单值/KPI，用 `SINGLE_VALUE` / `KPI_CARD`；如果是“用指标平台已有指标创建卡片”，必须先 `guanvis metric-init <metricId>`，再用 `createMetricChart()` + `metric()` / `metricDim()`，生成后端 `CARD_TYPE.METRIC_CHART`。复杂指标卡片参数先读 `references/metric-chart-reference.md`
20. **杜邦分析图**：杜邦不是普通 `ChartType`，用 `createDuPontChart()` 创建 `LAYOUT` 卡片；节点通常放 `KPI_CARD` 子卡片，并通过 `.setRoot()` / `.addChild()` 组织树。页面布局只放杜邦父卡片，不单独放子卡片；筛选器 `linkToAll()` 会覆盖杜邦子卡片。
21. **布局组件**：支持 `小标题(AreaTitle)` / `卡片组(CardGroup)` / `标签页(Tab)`。布局组件本身只支持放在画布根布局，不支持嵌套组合使用；内部布局能力详见 `references/builder-reference.md`。
22. **资源包禁止手改**：只改 DSL，不改 ZIP 内部文件；`upload` 只用于上传 `guanvis pack` 原样生成的包。批量重绑、迁移页面等需求先讨论方案。

## 何时使用

遇到这些任务就用：

- 新建观远 BI Card（柱形图、折线图、饼图、表格、KPI、散点图、漏斗、地图等 30+ 种）。
- 基于指标平台已有指标创建指标卡片（MetricChart，后端 `cdType=13`），支持指标自身格式和适用维度。
- 创建文本卡片（含内嵌指标引用）或图片卡片（外链/本地图片）。
- 创建筛选器并配置联动关系（选择筛选器、日历筛选器等）。
- 组装多个 Card 和筛选器为一个仪表板/Page，含 grid layout 布局和筛选器面板。
- 批量生成一组 Card 并上传到 BI 系统。
- 用户提到 `card.js`、`page.js`、CardPayload、图表类型、chart axes、zone spec、筛选器联动。

## 固定工作方式

### 1. 确认前置条件

```bash
guancli auth status
```

- 如果用户指定的资源（数据集、仪表板等）搜索不到，先用 `guancli auth list` 列出所有可用环境，提示用户确认是否需要切换 profile，而不要在当前 profile 上反复重试。

### 2. 生成 schema.js（只做一次或数据集变更时重新生成）

```bash
# 查找数据集
guancli ds search <关键词>

# 生成 schema.js（传入数据集 ID）
guanvis init <dsId1> <dsId2> -d ./my_dashboard/
```

如果用户给的是业务目录名而不是数据集名，先用 `guancli ds tree` 定位目录，再在目录内按真实数据集名搜索，不要把目录名直接当作数据集名反复 `ds search`。

生成的 `schema.js` 示例：
```javascript
// Auto-generated — DO NOT EDIT
defineDataset("s9ded2338f43807b095fbb4f", [
    { fdId: "jb16f22f6c1c21c3f6e8e293", name: "区域", fdType: "STRING", metaType: "DIM" },
    { fdId: "lb1c31b4dc86511a27049a98", name: "营收", fdType: "DOUBLE", metaType: "METRIC" },
    // ...
], { displayType: "EXCEL" });
```

### 2b. 生成 metrics.js（创建指标平台指标卡片时）

当用户说“用指标创建卡片”“指标卡片”且给出的是指标平台 metric ID/指标名时，走这条链路，而不是把指标当作数据集字段：

```bash
# 先用 guancli 查指标 ID（如果用户只给名称）
guancli metric search '<关键词>'

# 生成指标事实快照
guanvis metric-init <metricId1> <metricId2> -d ./my_dashboard/
```

生成后在 `card_*.js` 中使用：

```javascript
var card = createMetricChart(ChartType.PIVOT_TABLE, "销售指标分析")
    .setId("cardId24chars")
    .addRow(metricDim("销售额", "区域"))
    .addMetric(metric("销售额"));

registerMetricChart(card.build());
```

`metrics.js` 必须在 `card_*.js` 前加载；目录模式会自动按 `schema.js` → `metrics.js` → `card_*.js` → `selector_*.js` → `page.js` 的顺序执行。

### 3. 设置仪表板主题（按需）

如果用户**明确提到了视觉风格**（"深色科技风"、"蓝色简约"、"科技蓝T004" 或具体 themeId 等），在编写 card/page 之前把意图落到 `.preference.json`。不要把租户默认的“浅色”/“深色”当作可选主题；如果候选里没有合适风格，跳过这一步或执行 `theme preference --clear`，让命令自动使用内置“简约”：

```bash
cd ./my_dashboard

# (a) 用户描述了风格关键词 —— 拉一次主题列表，AI 也能离线核对候选
guanvis theme preference --keywords "深色 科技" --sync

# (b) 用户给出明确 themeId
guanvis theme preference --theme-id custom_blue --sync

# (c) 想先看看候选名字
guanvis theme sync   # 拉列表
guanvis theme list   # 看候选 themeId / themeName / themeType
```

> **多子目录工程**：每个子目录都是独立工程，主题各自隔离。如果不同子目录需要不同主题，**`cd` 进每个子目录分别跑一遍 `theme preference`**（每个子目录会有自己的 `themes/.preference.json` + 主题快照）；只要任一子目录配了自己的 `themes/`，preview/pack/publish 就必须在对应子目录里运行（详见 `references/theme.md`）。如果整个工程主题统一，把 `themes/` 配在根目录、所有子目录共享即可。

命令产出的目录形态（与 `schema.js` 同级）：

```
my_dashboard/
├── schema.js
├── themes/
│   ├── .preference.json        # theme preference 写入的偏好（themeId / keywords）
│   ├── .index.json             # theme sync 拉到的候选主题索引
│   ├── .sync-meta.json         # syncedAt / count
│   ├── default_7.json          # theme sync 落盘的主题快照（每个 themeId 一份）
│   └── custom_blue.json
└── ... (card_*.js / page.js 后面再加)
```

`.applied.json` 会在第一次 `pack`/`publish` 实际使用了线上主题时自动写入；这之前不存在很正常。回退到 skill 自带 `simple.json` 时**故意不写** `.applied.json`，避免污染下次解析。

何时跳过这一步：

- **改版已有看板**（工程下已存在 `themes/.applied.json`）→ 跳过，`pack`/`publish` 会自动继承上次主题。
- **新看板但用户没描述风格** → 跳过，自动落到 skill 自带的 `simple.json`（与原行为一致；离线/弱网都不会失败）。
- **候选主题只剩默认“浅色”/“深色”或都不贴合需求** → 不要为了命中而随便选，清空/不写偏好并使用内置“简约”兜底。
- 后续用户改主意要换风格 → 再跑一次 `theme preference` 就行，不需要重做 schema 或 card。

完整决策规则、`themes/` 目录结构、离线 vs 联网约定见 `references/theme.md`。

### 4. 编写 card 脚本

card 脚本使用 `field()` 或简写 `f()` 从 schema 引用字段（无需记忆 fdId）：

```javascript
// card_01_revenue.js — 使用 field(DS, ...) 完整写法
var card = createCard(ChartType.GROUPED_COLUMN, "营收分析")
    .bindDataset(DS)
    .setDescription("业务故事：用于回答各区域营收规模与产品结构差异，目标用户是经营管理层。指标口径：营收按 SUM 聚合。")
    .addRow(field(DS, "区域"))
    .addMetric(field(DS, "营收", {
        aggrType: AggrType.SUM,
        numberFormat: NumberFormat.currency("¥", 0)
    }))
    .addColumn(field(DS, "产品"))
    .setShowLegend(true, "right")
    .setDataLabel({ show: true, showNumber: true });

registerCard(card.build());
```

```javascript
// card_02_pivot.js — 使用 f() 简写（单数据集场景）
var card = createCard(ChartType.PIVOT_TABLE, "区域产品交叉分析")
    .bindDataset(DS)
    .addRow(f("区域"))
    .addColumn(f("产品"))
    .addMetric(f("营收", { aggrType: AggrType.SUM }))
    .addSort(f("营收", { aggrType: AggrType.SUM, sortType: SortOrder.DESC }))
    .setTableSetting({ showRowTotal: true, showColumnTotal: true });

registerCard(card.build());
```

### 5. 编写 page.js（可选）

```javascript
var page = createPage("销售仪表板")
    .setId("wb52d11444d6f1b4063d8cf8")
    .setDescription("综合销售分析")
    .setBackgroundColor("#f5f5f5")
    .setCardMargin(8)
    .addRow([{ card: 0, w: 4 }, { card: 1, w: 8 }], 4)
    .addFullWidthCard(2, 6)
    .addHalfWidthCards(3, 4, 6);

registerPage(page.build());
```

**仪表板主题**：项目目录下没配 `themes/` 时，`preview`/`pack`/`publish` 自动使用 skill 自带的简约主题（embed 在二进制里的 `simple.json`，不依赖租户线上主题列表）。如需切换租户自定义主题或带明确风格的默认主题，请参考 `references/theme.md`，通过 `guanvis theme preference` 写入 `themes/.preference.json`；租户默认“浅色”/“深色”没有特殊样式，不作为可选主题。**JS DSL 不再提供主题相关接口**——任何 `setDashboardTheme(...)` 或 `page.setTheme(...)` 调用都会因函数未定义而报错。

指标平台 MetricChart 也会在 `preview`/`pack`/`publish` 阶段自动应用主题视觉配置：透视表会补表格/合计样式，柱线饼等会补坐标轴、图例、数据标签和主题色。主题只写 `settings` 与 `meta.chartMain.props`，不改 `zoneData`、`dsInfo`、`defaultView` 等影响指标查询的字段。

**多页面支持**：可以在同一个项目中注册多个 page（多次调用 `registerPage`）。两种组织方式：

1. **单目录**：所有 card 和 page 在同一目录，page 通过 card index（注册顺序）引用
2. **子目录**：每个子目录有独立的 `schema.js`、`card_*.js`、`page.js`。page 通过 card ID 字符串引用（推荐）

子目录结构示例：
```
project/
├── overview/
│   ├── schema.js
│   ├── themes/             ← 主题偏好与缓存（按需，仅当跑过 theme preference / sync）
│   │   ├── .preference.json
│   │   ├── .applied.json
│   │   ├── .index.json
│   │   ├── .sync-meta.json
│   │   └── <themeId>.json
│   ├── card_01_kpi.js
│   ├── card_02_chart.js
│   ├── page.js             ← addFullWidthCard("card_id_string", 6)
│   └── charts/             ← 自定义图表内容
├── detail/
│   ├── schema.js
│   ├── themes/             ← 每个子目录是独立工程，主题各自维护
│   │   └── ...
│   ├── card_01_table.js
│   └── page.js
```

> 子目录模式下每个子目录是独立的看板工程，`themes/` 与 `schema.js` 同级、各自隔离；preview/pack/publish/`theme *` 命令必须 `cd` 进对应子目录单独执行。**在父级根目录直接 `guanvis pack/preview/publish .` 时，若任一子目录里出现了 `themes/`，命令会直接报错并提示需要进入子目录单独执行**——这避免了根目录运行时各子目录主题被静默忽略、全部退回内置 `simple.json` 的隐蔽问题。如果整个工程不需要主题（所有子目录都没有 `themes/`），在根目录一次性 `pack` 也照常工作，行为不变。

子目录模式下，page 布局必须使用 card ID 字符串而非 index：
```javascript
var p = createPage("Detail Page")
    .setId("pgId24chars")
    .addFullWidthCard("cardId24chars", 8);  // 用 card ID 而非 index
registerPage(p.build());
```

### 6. 执行命令

```bash
# 生成资源 ID（用于 .setId() 调用）
guanvis genid       # 生成 1 个
guanvis genid 5     # 生成 5 个
# 如果生成或填写的 ID 以数字开头，重新生成一组，避免 BI 前端 querySelector("#<id>") 报非法 selector

# 生成布局组件 ID
guanvis gen-layout-id tab                 # 生成 1 个 tab_ + 默认 6 位字母
guanvis gen-layout-id panel 3 --length 8  # 生成 3 个 panel_ + 8 位字母；length 只计算下划线后的随机字母，超出 6~10 时自动收敛
guanvis gen-layout-id areaTitle           # 生成 1 个 areaTitle_ + 默认 6 位字母
guanvis gen-layout-id cardGroup           # 生成 1 个 cardGroup_ + 默认 6 位字母

# 预览生成结果（JSON 输出到 stdout，含 payload 验证，用于调试）
guanvis preview ./my_dashboard/

# 打包为 ZIP 资源包
guanvis pack ./my_dashboard/
guanvis pack -o output.zip ./my_dashboard/

# 一步到位：构建并上传到 BI（在线同步）
guanvis publish ./my_dashboard/
guanvis publish ./my_dashboard/ --page-parent-dir <dir_id>  # 指定页面目录

# 上传已有 ZIP 资源包；只允许上传 guanvis pack 原样生成的 ZIP
guanvis upload output.zip

# 修复已发布资源描述（保留原 Card/Page ID）
# 如果本地维护对应 JS 工程，也同步更新 card_*.js / page.js 里的 .setDescription(...)。
guanvis card set-description <cd_id> --description "这张卡用于回答..."
guanvis card set-description <cd_id> --file ./card_story.md
guanvis page set-description <pg_id> --description "这张页面用于回答..."
guanvis page set-description <pg_id> --file ./page_story.md --visible=false

# 页面视觉验证（可选，PNG，通过 BI 后端服务端截图，不依赖浏览器）
# 仅在明确需要视觉质量判断且当前大模型支持图像理解时使用；图像分析会额外消耗 token/费用。
guanvis screenshot <pageId>                                     # 截图页面 PNG 到 <pageId>.png
guanvis screenshot <pageId> -o /tmp/dashboard.png               # 指定输出路径
guanvis screenshot <pageId> --orientation horizontal            # 横向截图

# 仪表板主题（详见 `references/theme.md`，[dir] 缺省为当前目录）
guanvis theme preference --keywords "深色 科技" --sync          # 在当前目录写入偏好并同步主题列表
guanvis theme preference ./my_dashboard --theme-id custom_blue  # 显式指定工程目录
guanvis theme preference --clear                                # 清空当前目录的偏好与 applied 快照（彻底回到内置 simple.json）
guanvis theme list                                              # 列出已落盘的候选主题
guanvis theme show                                              # 打印当前主题决策（不联网）
guanvis theme sync                                              # 强制刷新主题列表
```

**多子目录工程的执行方式**：每个子目录是独立工程，preview/pack/publish 必须在每个子目录里分别执行，每次产出独立的 ZIP 资源包；想要每个子目录用不同主题，就在每个子目录里分别 `theme preference`。在根目录直接运行 preview/pack/publish 时，若任一子目录里有 `themes/`，命令会拒绝执行并打印 `cd <subdir> && guanvis <preview|pack|publish> .` 提示。

```bash
# 多子目录工程 + 各子目录主题不同 → 在每个子目录分别执行
for sub in overview detail kpi; do
  cd "./project/$sub"
  guanvis theme preference --keywords "..." --sync
  guanvis publish .
  cd -
done

# 多子目录工程 + 整个工程不需要主题（无任一子目录配 themes/）→ 根目录一次性 pack 仍然可用（与原行为一致）
guanvis pack ./project
```

`publish` 和 `upload` 使用 BI 的 **transfer API**（`/api/manual/template/transfer`），特点：
- `needIdMapping=false`：保持资源 ID 不变，重复导入会覆盖同 ID 资源
- 发布前在线覆盖检查只探测 Page ID，不探测 Card/Selector ID；如果资源包不包含 Page，则不会执行在线覆盖检查，避免部分 BI 版本在导入前缓存"找不到相关卡片"
- 认证方式：随底层 `guancli fetch` 使用 `Cookie: uIdToken=...`
- 需要 `raw-backend-response: TRUE` header 绕过前端代理层
- 不需要目标系统开启"一键迁移"开关，所有环境通用

**资源包安全约束**：`upload` 只是上传器，不是制作自定义资源包的入口。除非用户明确批准，否则不得上传手工生成、解包修改、重打包或批量替换内部内容后的 ZIP。需要批量重绑数据集、字段、卡片或页面 ID 时，先讨论方案，不要直接改 ZIP。

**线上仪表板更新策略**：为了保护已经发布过的仪表板和线上仪表板，默认不要复用原 Page/Card/Selector ID 做覆盖更新。需要调整线上看板时，应先生成一组新的 ID，复制并修改 DSL/JS，给 Page 名称追加版本号（例如 `v2`、`v20260430` 或业务约定版本），再 `publish` 到目标目录。旧版本保留用于回滚和对比。仅当用户明确要求“覆盖原仪表板/复用原 ID”时，才允许同 ID 发布，并且命令必须显式加 `--allow-overwrite` 允许同 ID Page 覆盖；发布前可用 `--dry-run` 查看会覆盖哪些线上 Page。Card/Selector ID 不做在线覆盖检查。**Agent 禁止在未确认的情况下自行加 `--allow-overwrite`**：当 CLI 提示将覆盖线上 Page 时，必须先停止发布，向用户说明将覆盖的 Page ID、名称和覆盖后可能替换原页面布局，等用户明确确认“覆盖”后才可以重跑并加 `--allow-overwrite`。使用 `--allow-overwrite` 时，CLI 会先为冲突 Page 发起资源包导出备份并等待导出成功；备份未成功则中止覆盖。CLI 只记录备份导出记录和 packageId，不自动下载资源包；需要回滚时，到 BI 资源迁移导出记录中手动下载该资源包后再导入覆盖回去。

## 文件结构约定

目录模式下文件加载顺序：
1. `schema.js` — 数据集定义（自动生成，不可修改）
2. `metrics.js` — 指标定义（仅指标卡片需要，自动生成，不可修改）
3. `card_01_xxx.js` ~ `card_NN_xxx.js` — Card 定义（按文件名排序）
4. `selector_01_xxx.js` ~ `selector_NN_xxx.js` — 筛选器定义（在 card 之后执行，因为联动需要引用 card 索引）
5. `page.js` — Page/仪表板组装

自定义图表时，图表内容文件（如 ECharts 脚本）放在 **子目录**（如 `charts/`），避免被当作 card 脚本执行。

`themes/` 子目录由 `theme *` 子命令维护，与 `schema.js` 同级；preview/pack/publish 会自动读取并应用。点前缀文件（`.preference.json` / `.applied.json` / `.index.json` / `.sync-meta.json`）是元数据/缓存，`<themeId>.json` 是主题快照——所有文件**不要手改**，详见 `references/theme.md`。

## 参考示例

| 示例 | 路径 | 说明 |
|------|------|------|
| 基础仪表板 | `evals/sales_dashboard/` | 普通卡片（柱状图、折线图、KPI、饼图）+ 筛选器 + 页面布局 |
| 自定义图表 | `evals/custom_chart_echarts/` | ECharts Lite 自定义图表：柱状图 + 饼图，使用 `loadContent()` 文件模式 |
| Tab 布局 | `evals/tab_layout/` | 单页面 tab 示例，含根布局指标卡、图表卡片、文本卡片、筛选器和 panel 内卡片布局 |

生成脚本前先查阅对应示例中的文件结构和写法。

## 按需参考资料

| 场景 | 路径 | 读取时机 |
|------|------|----------|
| 字段、计算字段、NumberFormat、高级计算和卡片筛选器 API | `references/api-reference.md` | 编写字段、指标、公式或筛选条件时 |
| Card/Page/Tab/Selector/Text/Image/CustomChart Builder API 与枚举 | `references/builder-reference.md` | 编写或修改 JS DSL builder 调用时 |
| zone 校验、图表选型、地图/拆分图、字段对象细节 | `references/validation-and-chart-patterns.md` | pack 报错、选型不确定或需要特殊图表行为时 |
| 仪表板主题机制与 theme 命令排错 | `references/theme.md` | 用户指定视觉风格、改版继承主题或主题异常时 |
| 在线同步、认证、ID 管理和硬约束 | `references/publish-and-constraints.md` | publish/upload、更新线上资源或确认生成边界时 |
| Tableau 迁移清单 | `references/tableau-migration.md` | 从 Tableau 工作簿迁移到观远 BI 时 |
| 常见错误与修复 | `references/troubleshooting.md` | 命令失败或校验报错时 |

## 最后怎么向用户汇报

至少说明：

- 创建了多少个 Card、什么图表类型。
- 是否有筛选器，联动了哪些卡片。
- 是否有 Page，布局方式如何。
- 是否有验证错误及修复建议。
- `pack`/`publish`/`upload` 哪些步骤已成功。
