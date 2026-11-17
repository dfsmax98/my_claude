## Builder API 参考

### CardBuilder

| 方法 | 说明 |
|------|------|
| `createCard(chartType, name)` | 创建 Card（chartType 必须使用 `ChartType.XXX` 枚举） |
| `.setId(cardId)` | **必填**。设置资源 ID（严格 24 位字母数字，格式与后端 RandUtil.uuid 一致），支持多次上传覆盖更新。通过 `guanvis genid` 生成；如果生成或填写的 ID 以数字开头，建议重新生成一组，避免 BI 前端 `querySelector("#<id>")` 报错 |
| `.bindDataset(dsId)` | 绑定数据集（必填，dsId 必须在 defineDataset 中注册） |
| `.addRow(field)` | 添加行维度（X 轴） |
| `.addColumn(field)` | 添加列维度（按维度分组着色，如按地区/类别分色）。仅 `STACKED_COLUMN`、`GROUPED_COLUMN`、`GROUPED_BAR` 等多指标图表支持 |
| `.addMetric(field)` | 添加度量（Y 轴，主轴） |
| `.addMetricAdditional(field)` | 添加副轴度量（仅组合图 `*_WITH_LINE`/`*_WITH_SYMBOL`），默认绑定副 Y 轴（`plotOn: secondary`） |
| `.addColorBy(field)` | 按指标值渐变着色（接受度量字段，不是维度）|
| `.addTooltip(field)` / `.addFilter(field)` | 提示/筛选 |
| `.addSort(field)` / `.addSplit(field)` / `.addSize(field)` | 排序/拆分/大小 |
| `.addLocation(field)` / `.addTarget(field)` / `.addCompare(field)` | 位置/目标/对比 |
| `.setSplitSetting({ rows, columns })` | 拆分行列数（默认各 3），需配合 `.addSplit(field)` |
| `.setColorByColors(preset_or_config)` | colorBy 渐变色。传 `ColorByPreset.RedGreen` 等预设名称，或 `{ startColor, endColor, middleColor?, steps? }` 自定义 hex 颜色 |
| `.setShowLegend(show, position)` | 图例 |
| `.setDataLabel(config)` | 数据标签 |
| `.setAxis(config)` | 轴配置（见下方 Axis Config 详解） |
| `.setTableSetting(config)` / `.setPieSetting(config)` | 特殊图表设置 |
| `.setThemeColor(tcId, colors)` | 主题颜色 |
| `.setLimit(count)` | 数据行数限制 |
| `.setConditionalFormat(config)` / `.setAuxiliaryLine(config)` | 条件格式/辅助线 |
| `.linkTo(target, config)` | 图表卡片点击联动；`target` 可传布局 index 或 cardId，详细规则见本节 Card Linkage |
| `registerDrillPath(parentCardIndex, drillCards, config?)` | 全局函数，声明固定路径下钻，详细规则见本节 Card Drill |
| `.setRawSettings(key, value)` | 原始设置 |
| `.build()` | 构建（触发验证） |

### MetricChartBuilder（指标平台指标卡片）

用于“用指标平台已有指标创建卡片”，生成后端 `CARD_TYPE.METRIC_CHART`（`cdType=13`）。不要用普通 `createCard()` 伪造，也不要把指标 ID 当作数据集字段。

前置：先运行 `guanvis metric-init <metricId...> -d <dir>` 生成 `metrics.js`。目录模式会在 `card_*.js` 前自动加载。

| 函数/方法 | 说明 |
|------|------|
| `defineMetric(metricDef)` | 定义指标事实快照，由 `metric-init` 生成；不要手写/手改 |
| `metric(metricIdOrName, overrides?)` | 引用指标，传指标 ID 或指标名；用于 `.addMetric(...)` |
| `metricDim(metricIdOrName, dimName, overrides?)` | 引用某个指标的适用维度；维度名、`fdId` 或 `publicDimensionId` 均可匹配 |
| `metricDim(dimName, overrides?)` | 在所有已定义指标的适用维度中查找；多指标同名维度时优先用上面的双参数写法 |
| `createMetricChart(chartType, name)` | 创建指标卡片，`chartType` 使用 `ChartType.XXX`，默认可用 `PIVOT_TABLE` |
| `.setId(cardId)` | 设置 24 位资源 ID，用于重复导入覆盖 |
| `.addRow(field)` / `.addColumn(field)` | 添加指标适用维度 |
| `.addMetric(metric)` | 添加指标平台指标；至少一个 |
| `.addFilter(field, filterType, filterValue)` / `.addSort(field)` | 添加筛选/排序 |
| `.setShowLegend()` / `.setDataLabel()` / `.setAxis()` / `.setTableSetting()` / `.setRawSettings()` | 常用图表设置，和普通 CardBuilder 一致 |
| `.setProps(obj)` / `.setRawProps(key, value)` | 设置指标卡片 `meta.chartMain.props` |
| `.setConfig(obj)` / `.setRawConfig(key, value)` | 设置指标卡片 `meta.chartMain.config` |
| `.setSummary(obj)` | 设置指标卡片 `meta.summary` |
| `.setColumns(columns)` | 设置指标卡片 `content.columns` / `dsInfo.columns` |
| `.addMetricAdditional()` / `.addColorBy()` / `.addSize()` / `.addTooltip()` / `.addSplit()` | 添加副轴、颜色、大小、提示、拆分区域字段 |
| `.build()` | 构建指标卡片 |

完整参数表、MPH 占位列、自由钻取、条件格式、迷你图、业务限定、动态字段等见 `references/metric-chart-reference.md`。

```javascript
var card = createMetricChart(ChartType.PIVOT_TABLE, "销售指标分析")
    .setId("card12345678901234567890")
    .addRow(metricDim("销售额", "区域"))
    .addMetric(metric("销售额"))
    .addSort(metric("销售额", { sortType: SortOrder.DESC }));

registerMetricChart(card.build());
```

多指标示例：

```javascript
var card = createMetricChart(ChartType.GROUPED_COLUMN, "销售与利润")
    .setId("metriccard12345678901234")
    .addRow(metricDim("销售额", "月份", { granularity: Granularity.MONTH }))
    .addMetric(metric("销售额"))
    .addMetric(metric("利润"));

registerMetricChart(card.build());
```

#### 图表选型

- `SINGLE_VALUE`：只展示一个指标值，例如总销售额、订单数、门店数、平均客单价。
- `KPI_CARD`：展示主指标 + 对比指标，例如同比、环比、目标差异；使用时应同时配置 `.addMetric(...)` 和 `.addCompare(...)`。
- 没有对比指标时优先用 `SINGLE_VALUE`，即使卡片放在看板顶部 KPI 区。

#### Axis Config（`.setAxis(config)`）

`config` 对象可包含 `categoryAxis`（X 类目轴）、`mainAxis`（Y 主轴）、`secondaryAxis`（Y 副轴）：

```javascript
.setAxis({
    categoryAxis: {
        visible: true,
        showTitle: true, title: "月份",
        autoRotate: 45,
        labelFontSize: 12,
        showAxisLine: true
    },
    mainAxis: {
        visible: true,
        showTitle: true, title: "销售额",
        min: 0, max: 100000,
        autoExtremes: false,
        showGridLine: true,
        labelFontSize: 11
    },
    secondaryAxis: {
        visible: true,
        showTitle: true, title: "利润率",
        labelFontSize: 11
    }
})
```

| 属性 | 适用轴 | 说明 |
|------|--------|------|
| `visible` | 所有 | 是否显示轴（`false` 隐藏轴） |
| `showTitle` | 所有 | 是否显示轴标题 |
| `title` | 所有 | 轴标题文字 |
| `titleFontSize` / `titleColor` / `titleBold` | 所有 | 标题字体样式 |
| `unit` | mainAxis/secondaryAxis | 单位（如"万元"），显示在标题旁 |
| `min` / `max` | mainAxis/secondaryAxis | 固定轴范围（需 `autoExtremes: false`） |
| `autoExtremes` | mainAxis/secondaryAxis | `true`（默认）自动计算范围 |
| `showGridLine` | mainAxis/secondaryAxis | 是否显示网格线 |
| `reverseValue` | mainAxis/secondaryAxis | 反转轴方向 |
| `labelFontSize` / `labelColor` | 所有 | 刻度标签字体 |
| `autoRotate` | categoryAxis | 标签旋转角度（0/45/90） |
| `textLength` | categoryAxis | 标签截断字符长度 |
| `step` | categoryAxis | 标签间隔（每 N 个显示一个） |
| `showAxisLine` | categoryAxis | 是否显示轴线 |

#### Auxiliary Line Config（`.setAuxiliaryLine(config)`）

辅助线/参考线配置。`config` 对象按轴分组：

```javascript
.setAuxiliaryLine({
    mainAxis: [
        { name: "目标线", color: "#FF0000", valueType: "FIXED", fixedValue: "50000" },
        { name: "平均值", color: "#0088FF", valueType: "CALCULATED", calculatedValue: "AVG" }
    ],
    secondaryAxis: [
        { name: "基准线", color: "#00AA00", valueType: "FIXED", fixedValue: "0.3" }
    ]
})
```

每条辅助线的属性：

| 属性 | 说明 |
|------|------|
| `name` | 辅助线名称（显示在图例中） |
| `color` | 颜色（hex 字符串如 `"#FF0000"`） |
| `valueType` | `"FIXED"`（固定值）或 `"CALCULATED"`（聚合计算） |
| `fixedValue` | 当 `valueType="FIXED"` 时的固定数值（字符串格式） |
| `calculatedValue` | 当 `valueType="CALCULATED"` 时的聚合类型：`"AVG"`（平均值）、`"MAX"`、`"MIN"`、`"MEDIAN"`、`"SUM"` |

#### Conditional Format Config（`.setConditionalFormat(config)`）

条件格式用于按值区间设置颜色。通过 `setRawSettings("conditionalFormat", config)` 设置（因为结构较复杂，建议直接用 `setRawSettings`）。

> **迁移建议**：Tableau 的 Reference Line 对应 `setAuxiliaryLine`，Reference Band 暂无直接等价，可用辅助线近似。条件格式主要用于表格类图表的单元格着色。

#### Card Linkage（图表卡片点击联动）

`CardBuilder.linkTo(target, config)` 用于让一个普通图表卡片、固定路径下钻子卡，或自定义图表的 data view（子卡片），在点击维度值后过滤同一页面内的目标图表卡片。
通过 `settings.asFilter` 配置联动关系，通过 `settings.interaction`配置默认交互，不是 selector 联动。自定义图表作为联动源时还需在 `renderChart` 里回传 `clickFunc`（见 Custom Chart 章节）。

```javascript
// card_00_region_sales.js
var card = createCard(ChartType.GROUPED_COLUMN, "区域销售")
    .setId("aaaaaaaaaaaaaaaaaaaaaaaa")
    .bindDataset(DS)
    .addRow(f("区域"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
    .linkTo(1, {
        fields: [
            { source: "区域", target: "区域" }
        ]
    });

registerCard(card.build());
```

`target` 为数字时，默认和页面布局中的 `card: n` 含义一致，按 `registerCard` / `registerMetricChart` / `registerTextCard` / `registerImageCard` / `registerCustomChart` / `registerDuPontChart` 等可布局资源的注册顺序解析；`registerSelector` 不参与该 index。CardBuilder 点击联动目前只支持普通图表卡片、下钻子卡和杜邦子卡作为目标，不支持 MetricChart、文本、图片和自定义图表。注意它和 `SelectorBuilder.linkTo(cardIndex)` 不同，selector 的 index 是过滤后的可联动目标序列：普通图表和 MetricChart 按注册/布局顺序进入序列，文本/图片/自定义图表等不可联动资源不占序号，杜邦子图追加在末尾。

`target` 也可以是 cardId 字符串，用于引用不在布局 index 中的固定路径下钻子卡；字符串目标也可以指向普通 layout 图表卡。

杜邦子卡片不放页面布局，但可参与联动，数字索引追加在可布局资源之后，顺序为杜邦树中的子卡片构建顺序；也可以使用 cardId 字符串目标直接引用。

构建阶段会按当前点击动作重算 `interaction`：只有联动一个动作时默认直接联动；如果已有跳转、下钻等其它点击动作，会切换为菜单选择。

支持范围：

- 普通图表卡片可以联动同页普通图表卡片，或其它下钻路径中的子卡；CardBuilder 点击联动暂不支持 MetricChart 作为 source 或 target。
- 下钻子卡可以联动同页普通图表卡片。
- 下钻路径内的父子卡、同路径子卡之间不建立联动；下钻子卡之间也不建立联动。
- source 卡片不能跨 page 复用，也不能已有 `settings.asFilter`。
- source 只能用 `.addRow(...)` / `.addColumn(...)` 添加的维度；target 使用目标卡片绑定的数据集字段。
- 一次 `.linkTo(...)` 声明一组 `{ source, target }`；多个目标多次调用。
- 日期联动会按 source 日期粒度对齐目标日期字段；source 使用月/季度/年等粒度时，用 `field(..., { granularity })` 表达该粒度。
- 构建阶段会校验字段、同页关系和联动环。

```javascript
var month = field(DS, "日期", { granularity: Granularity.MONTH });

var trend = createCard(ChartType.BASIC_LINE, "月度趋势")
    .setId("bbbbbbbbbbbbbbbbbbbbbbbb")
    .bindDataset(DS)
    .addRow(month)
    .addMetric(f("订单数", { aggrType: AggrType.SUM }));

var source = createCard(ChartType.GROUPED_COLUMN, "月度区域销售")
    .setId("cccccccccccccccccccccccc")
    .bindDataset(DS)
    .addRow(month)
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
    .linkTo(0, {
        fields: [
            // target 写原始日期字段名时，会按 source 的 MONTH 粒度自动对齐
            { source: month, target: "日期" }
        ]
    });

registerCard(trend.build());  // layout card index 0
registerCard(source.build()); // source linkTo(0) targets trend
```

#### Card Drill（固定路径下钻）

`registerDrillPath(parentCardIndex, drillCards, config?)` 用于声明固定路径下钻。父卡必须是页面 layout 中的普通图表卡；下钻子卡仍用 `createCard(...).build()` 定义，但不要 `registerCard()`，也不要放进页面布局。

```javascript
var province = createCard(ChartType.BASIC_COLUMN, "省份销售额")
    .setId("aaaaaaaaaaaaaaaaaaaaaaaa")
    .bindDataset(DS)
    .addRow(f("省份"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));
registerCard(province.build());

var city = createCard(ChartType.BASIC_BAR, "城市销售额")
    .setId("bbbbbbbbbbbbbbbbbbbbbbbb")
    .bindDataset(DS)
    .addRow(f("城市"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));

var store = createCard(ChartType.PIVOT_TABLE, "门店明细")
    .setId("cccccccccccccccccccccccc")
    .bindDataset(DS)
    .addRow(f("门店"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));

registerDrillPath(0, [city.build(), store.build()], {
    position: DrillPathPosition.BOTTOM
});
```

`position` 可传 `DrillPathPosition.TOP` 或 `DrillPathPosition.BOTTOM`，默认在底部展示。下钻链路的点击交互由 guanvis 维护，不要通过 `setRawSettings("interaction", ...)` 手写。

`drillWithPageFilters` 只对无维度也支持下钻的指标/进度类父卡生效：`SINGLE_VALUE`、`SOLID_GAUGE`、`PROGRESS_BAR`、`PROGRESS_PIE`、`KPI_CARD`、`LIQUID_GAUGE`。未显式传入时不会写入；传给其他图表类型会输出 warning 并忽略。

如果父卡已经通过 `setRawSettings` 写了 `drillPathPosition` 或支持类型上的 `drillWithPageFilters`，建议改为放到 `registerDrillPath` 里统一声明；两边同时写时值必须一致。

下钻子卡可以作为联动 source：

```javascript
var city = createCard(ChartType.BASIC_BAR, "城市销售额")
    .setId("bbbbbbbbbbbbbbbbbbbbbbbb")
    .bindDataset(DS)
    .addRow(f("城市"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
    .linkTo(1, {
        fields: [{ source: "城市", target: "城市" }]
    });
```

普通 layout 卡要联动到下钻子卡时，使用 cardId 字符串：

```javascript
overview.linkTo("bbbbbbbbbbbbbbbbbbbbbbbb", {
    fields: [{ source: "区域", target: "城市" }]
});
```

固定路径下钻支持普通图表卡作为父卡或子卡；不支持自由下钻、指标图表下钻、selector/text/image/custom chart 作为下钻父卡或子卡，也不支持下钻子卡进入页面 layout。

### PageBuilder

**布局单位**：
1. 默认横向使用 12 列栅格；开启精细模式后使用 60 列栅格。
2. 推荐通过 `.setFineMode(true)` 设置为精细模式，且必须在任何 `addRow()` / `placeCard()` / `addTab()` / `addAreaTitle()` / `addCardGroup()` 等布局方法之前调用。
3. `addRow()` 及其快捷方法的 `height` 省略或为 0 时使用默认行高（普通 6，精细 18）。
4. 区域小标题用 `createAreaTitle(...).setId(...).build()` 定义，并通过 `page.addAreaTitle(title)` 放在 Page 根布局；不要放进 tab panel。
5. 卡片组用 `createCardGroup(...).setId(...)` 定义，并通过 `page.addCardGroup(group)` 放在 Page 根布局。
6. 下文布局 API 中的 `cardRef` 表示：非 selector 卡片的数字 index，或已注册 selector 的字符串 ID。`registerSelector()` 不参与数字 index 计数；被布局引用的 selector 不再进入同页筛选器栏。

| 方法 | 说明 |
|------|------|
| `createPage(name)` | 创建 Page |
| `.setId(pgId)` | 设置 Page ID |
| `.setParentDir(dirId)` | 设置页面所在目录 ID（不设置则在根目录），目录 ID 可通过 `guancli page tree` 获取 |
| `.addRow(specs, height?)` | **推荐**：灵活行布局，specs = `[{ card: cardRef, w: colSpan }, ...]`；不传 w 时自动等分当前栅格 |
| `.addFullWidthCard(cardRef, height?)` | 全宽行，等价于 `addRow([{ card }], height)` |
| `.addHalfWidthCards(a, b, height?)` | 左右各半 |
| `.addThirdWidthCards(a, b, c, height?)` | 三等分 |
| `.addQuarterWidthCards(a, b, c, d, height?)` | 四等分 |
| `.placeCard(cardRef, x, y, w, h)` | 精确放置 Card，`w/h` 必须大于 0， `x/y/w/h` 必须显式填写 |
| `.addTab(tab, height?)` | 添加一个满宽 tab 容器；不传 height 时按第一个 panel 内容自动推导 |
| `.addAreaTitle(areaTitle, height?)` | 添加一个满宽区域小标题|
| `.addCardGroup(group, height?)` | 添加一个满宽卡片组；不传 height 时按标题和组内布局自动推导 |
| `.setBackgroundColor(color)` | 页面背景色 |
| `.setCardMargin(margin)` | 卡片间距 |
| `.setFineMode(enabled)` | 开启/关闭精细模式 |
| `.setDashboardTitle(enabled, options?: { title?: string })` | 开启/关闭仪表板标题；未传 `title` 时默认使用 Page 名称 |
| `.setLayoutSetting(config)` | 原始 layout 配置 |
| `.build()` | 构建 |

### AreaTitleBuilder

`areaTitle` 是 Page 根布局里的区域小标题，不是 Card，不绑定数据集，也不会生成 page-card relation。ID 必须以 `areaTitle_` 开头，建议用 `guanvis gen-layout-id areaTitle` 生成。

| 方法 | 说明 |
|------|------|
| `createAreaTitle(name)` | 创建区域小标题，`name` 即为标题的内容，会被写入该组件的 style 中，必须要传 name |
| `.setId(areaTitleId)` | **必填**。设置区域小标题 ID，必须以 `areaTitle_` 开头 |
| `.setShowTitle(boolean)` | 是否显示标题 |
| `.setFontSize(number)` | 字号 |
| `.setColor(color)` | 字体颜色 |
| `.setBold(boolean)` | 是否加粗 |
| `.setTextAlign(alignment)` | 对齐方式, 支持 `left`, `center`, `right` |
| `.setBackgroundColor(color)` | 背景色 |
| `.setShowBgImage(boolean)` | 是否显示背景图 |
| `.setShowIcon(boolean)` | 是否显示图标 |
| `.build()` | 构建 areaTitle result |

```javascript
var salesTitle = createAreaTitle("销售概览")
    .setId("areaTitle_AbCdEf")
    .setFontSize(20)
    .setBold(true)
    .setTextAlign("left")
    .build();

var page = createPage("销售仪表板")
    .setId("p184352b7a76776db5f534df")
    .addAreaTitle(salesTitle)
    .addFullWidthCard(0, 6);

registerPage(page.build());
```

### CardGroupBuilder

`cardGroup` 是一个布局容器，不是 Card，不绑定数据集，也不会生成独立 page-card relation。ID 必须以 `cardGroup_` 开头，建议用 `guanvis gen-layout-id cardGroup` 生成。卡片组目前只能放入根布局，暂不支持放入 tab panel、另一个卡片组或嵌套区域小标题。

| 方法 | 说明 |
|------|------|
| `createCardGroup(name)` | 创建卡片组，`name` 写入分组标题 |
| `.setId(cardGroupId)` | **必填**。设置卡片组 ID，必须以 `cardGroup_` 开头 |
| `.setShowTitle(boolean)` | 是否显示标题，默认 `true` |
| `.addRow(specs, height?)` | 在组内按行放置卡片，写法同 `PageBuilder.addRow()` |
| `.addFullWidthCard(cardRef, height?)` | 在组内放一张满宽卡片 |
| `.placeCard(cardRef, x, y, w, h)` | 在组内精确放置卡片 |

卡片组内布局方法同 `PageBuilder`，使用 `cardRef`。

```javascript
var salesGroup = createCardGroup("销售概览")
    .setId("cardGroup_AbCdEf")
    .addRow([{ card: 0 }, { card: 1 }])
    .addFullWidthCard(2);

var page = createPage("销售仪表板")
    .setId("p184352b7a76776db5f534df")
    .addCardGroup(salesGroup);

registerPage(page.build());
```

#### 页面密度尺寸建议

以下尺寸建议以非精细模式的 12 列布局单位为基准，用于生成页面时选择页面卡片间距和常见卡片高度。精细模式目前只定义横向 60 列栅格与显式 `x/y/w/h` 放置规则，暂不提供独立的密度尺寸换算规则。

密度选择建议：默认使用 `comfortable`；当页面用于汇报展示、希望更强留白感，或卡片数量较少时，使用 `relaxed`。同一页面建议只选择一个主密度基准。

| 项目 | `comfortable` | `relaxed` |
|------|------|------|
| 页面卡片间距 | `20` | `30` |
| 单指标卡高度（`SINGLE_VALUE`） | `2` | `3` |
| 对比指标卡高度（`KPI_CARD`） | `2` | `3` |
| 图表高度 | `6` | `7` |
| 表格高度 | `5` | `6` |

同一行卡片默认使用同一高度，避免页面节奏不齐。若需要压缩页面，可在不影响可读性的前提下降低局部卡片高度。

注意：这里的高度建议是非精细模式下的页面生成建议，不覆盖 `addRow()` 在精细模式下省略高度时使用默认行高 `18` 的 API 行为。

### Tab Builder

tab 用于把页面中的卡片分到多个 panel。适合同一主题下多组互斥查看的分析内容；若卡片较少或需要同时对照，优先直接平铺。关键总览指标通常放在 tab 外，tab 内按实际分析主题组织 panel。支持通过 `page.addTab(tab)` 添加满宽 tab，暂不支持半宽 tab 或 tab 嵌套。 示例可以参考 `evals/tab_layout/`。

| 方法 | 说明 |
|------|------|
| `createTab(name)` | 创建 tab 容器；`name` 用于脚本可读性，页面上显示的是各 panel 的 name |
| `.setId(tabId)` | **必填**。设置 tab ID，必须以 `tab_` 开头且同一页面内唯一。建议用 `guanvis gen-layout-id tab` 生成 |
| `.addPanel(name, callback)` | 添加 panel；callback 接收 `panel` 配置对象，必须在其中放入至少一张卡片 |
| `.setLabelStyle(style)` | 设置标签样式：`TabLabelStyle.UNDERLINE`（默认）、`CARD`、`CAPSULE`、`TRAPEZOID` |
| `.setAlignment(alignment)` | 设置标签对齐：`TabAlignment.LEFT`（默认）、`CENTER`、`RIGHT` |
| `.setTabSize(size)` | 设置标签宽度：`TabSizeType.MAX_CONTENT`（默认）或 `FLEX` |
| `panel.setId(panelId)` | **必填**。设置 panel ID，必须以 `panel_` 开头且同一页面内唯一。建议用 `guanvis gen-layout-id panel` 生成 |
| `panel.addRow(specs, height?)` | 在 panel 内按行放置卡片，写法同 `PageBuilder.addRow()` |
| `panel.addFullWidthCard(cardRef, height?)` | 在 panel 内放一张满宽卡片 |
| `panel.placeCard(cardRef, x, y, w, h)` | 在 panel 内精确放置卡片 |

**使用示例**：

```javascript
var salesTab = createTab("销售分析")
    .setId("tab_AbCdEf")
    .setLabelStyle(TabLabelStyle.CAPSULE)
    .setAlignment(TabAlignment.CENTER)
    .addPanel("区域分析", function(panel) {
        panel
            .setId("panel_GhIjKl")
            .addRow([{ card: 0, w: 6 }, { card: 1, w: 6 }], 6);
    })
    .addPanel("趋势分析", function(panel) {
        panel
            .setId("panel_MnOpQr")
            .addFullWidthCard(2, 8);
    });

var page = createPage("销售仪表板")
    .setId("p184352b7a76776db5f534df")
    .addTab(salesTab);

registerPage(page.build());
```

注意：

- tab 必须有 panel，panel 必须有卡片；不要创建空 tab 或空 panel。
- panel 内布局方法同 `PageBuilder`，使用 `cardRef`。
- panel 布局跟随页面精细模式：`page.setFineMode(true)` 后，panel 也使用 60 列栅格和精细模式默认行高。
- 不需要手工设置 tab 高度；只有明确要固定高度时才给 `page.addTab(tab, height)` 传第二个参数。

### SelectorBuilder（筛选器）

筛选器是特殊的卡片（`cdType=6`），可联动影响其他图表卡片。默认情况下，注册后未被页面布局引用的 selector 会进入页面筛选器栏；如需把筛选器作为画布内容展示，在 `page.js` 中使用 selector 字符串 ID 作为 `cardRef`。

**布局归属**：
- 全局筛选器可进入页面筛选器栏，并按需使用 `.linkToAll()`。
- 凡是作为画布内容或隶属于某个分区、Tab、CardGroup 的筛选器，必须跟随所属布局放置，不进入筛选栏。局部筛选器使用 `.linkTo(...)` 明确联动所属分区内图表，不默认 `.linkToAll()`。

| 方法 | 说明 |
|------|------|
| `createSelector(name)` | 创建筛选器 |
| `.setId(cardId)` | 设置固定资源 ID（同 CardBuilder） |
| `.setSelectorType(type)` | 筛选器类型：`SelectorType.DS_ELEMENTS`（列表选择，默认）、`DS_INTERVAL`（数值范围）、`CALENDAR`（日期）、`TIME_MACRO`（快捷日期区间） |
| `.setFilterType(type)` | 筛选条件：`DS_INTERVAL` 默认 `"BT"`（区间），`DS_ELEMENTS` 默认 `"IN"`。可用值参见 `FilterType` 枚举 |
| `.bindDataset(dsId)` | 绑定数据集（可选，单数据集场景自动绑定） |
| `.bindField(field)` | 绑定筛选字段（`DS_ELEMENTS`/`DS_INTERVAL`/`CALENDAR` 必填，`TIME_MACRO` 不需要），使用 `f("字段名")` 引用 |
| `.setGranularity(granularity)` | 设置 `CALENDAR` 日期筛选器粒度，等价于只允许一个粒度。可用值：`Granularity.YEAR`、`QUARTER`、`MONTH`、`WEEK`、`DAY` |
| `.setGranularityOptions(options, defaultGranularity?)` | 设置 `CALENDAR` 可选日期粒度列表和默认粒度，例如 `[Granularity.MONTH, Granularity.QUARTER]`。未显式设置时会从目标卡片日期字段粒度自动推断 |
| `.setTimeMacroOptions(options, defaultMacroName?)` | 设置快捷日期选项（自动设置 `selectorType` 为 `TIME_MACRO`）。`options`: `[{ name, expr }]`，`expr` 使用内置宏名（见示例）。`defaultMacroName` 默认选中的宏名，传 `null` 则不选（页面打开时无默认值），不传则取第一项。不需要 `bindField` 和 `bindDataset` |
| `.setMultiSelect(bool)` | 是否多选（默认 false） |
| `.setDefaultType(type)` | 默认值类型：`SelectorDefaultType.FIRST_PICK`、`FIXED_VALUE` 或 `ALL`。未显式设置时按 `ALL`/空值生成；作为级联目标且默认是 `ALL`/空值时会自动改为 `FIRST_PICK` |
| `.setDefaultAll()` | 设置默认"全部"（不筛选），等价于 `setDefaultType(SelectorDefaultType.ALL)` |
| `.setDefaultValue(values, displayValues?)` | 设置固定默认值，自动切换为 FIXED_VALUE 类型 |
| `.setDefaultDateRange(start, end, displayValues?)` | 设置 `CALENDAR` 日期区间默认值，自动切换为 FIXED_VALUE；比手写数组更不容易漏填区间端点 |
| `.setFirstPickLink(bool)` | FIRST_PICK 模式下是否联动刷新（默认 false） |
| `.setDisplayType(type)` | 展示类型（仅 `DS_ELEMENTS` 使用）：`SelectorDisplay.SEARCH_LIST`（单选下拉）、`SEARCH_BOX`（多选下拉）、`CHECKBOX`（复选框）、`RADIO`（单选框）、`BUTTON_GROUP`（按钮组）。不设置时根据 multiSelect 自动选择。`DS_INTERVAL` 类型不需要此设置 |
| `.setShowSelectAll(bool)` | 是否显示"全选"（默认 true） |
| `.setCanClear(bool)` | 是否可清空（默认 true） |
| `.linkTo(cardIndex, targetFieldName?)` | 联动指定卡片（cardIndex 为过滤后的可联动目标序列：普通图表和 MetricChart 按注册/布局顺序，杜邦子图追加在末尾），可指定目标字段名（默认同名匹配） |
| `.linkToSelector(selectorId, targetFieldName?)` | 联动指定筛选器（用于省→市→区等级联）。`selectorId` 为目标筛选器 ID；`targetFieldName` 默认按源字段名匹配目标筛选器数据集字段。目标筛选器为 `ALL`/空默认值时会自动启用 `FIRST_PICK + firstPickLink`，固定默认值会保留 |
| `.linkToAll()` | 自动联动所有普通图表卡片、MetricChart 和杜邦子卡片（按同名字段匹配） |
| `.build()` | 构建（触发验证） |

**使用示例**：

```javascript
// selector_01_region.js — 列表选择（DS_ELEMENTS，默认）
var sel = createSelector("区域筛选")
    .setId("s184352b7a76776db5f534df")
    .bindField(f("区域"))
    .setMultiSelect(true)
    .linkToAll()
    .build();
registerSelector(sel);
```

```javascript
// selector_02_profit_rate.js — 数值范围（DS_INTERVAL）
var sel = createSelector("利润率筛选")
    .setId("h61d8bf256952ef3fcf961c5")
    .setSelectorType(SelectorType.DS_INTERVAL)  // 范围筛选器
    .bindField(f("利润率"))
    .linkToAll()
    .build();
registerSelector(sel);
// DS_INTERVAL 默认 filterType="BT"（区间），展示两个输入框（起始值-结束值）
// 也可设置 .setFilterType("EQ") 单值等于，或 "GT"/"LT" 等比较
```

```javascript
// selector_03_date.js — 日期范围（CALENDAR）
var sel = createSelector("日期筛选")
    .setId("abc123def456abc123def456")
    .setSelectorType(SelectorType.CALENDAR)
    .bindField(f("订单日期"))
    .setDefaultDateRange("2026-01-01", "2026-01-31")
    .linkToAll()
    .build();
registerSelector(sel);
// CALENDAR 默认 filterType="BT"（区间），固定默认值必须是 2 个日期值。
// 支持 "2026-01-15"、"2026-01"、"2026-Q1"、"2026-W03"、"2026" 等格式。
// 同一个默认值数组必须使用同一粒度；未显式 setGranularity 时会从默认值格式推断粒度。
```

```javascript
// selector_03_timemacro.js — 快捷日期（TIME_MACRO）
var sel = createSelector("快捷日期")
    .setId("gf7a7ed51ec7c9477fcd1d81")
    .setTimeMacroOptions([
        { name: "今天", expr: ["TODAY"] },
        { name: "昨天", expr: ["YESTERDAY"] },
        { name: "最近7天", expr: ["LAST_7_DAY"] },
        { name: "最近30天", expr: ["LAST_30_DAY"] },
        { name: "本月", expr: ["MONTH_TO_DAY"] },
        { name: "上月", expr: ["LAST_MONTH"] },
        { name: "本年", expr: ["YEAR_TO_DAY"] }
    ], "最近7天")
    .linkToAll()
    .build();
registerSelector(sel);
// TIME_MACRO 不需要 bindField/bindDataset，自动匹配目标卡片中的日期字段联动
// 内置宏名（expr数组只需一个元素）：TODAY, YESTERDAY, LAST_7_DAY, LAST_14_DAY,
//   LAST_30_DAY, LAST_90_DAY, LAST_1_YEAR, LAST_WEEK, LAST_MONTH,
//   WEEK_TO_DAY, MONTH_TO_DAY, YEAR_TO_DAY, DAY_BEFORE_YESTERDAY,
//   WEEK_TO_YESTERDAY, MONTH_TO_YESTERDAY, YEAR_TO_YESTERDAY,
//   QUARTER_TO_DAY, QUARTER_TO_YESTERDAY, YEAR_TO_LAST_MONTH, YEAR_TO_LAST_QUARTER
```

```javascript
// selector_04_cascade.js — 筛选器级联（省 -> 市）
var city = createSelector("市")
    .setId("bbbbbbbbbbbbbbbbbbbbbbbb")
    .bindField(f("市"))
    .build();
registerSelector(city);

var province = createSelector("省")
    .setId("aaaaaaaaaaaaaaaaaaaaaaaa")
    .bindField(f("省"))
    .linkToSelector("bbbbbbbbbbbbbbbbbbbbbbbb") // 默认用“省”过滤“市”筛选器的数据集
    .linkToAll()
    .build();
registerSelector(province);
// 若目标筛选器“市”是 ALL/空默认值（包括显式 setDefaultAll()），
// 会自动启用 FIRST_PICK + firstPickLink，省变化后自动重选第一项并继续向下游联动。
// 若目标筛选器已显式 setDefaultValue([...]) 固定默认值，则保持用户设置。
// 如果目标筛选器数据集中的上游字段不是同名字段，可传第二个参数：
// .linkToSelector("bbbbbbbbbbbbbbbbbbbbbbbb", "所属省份")
```

**筛选器类型选择指南**：
- **离散值**（区域、类别、客户名等文本字段）→ `DS_ELEMENTS`（默认），配合 `setDisplayType` 选择展示样式
- **连续数值范围**（利润率、金额区间等）→ `SelectorType.DS_INTERVAL`，默认区间输入（起始值-结束值）
- **日期选择**（精确日期范围）→ `SelectorType.CALENDAR`，需要 `bindField` 绑定日期字段。默认会从联动目标卡片推断日期粒度；如需固定月/季度等粒度，可用 `.setGranularity(Granularity.MONTH)` 或 `.setGranularityOptions([...], default)`
- **快捷日期区间**（本月/上月/近7天等预设区间）→ `.setTimeMacroOptions(options, default)`，不需要 `bindField`，自动匹配目标卡片日期字段联动。`default` 传 `null` 表示无默认值

**联动机制**：筛选器通过 `settings.asFilter` 配置联动关系。`linkTo(cardIndex)` 会自动构建 `columnMappings`，将筛选器字段映射到目标卡片的同名字段；cardIndex 只统计普通图表、MetricChart 和杜邦子卡片，文本/图片等不可联动资源不占序号。`linkToSelector(selectorId, targetFieldName?)` 用于筛选器联动筛选器，目标必须是已注册的 DS_ELEMENTS/TREE 筛选器，构建时会检查 selector 级联成环；目标为 ALL/空默认值时会自动改为 `FIRST_PICK + firstPickLink`，目标已有固定默认值时保留用户设置。`linkToAll()` 会自动匹配所有普通图表卡片、MetricChart 和杜邦子卡片中的同名字段，不自动包含筛选器。若同一个筛选器同时写了 `linkTo(index, "自定义字段")` 和 `linkToAll()`，显式 `linkTo` 的目标字段映射优先。

**文件命名**：筛选器脚本建议命名为 `selector_NN_xxx.js`，会在 `card_*.js` 之后、`page.js` 之前执行。

### TextCardBuilder（文本卡片）

文本卡片（`cdType=1`）用于在仪表板中展示富文本内容，支持内嵌 SINGLE_VALUE 指标引用（在文本中内联展示实时指标值）。

| 方法 | 说明 |
|------|------|
| `createTextCard(name)` | 创建文本卡片 |
| `.setId(cardId)` | **必填**。设置资源 ID |
| `.addText(text)` | 添加一段普通文本 |
| `.addHeader(text, level?)` | 添加标题（level 1-6，默认 2） |
| `.addMarkdown(markdownText)` | **推荐**。用 Markdown 语法批量定义富文本内容（见下方 Markdown 语法说明） |
| `.embedCard(cardRefId, placeholder?)` | 在当前文本块末尾嵌入一个 SINGLE_VALUE 指标引用。`cardRefId` 是被引用卡片的 ID，`placeholder` 是占位文本（默认空格） |
| `.setRawSettings(key, value)` | 原始设置 |
| `.build()` | 构建（触发验证） |

**使用示例**：

```javascript
// card_00_kpi.js — 先创建被引用的 SINGLE_VALUE 卡片
var kpi = createCard(ChartType.SINGLE_VALUE, "总营收指标")
    .setId("a184352b7a76776db5f534df")
    .bindDataset(DS)
    .addMetric(f("营收", { aggrType: AggrType.SUM }));
registerCard(kpi.build());

// card_01_text.js — 文本卡片引用上面的指标
var text = createTextCard("业绩概览")
    .setId("b284352b7a76776db5f534df")
    .addHeader("本月业绩报告")
    .addText("本月总营收为 ")
    .embedCard("a184352b7a76776db5f534df", "[总营收]")
    .addText("，较上月有所增长。");
registerTextCard(text.build());
```

**嵌入机制**：文本卡片使用 Draft.js 格式存储内容。`embedCard()` 通过 `entityMap` 中的 `Macro` 类型实体引用其他 SINGLE_VALUE 卡片的 ID，BI 系统在渲染时会将占位文本替换为实时指标值。被引用的卡片**必须是 SINGLE_VALUE 类型**。

**Markdown 模式**（推荐用于复杂文本）：

`addMarkdown()` 支持以下 Markdown 语法，自动转换为 BI 富文本格式：

| 语法 | 效果 |
|------|------|
| `# ~ ######` | 一至六级标题 |
| `**text**` | **加粗** |
| `*text*` | *斜体* |
| `~~text~~` | ~~删除线~~ |
| `` `code` `` | 行内代码 |
| `- item` / `* item` | 无序列表（支持缩进嵌套） |
| `1. item` | 有序列表 |
| `> quote` | 引用块 |
| `---` | 分隔线 |
| `{{cardId:占位文本}}` | 内嵌 SINGLE_VALUE 指标引用 |

```javascript
// 使用 addMarkdown 一次性定义复杂富文本（ID 通过 guanvis genid 预生成）
var kpiId = "c384352b7a76776db5f534df";
var kpi = createCard(ChartType.SINGLE_VALUE, "总营收")
    .setId(kpiId)
    .bindDataset(DS)
    .addMetric(f("营收", { aggrType: AggrType.SUM }));
registerCard(kpi.build());

var text = createTextCard("数据报告")
    .setId("d484352b7a76776db5f534df")
    .addMarkdown(
        "## 月度业绩报告\n\n" +
        "本月总营收为 {{" + kpiId + ":总营收}}，**表现优异**。\n\n" +
        "### 关键发现\n" +
        "1. 华东区域贡献最大\n" +
        "2. 新品类增长 *显著*\n\n" +
        "> 数据截至本月最后一个工作日"
    );
registerTextCard(text.build());
```

### createTextCardWithData（带数据的文本卡片）

高层便捷方法，一次调用自动完成：创建多个 SINGLE_VALUE 指标卡片 → 创建包含 Markdown 富文本的文本卡片 → 自动注册所有卡片。省去手动创建 KPI 卡片、拼接 `{{cardId:placeholder}}` 占位符、依次注册的繁琐步骤。

```javascript
createTextCardWithData(config)
```

**config 参数**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `textCardId` | 是 | 文本卡片的资源 ID |
| `textCardName` | 否 | 文本卡片名称（默认"数据报告"） |
| `textCardDescription` | 否 | 文本卡片描述 |
| `dsId` | 否 | 数据集 ID（默认使用 `DS`，即第一个 `defineDataset` 的数据集） |
| `metrics` | 是 | 指标配置数组（见下表） |
| `markdown` | 是 | Markdown 模板，用 `{{字段名或label}}` 引用指标 |

**metrics 数组元素**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | 是 | 该 SINGLE_VALUE 卡片的资源 ID |
| `fieldName` | 是 | 数据集中的字段名 |
| `label` | 否 | 指标别名（用于 Markdown 中引用和卡片命名，默认取 fieldName） |
| `aggrType` | 否 | 聚合类型（默认 `AggrType.SUM`） |
| `numberFormat` | 否 | 数值格式 |

**Markdown 中的引用语法**：使用 `{{label}}` 或 `{{fieldName}}` 引用指标，函数自动替换为对应 SINGLE_VALUE 卡片的 Macro 引用。

**使用示例**：

```javascript
createTextCardWithData({
    textCardId: "t184352b7a76776db5f534df",
    textCardName: "月度业绩报告",
    metrics: [
        { id: "m184352b7a76776db5f534df", fieldName: "营收", label: "总营收",
          aggrType: AggrType.SUM, numberFormat: NumberFormat.currency("¥", 0) },
        { id: "m284352b7a76776db5f534df", fieldName: "利润", aggrType: AggrType.SUM },
        { id: "m384352b7a76776db5f534df", fieldName: "订单数", label: "总订单",
          aggrType: AggrType.COUNT }
    ],
    markdown: [
        "## 月度业绩报告",
        "",
        "本月总营收为 {{总营收}}，利润 {{利润}}。",
        "",
        "### 关键指标",
        "- 总订单数：{{总订单}}",
        "- 利润率表现**优异**",
        "",
        "> 数据截至本月最后一个工作日"
    ].join("\n")
});

// 布局：第一行 3 个 KPI 指标卡（cardIndex 0~2），第二行全宽文本报告（cardIndex 3）
var page = createPage("业绩仪表板")
    .setId("p184352b7a76776db5f534df")
    .addRow([{ card: 0, w: 4 }, { card: 1, w: 4 }, { card: 2, w: 4 }], 3)
    .addFullWidthCard(3, 6);
registerPage(page.build());
```

**注册顺序**：`createTextCardWithData` 会按 `metrics` 数组顺序先注册 SINGLE_VALUE 卡片（cardIndex 从 0 开始），最后注册文本卡片。在 page 布局中，前 N 个 cardIndex 对应 N 个指标卡，第 N 个 cardIndex 对应文本卡片。

### ImageCardBuilder（图片卡片）

图片卡片（`cdType=4`）用于在仪表板中展示图片，支持外链 URL 和本地图片文件。

**支持的图片格式**：本地上传仅支持 `jpg/jpeg/png/gif` 格式。**不支持 SVG**——如需使用 SVG 图片，必须先转换为 PNG 等支持的格式后再上传。

**SVG 转 PNG 推荐方式**（按优先级排列）：
1. `npx sharp-cli -i input.svg -o output.png -f png` — 基于 sharp（最流行的 Node.js 图像处理库），无需提前安装
2. `npx sharp-cli -i input.svg -o output.png -f png resize 1200` — 指定宽度缩放
3. **agent-browser** — 通过浏览器打开 SVG 文件再截图，适合需要精确 CSS/字体渲染的场景

不要使用 `ffmpeg`（不支持 SVG）或 `cairosvg`（Python 依赖复杂易出错）。

| 方法 | 说明 |
|------|------|
| `createImageCard(name)` | 创建图片卡片 |
| `.setId(cardId)` | **必填**。设置资源 ID |
| `.setUrl(url)` | 设置外链图片 URL（sourceType=1） |
| `.setLocalImage(filePath)` | 设置本地图片文件路径（sourceType=2），打包时图片会作为附件写入 ZIP |
| `.setRenderType(type)` | 设置图片渲染模式：`ImageRenderType.RATIO`（原比例，默认）、`ImageRenderType.STRETCH`（拉伸填满）、`ImageRenderType.FIT_TO_CONTENT`（自适应内容） |
| `.setRawSettings(key, value)` | 原始设置 |
| `.build()` | 构建（触发验证） |

**使用示例**：

```javascript
// 外链图片
var img1 = createImageCard("Logo")
    .setId("c384352b7a76776db5f534df")
    .setUrl("https://example.com/logo.png");
registerImageCard(img1.build());

// 本地图片 + 拉伸填满模式（适合 Banner）
var img2 = createImageCard("Banner")
    .setId("d484352b7a76776db5f534df")
    .setLocalImage("./assets/banner.png")
    .setRenderType(ImageRenderType.STRETCH);
registerImageCard(img2.build());
```

**本地图片机制**：`setLocalImage()` 指定本地文件路径，`pack`/`publish` 时工具会将图片文件读取并作为 Appendix 附件打包进 ZIP 资源包。导入 BI 系统时，后端会将图片存储到内部文件存储并建立引用关系。仅支持 jpg/jpeg/png/gif 格式；SVG 需先转为 PNG。

### CustomChartBuilder（自定义图表）

自定义图表（`cdType=10`）允许使用自定义 HTML/CSS/JavaScript 代码渲染图表，适用于内置图表类型无法满足的场景。支持三种子类型：

| 子类型 | 说明 |
|--------|------|
| `CustomChartSubType.SDK` | 标准自定义图表，在 iframe 中运行。支持任意前端库（Vega-Lite/D3/ECharts 等）。**Tableau 迁移场景首选** |
| `CustomChartSubType.ECHARTS_LITE` | 原生 ECharts 模式，无 iframe。只需写 JS 脚本设置 `option`。仅适用于 ECharts 能满足的简单场景 |

**子类型选择指南**：
- 自定义图表优先使用 **SDK** 模式 + Vega-Lite，模板和文档支持最完整
- 纯 ECharts 且脚本极简的场景 → 可用 **ECHARTS_LITE**（无 iframe 开销，但也可以用 SDK 模式）
- SDK 模式运行在 iframe 中，需要通过 `__asset_text__`/`__asset_base64__` 内嵌外部资源

| 方法 | 说明 |
|------|------|
| `createCustomChart(name)` | 创建自定义图表卡片 |
| `.setId(cardId)` | **必填**。设置资源 ID |
| `.setSubType(subType)` | 设置子类型，默认 `SDK`。用 `CustomChartSubType.XXX` |
| `.loadContent(baseName)` | **推荐**。从文件加载 HTML/CSS/JS。工具自动读取 `baseName.html`、`baseName.css`、`baseName.js`（`.js` 必须存在，`.html` 和 `.css` 可选） |
| `.setContent(html, css, script)` | 内联设置 HTML/CSS/JS（仅在内容极简时使用）|
| `.addLib(url)` | 添加外部 JS 库 URL |
| `.setProps(props)` | 设置自定义属性 |
| `.addDataView(cardBuilder)` | 添加数据视图（子卡片），子卡片使用普通 `CardBuilder` 创建（任意 ChartType 均可，系统自动转换为 DATA_GRID）。用 `.addRow()` 放维度、`.addMetric()` 放度量 |
| `.setRawSettings(key, value)` | 原始设置 |
| `.build()` | 构建（触发验证） |

**数据流**：BI 前端查询子卡片（data view）的数据 → 将结果按列组织为 `data` → 传给自定义图表的 `renderChart(data, clickFunc, config)` 函数（SDK）或直接可用 `data` 变量（ECHARTS_LITE）。

**点击联动（custom chart 作为联动源）**：在 data view（子卡片 `CardBuilder`）上调用 `.linkTo(target, { fields: [{ source, target }] })`，即可让自定义图表成为同页联动源——图表内部点击某维度时，按映射过滤目标卡片。`target` 仍按布局 index 或 cardId 解析（不能指向自身所在的自定义图表）。校验、字段匹配、同页与联动环检查与普通图表卡片完全一致，结果写为 data view 的 `settings.asFilter` + `interaction=LINK`。SDK 子类型必须在 `renderChart` 里用第二个入参 `clickFunc` 回传点击：`clickFunc({ clickedItems: [{ idx: [viewIndex, columnIndex], colName: '列名', value: ['选中值'] }] })`；`idx[1]` 指向 data view 行字段的列序号。ECHARTS_LITE 也用同样的 `clickFunc`。

`data` 格式（二维数组，外层每个元素对应一个数据视图，内层每个元素对应一个字段列）：
```javascript
// data[viewIndex][columnIndex] = { name: "字段名", data: [...值], numberFormat: ... }
data[0][0].name  // → "类别"
data[0][0].data  // → ["办公用品", "技术", "家具"]
data[0][1].name  // → "销售额"
data[0][1].data  // → [4916842, 3157709.5, 3037943.5]
```

`config` 包含 `{ theme: "LIGHT"|"DARK", colors: string[], customOptions: object, language: string }`。

**推荐的工作方式**（文件模式）：

1. AI 将自定义图表的 HTML/CSS/JS 分别写入独立文件（如 `my_chart.html`、`my_chart.css`、`my_chart.js`）
2. 在 card 脚本中使用 `.loadContent("my_chart")` 引用

文件结构示例（**内容文件必须放在子目录中**，避免被 pack 当作 card 脚本执行）：
```
project/
├── schema.js
├── card_01_custom.js       ← card 脚本（loadContent("charts/my_chart")）
├── page.js
└── charts/                 ← 子目录：自定义图表内容文件
    ├── my_chart.html       ← HTML（可选）
    ├── my_chart.css        ← CSS（可选）
    ├── my_chart.js         ← JavaScript（必须）
    └── us-10m.json         ← 资源文件（可选，通过 asset 占位符引用）
```

**资源内嵌**（`__asset_text__` / `__asset_base64__`）：

自定义图表运行在 iframe 沙箱中，不能从外部 URL 加载资源（CORS/sandbox 限制）。需要将 GeoJSON、图片等资源内嵌到 JS/HTML 中。使用 asset 占位符让 `pack`/`publish` 自动替换：

```javascript
// 在 .js 文件中引用本地文件为 JSON 字符串（自动 escape）
var geoData = JSON.parse(__asset_text("./us-10m.json")__);

// 引用本地文件为 base64 编码字符串
var logoBase64 = __asset_base64("./logo.png")__;
```

- `__asset_text("path")__` — 读取文件内容，做 JSON string escape 后替换（结果带双引号，是一个合法的 JSON 字符串字面量）
- `__asset_base64("path")__` — 读取文件内容，做 base64 编码后替换（结果带双引号）
- 路径相对于内容文件所在目录（即 `.loadContent()` 指向的目录）
- 路径不允许向上跳出内容目录（安全限制）
- 占位符仅在 `pack`/`publish` 构建时处理，不影响 AI 脚本的可读性

### DuPontBuilder（杜邦分析图）

杜邦分析图不是普通 `ChartType`，而是 BI 的 `LAYOUT` 卡片（`cdType=9`），meta 结构为 `{ layoutType: "DU_PONT", layout: ... }`。guanvis 用 `createDuPontChart()` 创建父卡片，用普通 `CardBuilder` 创建每个节点中的指标卡。

| 方法 | 说明 |
|------|------|
| `createDuPontChart(name)` | 创建杜邦分析图父卡片 |
| `.setId(cardId)` | **必填**。设置杜邦父卡片 ID |
| `.setRoot(cardBuilder, options?)` | 设置根节点。`cardBuilder` 必须是已 `.setId()` 的普通图表卡片，通常为 `KPI_CARD` |
| `.addChild(parentCardOrId, childCardBuilder, options?)` | 给指定父节点添加子节点。`parentCardOrId` 可传父节点的 `CardBuilder` 或 cardId |
| `.addChildren(parentCardOrId, childCardBuilders, optionsOrOptionsList?)` | 批量添加子节点 |
| `.setLayout({})` | 仅用于创建空杜邦图占位；非空 raw layout 不支持，请用 `.setRoot()` / `.addChild()` 自动注册子卡 |
| `.setDescription(desc)` | 描述 |
| `.setRawSettings(key, value)` | 原始 settings |
| `.build()` | 构建（触发验证） |

`options` 支持：

| 属性 | 说明 |
|------|------|
| `operation` | 记录在父节点 `operations` 中的运算符，如 `"*"`, `"/"`, `"+"`, `"-"` |
| `bgColor` | 节点背景色 |
| `style` | 节点样式覆盖，支持 `titleFont`、`kpiFont`、`bgColor`、`kpiLayout`、`collapse`、`width`、`height` 等 |

`operation` 使用 `DuPontOperation.ADD` / `SUBTRACT` / `MULTIPLY` / `DIVIDE` / `NONE`；也兼容 `"*"`、`"/"` 并自动转成 BI 前端使用的 `"×"`、`"÷"`。`kpiLayout` 使用 `DuPontKpiLayout.TILE`（平铺式）或 `DuPontKpiLayout.COMPACT`（紧凑式）。

```javascript
var roe = createCard(ChartType.KPI_CARD, "净资产收益率")
    .setId("aaaaaaaaaaaaaaaaaaaaaaaa")
    .bindDataset(DS)
    .addMetric(f("净利润", { aggrType: AggrType.SUM }));

var margin = createCard(ChartType.KPI_CARD, "销售净利率")
    .setId("bbbbbbbbbbbbbbbbbbbbbbbb")
    .bindDataset(DS)
    .addMetric(f("销售收入", { aggrType: AggrType.SUM }));

var turnover = createCard(ChartType.KPI_CARD, "资产周转率")
    .setId("cccccccccccccccccccccccc")
    .bindDataset(DS)
    .addMetric(f("资产总额", { aggrType: AggrType.SUM }));

var dupont = createDuPontChart("杜邦分析")
    .setId("dddddddddddddddddddddddd")
    .setRoot(roe, { style: { kpiLayout: DuPontKpiLayout.COMPACT } })
    .addChild(roe, margin, { operation: "*" })
    .addChild(roe, turnover, { operation: "*" });

registerDuPontChart(dupont.build());
```

页面布局中放杜邦父卡片即可，杜邦子卡片会以 `pId=父卡片ID` 打包，不要再单独放进页面布局：

```javascript
var page = createPage("财务分析")
    .setId("eeeeeeeeeeeeeeeeeeeeeeee")
    .addFullWidthCard("dddddddddddddddddddddddd", 10);
registerPage(page.build());
```

本地校验会检查：
- 杜邦父卡片必须是 `LAYOUT` payload，`layoutType` 必须是 `DU_PONT`
- layout 节点必须有 `id` / `cardId`
- layout 中引用的 `cardId` 必须是当前杜邦父卡片名下的普通子卡片，不能引用无关顶层卡片、selector、其它 layout 或自定义图表 data view
- 节点 `id` 不允许重复

**内嵌第三方 JS 库**（如 Vega-Lite、D3 等）：

SDK 模式的 iframe 沙箱**阻止从外部 CDN 加载脚本**（sandbox/CSP 限制）。`addLib()` 添加的 CDN URL 在安全模式下不生效。正确做法是：

1. 将第三方库的 `.min.js` 文件下载到 `charts/` 目录
2. 在渲染 JS 文件中用 `__asset_text__` 内嵌并通过 `new Function()` 执行

```javascript
// 内嵌 Vega-Lite 库（下载到 charts/ 目录后引用）
var _vegaSrc = __asset_text("./vega.min.js")__;
var _vegaLiteSrc = __asset_text("./vega-lite.min.js")__;
var _vegaEmbedSrc = __asset_text("./vega-embed.min.js")__;
(new Function(_vegaSrc))();
(new Function(_vegaLiteSrc))();
(new Function(_vegaEmbedSrc))();

// 之后即可使用 vegaEmbed(...)
```

**注意**：内嵌大型库会增加资源包体积（Vega-Lite 全套约 800KB），但确保在所有环境下都能正常运行。`addLib()` 仅在未开启安全模式的环境中有效，不推荐用于生产。

**Vega-Lite 地图（geoshape）的坑**：Vega-Lite 的 `geoshape` mark 在使用 inline GeoJSON 数据时，projection 的自动 fit 行为不可靠，常导致地图渲染为空白。推荐的替代方案：

- **方案 A（推荐）**：只内嵌 `vega.min.js`，手动实现 Mercator 投影 + SVG 渲染。`vega.min.js` 中不直接暴露 `geoMercator` 等 d3-geo API，需自行实现投影公式：
  ```javascript
  function toRad(deg) { return deg * Math.PI / 180; }
  function mercX(lon) { return toRad(lon); }
  function mercY(lat) { return Math.log(Math.tan(Math.PI / 4 + toRad(lat) / 2)); }
  // 计算 projected bounding box 后用 fitSize 逻辑缩放到容器
  ```
  关键：x 和 y 都必须转换到同一单位空间（弧度），否则宽高比会错误。
- **方案 B**：使用 `ECHARTS_LITE` 子类型代替 SDK，ECharts 的 `registerMap` + `visualMap` 对 inline GeoJSON 支持更好。
- **方案 C**：如果必须用 Vega-Lite，`data.values` 必须是完整的 FeatureCollection 对象（不是 features 数组），`format` 设为 `{"type": "json", "property": "features"}`。参考 [vega-lite#3432](https://github.com/vega/vega-lite/issues/3432)。
- 只有完整格式 `__asset_text("path")__` 才会被替换，注释或字符串中的 `__asset_text__` 文字不受影响
- **来源标注**：对于从网上下载的资源文件（如 GeoJSON），在占位符上方用注释标注来源 URL，便于后续维护和溯源：

```javascript
// source: https://cdn.jsdelivr.net/npm/vega-datasets@2/data/us-10m.json
var geoData = JSON.parse(__asset_text("./us-10m.json")__);
```

**SDK 子类型示例**（iframe 模式，使用 `gd-plugin.js`）：

`card_01_custom.js`（card 脚本）：
```javascript
var dataView = createCard(ChartType.DATA_GRID, "数据视图")
    .setId("a484352b7a76776db5f534df")
    .bindDataset(DS)
    .addRow(f("类别"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));

var chart = createCustomChart("自定义柱状图")
    .setId("b484352b7a76776db5f534df")
    .setSubType(CustomChartSubType.SDK)
    .loadContent("charts/my_chart")
    .addDataView(dataView);

registerCustomChart(chart.build());
```

`charts/my_chart.html`：
```html
<div id="container"></div>
<script>loadBuiltinResourceByName('echarts')</script>
```

`charts/my_chart.css`：
```css
#container { width: 100%; height: 100%; }
```

`charts/my_chart.js`（运行在 BI iframe 中的渲染代码）：
```javascript
var myChart = echarts.init(document.getElementById('container'));
function renderChart(data, clickFunc, config) {
  // data[0] = 第一个数据视图的列数据: [{name:"类别", data:[...]}, {name:"销售额", data:[...]}]
  var cols = data[0] || [];
  myChart.setOption({
    xAxis: { type: 'category', data: (cols[0] || {}).data || [] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: (cols[1] || {}).data || [] }],
    color: config.colors
  });
  myChart.resize();
}
new GDPlugin().init(renderChart);
```

**ECHARTS_LITE 子类型示例**（无 iframe，直接操作 ECharts，仅适用于纯 ECharts 场景）：

`card_01_echarts.js`（card 脚本）：
```javascript
var dataView = createCard(ChartType.DATA_GRID, "数据视图")
    .setId("c484352b7a76776db5f534df")
    .bindDataset(DS)
    .addRow(f("类别"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));

var chart = createCustomChart("ECharts 柱状图")
    .setId("d484352b7a76776db5f534df")
    .setSubType(CustomChartSubType.ECHARTS_LITE)
    .loadContent("charts/echarts_bar")
    .addDataView(dataView);

registerCustomChart(chart.build());
```

`charts/echarts_bar.js`（ECharts 渲染代码，HTML 和 CSS 文件可省略）：
```javascript
// data[0] = [{name:"类别", data:[...]}, {name:"销售额", data:[...]}]
var cols = data[0] || [];
var categories = (cols[0] || {}).data || [];
var values = (cols[1] || {}).data || [];
option = {
  xAxis: { type: "category", data: categories },
  yAxis: { type: "value" },
  series: [{ type: "bar", data: values }]
};
```

> **注意**：ECHARTS_LITE 模式下，脚本中的 `data`、`config`、`clickFunc`、`utils` 是预定义变量。将 ECharts option 赋值给 `option` 变量即可渲染。**不要使用 `new GDPlugin().init()`**，那是 SDK（iframe）模式的 API。

**ECHARTS_LITE 自定义地图示例**（使用 `__asset_text__` 内嵌 GeoJSON）：

`card_01_map.js`（card 脚本）：
```javascript
var dataView = createCard(ChartType.DATA_GRID, "地图数据视图")
    .setId("c584352b7a76776db5f534df")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addMetric(calcField("利润率", "SUM([利润])/SUM([销售额])"));

var chart = createCustomChart("各省利润率(ECharts)")
    .setId("d584352b7a76776db5f534df")
    .setSubType(CustomChartSubType.ECHARTS_LITE)
    .loadContent("charts/profit_map")
    .addDataView(dataView);

registerCustomChart(chart.build());
```

`charts/profit_map.js`（ECharts 地图渲染，需配套 `china.json`）：
```javascript
// source: guandata-web 内置地图或 https://geo.datav.aliyun.com/...
var chinaGeoJSON = JSON.parse(__asset_text("./china.json")__);

var cols = data[0] || [];
var names = (cols[0] || {}).data || [];
var values = (cols[1] || {}).data || [];

var mapData = [];
for (var i = 0; i < names.length; i++) {
    mapData.push({ name: names[i], value: +(values[i]) || 0 });
}

echarts.registerMap("china", chinaGeoJSON);

option = {
    tooltip: { trigger: "item" },
    visualMap: { min: -0.3, max: 0.3, calculable: true,
        inRange: { color: ["#e0f3f8", "#abd9e9", "#74add1", "#4575b4", "#313695"] } },
    series: [{ type: "map", map: "china", label: { show: true, fontSize: 10 }, data: mapData }]
};
```

> **适用场景**：ECHARTS_LITE 自定义地图仅适用于不需要其他 JS 库的简单场景。Tableau 迁移场景应使用 **SDK 模式**（支持 Vega-Lite 等更灵活的库）。中国地图优先使用 `BASIC_MAP` 内置图表。

### 枚举常量

| 枚举 | 常用值 | 说明 |
|------|--------|------|
| `ChartType` | `BASIC_COLUMN`, `BASIC_BAR`, `BASIC_LINE`, `PIE`, `PIVOT_TABLE`, `DETAIL_TABLE`, `KPI_CARD`, `BASIC_MAP`, `WORLD_MAP`, `POINT_MAP`, `BUBBLE_MAP` 等 74 种 | 图表类型（与后端 ChartType.scala 一一对应）。地图类型使用 `addRow()` 放地理维度 |
| `AggrType` | `SUM`, `AVG`, `COUNT`(=CNT), `COUNT_DISTINCT`(=CNT_DISTINCT), `MIN`, `MAX` | 聚合类型 |
| `FieldType` | `STRING`, `INT`, `LONG`, `DOUBLE`, `FLOAT`, `DATE`, `BOOL`, `DECIMAL` | 字段数据类型 |
| `SortOrder` | `ASC`, `DESC` | 排序方向 |
| `Granularity` | `NONE`, `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAYOFWEEK`, `DAY`, `HOUR`, `MINUTE`, `SECOND` | 日期粒度 |
| `FilterType` | `IN`, `NOT_IN`, `GT`, `GE`, `LT`, `LE`, `EQ`, `NE`, `BT`（区间）, `CONTAINS`, `NOT_CONTAINS`, `STARTSWITH`, `ENDSWITH`, `IS_NULL`, `NOT_NULL` | 筛选条件类型 |
| `FilterLevel` | `DETAIL`（明细）, `AGGREGATION`（聚合）, `RESULT`（结果） | 筛选级别 |
| `NumberFormat` | `.number()`, `.currency()`, `.percentage()`, `.auto()`, `.custom()` | 数值格式化工厂 |
| `SelectorType` | `DS_ELEMENTS`（默认）, `DS_INTERVAL`, `CALENDAR`, `TIME_MACRO` | 筛选器类型 |
| `SelectorDisplay` | `SEARCH_LIST`（单选下拉）, `SEARCH_BOX`（多选下拉）, `CHECKBOX`（复选框）, `RADIO`（单选框）, `BUTTON_GROUP`（按钮组） | 筛选器展示类型，不设置时根据 multiSelect 自动推断 |
| `SelectorDefaultType` | `FIRST_PICK`, `FIXED_VALUE`, `ALL`（默认，全部/不筛选） | 筛选器默认值类型 |
| `CardType` | `CHART`(0), `TEXT`(1), `IFRAME`(2), `PICTURE`(4), `SELECTOR`(6), `LAYOUT`(9) | 卡片类型（内部使用，通常不需要直接引用） |
| `ImageSourceType` | `OUTSIDE_LINK`(1), `LOCAL_IMAGE`(2) | 图片来源类型 |
| `ImageRenderType` | `RATIO`(1，原比例), `STRETCH`(2，拉伸填满), `FIT_TO_CONTENT`(3，自适应内容) | 图片渲染模式 |
| `CustomChartSubType` | `SDK`（iframe，首选）, `ECHARTS_LITE`（原生 ECharts） | 自定义图表子类型 |
| `DuPontKpiLayout` | `TILE`（平铺式）, `COMPACT`（紧凑式） | 杜邦节点指标布局 |
| `DuPontOperation` | `NONE`, `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE` | 杜邦父节点到各子节点的运算符 |
