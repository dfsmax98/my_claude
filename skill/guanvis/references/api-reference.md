## API 参考

### 数据集与字段

| 函数 | 说明 |
|------|------|
| `defineDataset(dsId, columns, options?)` | 定义数据集 schema（由 init 命令生成）。第一个数据集自动暴露为 `global.DS`（dsId 字符串）。`options.displayType` 指定数据集类型（如 `"EXCEL"`, `"DATAFLOW"`），确保看板页面正确显示数据集图标 |
| `field(dsId, fieldName, overrides?)` | 从 schema 构造字段引用，`dsId` 是字符串。可叠加 aggrType/alias/numberFormat/sortType/granularity 等 |
| `f(fieldName, overrides?)` | `field(DS, fieldName, overrides)` 的简写，仅适用于**单数据集**场景 |
| `calcField(name, formula, opts?)` | 创建卡片级计算字段（公式中用 `[字段名]` 引用字段）。`opts`: `calculationType`/`fdType`/`numberFormat`/`advCalc`/`fieldFormat` 等 |
| `filterField(dsId, fieldName, filterType, filterValue?, opts?)` | 创建筛选字段（带 filterType/filterValue），传给 `.addFilter()` 使用 |
| `getDataset(dsId)` | 获取已定义的数据集对象（返回对象，**不要**传给 `field()` 和 `bindDataset()`） |

**`field()` vs `calcField()` vs `filterField()` 选择**：
- `field()` — 引用数据集中已有的字段，用于维度/指标/排序等；单字段聚合优先在这里设置 `aggrType`，如 `SUM`、`AVG`、`COUNT`、`COUNT_DISTINCT`、`MIN`、`MAX`
- `calcField()` — 创建公式计算字段（如利润率 = 利润/销售额），用于必须组合多个字段、多个聚合或数据库函数的指标
- `filterField()` — 创建筛选条件字段，专门用于 `.addFilter()`

三者都是字段工厂函数，输出都是字段对象。

### 指标平台指标与维度

当卡片基于指标平台已有指标创建时，先生成指标事实快照：

```bash
guanvis metric-init <metricId1> <metricId2> -d ./my_dashboard/
```

`metric-init` 会写入 `metrics.js`，内容通过 `defineMetric()` 保存指标 ID、名称、类型、数据格式、适用维度和时间维度。AI 不应手改 `metrics.js`；指标变化时重新运行命令。

| 函数 | 说明 |
|------|------|
| `defineMetric(metricDef)` | 定义指标事实快照，由 `metric-init` 自动生成 |
| `metric(metricIdOrName, overrides?)` | 引用指标平台指标，用于 `createMetricChart(...).addMetric(...)` |
| `metricDim(metricIdOrName, dimName, overrides?)` | 引用指定指标的适用维度，用于行/列/筛选/排序 |
| `metricDim(dimName, overrides?)` | 在所有已定义指标中按维度名查找；同名维度较多时不要使用 |
| `getMetric(metricIdOrName)` | 获取已定义指标对象 |

指标搜索使用位置参数，例如 `guancli metric search '销售额'`。不要使用 `--name-like`。

复杂指标卡片的 `zoneData`、`props`、`config`、`summary`、MPH 占位列和验证方式见 `references/metric-chart-reference.md`。

示例：

```javascript
var card = createMetricChart(ChartType.PIVOT_TABLE, "销售指标分析")
    .setId("card12345678901234567890")
    .addRow(metricDim("销售额", "区域"))
    .addMetric(metric("销售额"));

registerMetricChart(card.build());
```

**聚合字段优先级**：

- 单字段聚合必须优先使用原生聚合配置，例如 `.addMetric(f("销售额", { aggrType: AggrType.SUM }))`、`.addMetric(f("客户ID", { aggrType: AggrType.COUNT_DISTINCT }))`。
- 去重计数使用 `AggrType.COUNT_DISTINCT`；不要在 `calcField()` 里写 `COUNT_DISTINCT([字段])`，这不是通用 SQL 函数，数据库直连时可能下推失败。
- 只有复合指标才使用 `calcField()`，例如 `SUM([销售额]) / COUNT(DISTINCT [客户ID])`；这类公式必须按 `schema.js` 里的 `displayType` 对应数据库方言生成。

**多数据集场景**：当 `schema.js` 包含多个 `defineDataset()` 时，`DS` 指向第一个数据集的 dsId 字符串。其他数据集需要直接用 dsId 字符串：

```javascript
var DS_ORDER = "od8e9899dfcb14f689e1bf80";  // 直接写 dsId 字符串
var card = createCard(ChartType.BASIC_LINE, "趋势图")
    .bindDataset(DS_ORDER)
    .addRow(field(DS_ORDER, "订单日期", { granularity: Granularity.MONTH }))
    .addMetric(field(DS_ORDER, "销售额", { aggrType: AggrType.SUM }));
```

### Number Format

| 工厂方法 | 参数 | 说明 |
|----------|------|------|
| `NumberFormat.number(decimals?, thousands?)` | int, bool | 数值格式（默认 0 位小数，有千分位） |
| `NumberFormat.currency(symbol?, decimals?)` | string, int | 货币格式（默认 ¥，2 位小数） |
| `NumberFormat.percentage(decimals?, divideBy?)` | int, int | 百分比格式（默认 1 位小数） |
| `NumberFormat.auto(unit?)` | string | 自动缩略单位（万/亿/K/M） |
| `NumberFormat.custom(opts)` | object | 自定义格式 |

### 日期粒度 (Granularity)

DATE 类型字段拖入维度区时可指定时间粒度：

```javascript
f("订单日期", { granularity: Granularity.YEAR })   // 按年
f("订单日期", { granularity: Granularity.QUARTER }) // 按季度
f("订单日期", { granularity: Granularity.MONTH })   // 按月
f("订单日期", { granularity: Granularity.DAY })     // 按天
```

可用值：`NONE`, `YEAR`, `QUARTER`, `MONTH`, `WEEK`, `DAYOFWEEK`, `DAY`, `HOUR`, `MINUTE`, `SECOND`

### 卡片级计算字段

使用 `calcField()` 在卡片指标区创建公式计算字段（不依赖 ETL 预计算）：

```javascript
.addMetric(calcField("利润率", "sum([Profit])/sum([Sales])"))
.addMetric(calcField("客单价", "[Sales]/[Quantity]", { calculationType: "normal" }))
.addMetric(calcField("发货天数", "datediff([Ship Date],[Order Date])"))
```

**公式语法**：formula 中用 `[字段名]` 引用数据集字段。公式本质上是 **SQL 表达式**，支持的函数取决于底层数据引擎：
- **上传的 Excel/CSV 或抽取数据集** → 使用 **Apache Spark 3.5 SQL** 语法（支持 `datediff`、`case when`、`if`、`concat`、窗口函数等）
- **数据库直连数据集** → 使用**目标数据库自身的 SQL** 语法（如 MySQL、PostgreSQL、ClickHouse 等）

> **重要**：`schema.js` 中的 `displayType` 是生成 `calcField()` 公式时的 SQL 方言事实源。数据库直连数据集会把公式下推到目标库执行，不能把平台聚合枚举或伪函数直接写进公式。例如 PostgreSQL 去重计数应写 `COUNT(DISTINCT [客户ID])`，不要写 `COUNT_DISTINCT([客户ID])`；如果只是单独统计去重人数，应改用 `f("客户ID", { aggrType: AggrType.COUNT_DISTINCT })`。

`calcField(name, formula, opts?)` 参数：
- `name`：字段显示名
- `formula`：SQL 表达式，用 `[字段名]` 引用数据集字段
- `opts.calculationType`：`"aggregation"`（默认）, `"normal"`, `"window"`（窗口计算）
- `opts.fdType`：默认 `"DOUBLE"`，可改为 `"LONG"`、`"STRING"` 等
- `opts.numberFormat` / `opts.alias`：同 `field()` overrides
- `opts.advCalc` / `opts.fieldFormat` / `opts.aggrType`：需要还原同环比、占比、表格指标格式等高级 zoneData 时可显式传入，导出器会原样透传到 card meta

**calculationType 选择**：
- `"aggregation"`（默认）— 公式**必须**包含聚合函数（如 `SUM([Profit])/SUM([Sales])`），否则后端报 `MISSING_AGGREGATION` 错误
- `"normal"` — 明细级公式，不含聚合函数（如 `datediff([Ship Date],[Order Date])`），适用于明细表或作为其他聚合的输入
- `"window"` — 窗口计算公式（如 `sum([Sales]) over(partition by [Category])`），用于排名、累计等

> **明细表限制**：`DETAIL_TABLE` / `SCROLL_TABLE` 只支持逐行明细展示，卡片级 `calcField()` 必须显式使用 `{ calculationType: "normal" }`，且公式中不要写 `SUM`/`COUNT(DISTINCT ...)`/`GROUP_CONCAT`/`STRING_AGG` 等聚合或窗口计算。需要汇总时，改用非明细图表的原生指标 `aggrType`；复杂聚合用非明细图表的 `aggregation` calcField，或在 ETL / 数据集计算字段中预计算。本地校验只稳定拦截 `aggregation`/`window` 类型和明显 `OVER(...)` 窗口子句，不维护跨 SQL 方言聚合函数名单。

> **常见错误**：`calcField("利润率", "[利润]/[销售额]")` 使用默认 `calculationType: "aggregation"` 但公式中没有聚合函数，会导致 `MISSING_AGGREGATION` 错误。正确写法是 `calcField("利润率", "SUM([利润])/SUM([销售额])")` 或改为 `{ calculationType: "normal" }`。

### 同环比高级计算

优先使用 BI 原生高级计算 builder，不要用 `calcField()` 手拼同比/环比公式。当前锁定的 MVP 范围对应界面「高级计算 → 同比/环比」里的以下设置：
- 时间类型：日环比、周同比、月同比、季同比、年同比、年同比(按周)
- 期末值：上月末、上季度末、上年末
- 自定义：后移 1 个月
- 输出值：增长值、增长率、对比值、本期/对比期（内置自定义公式预设）
- 增长率类型：普通增长率、绝对增长率

默认规则：同比、环比、同环比、年同比、月环比等语义未指定输出值时默认生成增长率；未指定模式时默认生成日期筛选模式（`ComparativeMode.FILTER_BASED`），保证页面日期筛选器联动生效。需要普通模式时显式传 `{ mode: ComparativeMode.NORMAL }`；需要增长值或对比值时显式传 `ComparativeOutput.GROWTH_VALUE` / `ComparativeOutput.COMPARE_VALUE`。

预聚合周期字段（例如数据集中已经按周产出的 `周开始日期`、按月产出的 `月开始日期`）不能按默认 DAY 筛选窗口计算。使用这类字段做周环比/月环比时，把日期字段声明为 `Granularity.NONE`，builder 会自动生成不带筛选窗口和 `mode` 的同环比：

```javascript
var weekStart = f("周开始日期", { granularity: Granularity.NONE });

createCard(ChartType.PIVOT_TABLE, "周报")
    .bindDataset(DS)
    .addRow(weekStart)
    .addMetric(f("GMV", {
        alias: "GMV周环比",
        aggrType: AggrType.SUM,
        advCalc: comparative.weekOverWeek(weekStart)
    }));
```

示例：

```javascript
var dateField = f("订单日期");

createCard(ChartType.PIVOT_TABLE, "销售同环比")
    .bindDataset(DS)
    .addRow(dateField)
    .addMetric(f("销售额", {
        alias: "年同比增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYear(dateField)
    }))
    .addMetric(f("销售额", {
        alias: "年同比绝对增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYear(dateField, ComparativeOutput.GROWTH_RATE, {
            growthRateType: GrowthRateType.ABS
        })
    }))
    .addMetric(f("销售额", {
        alias: "月同比对比值",
        aggrType: AggrType.SUM,
        advCalc: comparative.monthOverMonth(dateField, ComparativeOutput.COMPARE_VALUE)
    }))
    .addMetric(f("销售额", {
        alias: "本期除以去年同期",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYear(dateField, ComparativeOutput.CURRENT_OVER_COMPARE)
    }))
    .addMetric(f("销售额", {
        alias: "上月末增长值",
        aggrType: AggrType.SUM,
        advCalc: comparative.periodEnd(dateField, ComparativePeriodEnd.MONTH_END, ComparativeOutput.GROWTH_VALUE)
    }))
    .addMetric(f("销售额", {
        alias: "月同比普通模式增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.monthOverMonth(dateField, {
            mode: ComparativeMode.NORMAL
        })
    }));
```

KPI 指标卡的 compare 区也支持同环比高级计算：

```javascript
var dateField = f("订单日期");

createCard(ChartType.KPI_CARD, "销售额 KPI")
    .bindDataset(DS)
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
    .addCompare(f("销售额", {
        alias: "年同比增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYear(dateField)
    }));
```

常用枚举：
- `ComparativeOutput.GROWTH_VALUE`：增长值
- `ComparativeOutput.GROWTH_RATE`：增长率
- `ComparativeOutput.COMPARE_VALUE`：对比值
- `ComparativeOutput.CURRENT_OVER_COMPARE`：本期 / 对比期，底层生成 `valueType: "CUSTOM"` 与公式 `[orig]/[shifted]`
- `GrowthRateType.NORMAL`：普通增长率，默认值
- `GrowthRateType.ABS`：绝对增长率
- `ComparativeMode.FILTER_BASED`：日期筛选模式，默认值，用于复现前端「对比」槽位 + 日期筛选的高级计算
- `ComparativeMode.NORMAL`：普通模式，只有明确不需要页面日期筛选器联动时使用
- `ComparativePeriodEnd.MONTH_END` / `QUARTER_END` / `YEAR_END`：期末值

### 累计高级计算

优先使用 BI 原生累计高级计算 builder，不要用 `calcField()` 手拼窗口累计公式。当前范围对应界面「高级计算 → 累计计算」，输出 `advType: "RUNNING_TOTAL"`。

示例：

```javascript
var orderDate = f("订单日期");
var region = f("地区");
var province = f("省/自治区");
var category = f("类别");

createCard(ChartType.PIVOT_TABLE, "销售累计")
    .bindDataset(DS)
    .addRow(orderDate)
    .addRow(region)
    .addRow(province)
    .addColumn(category)
    .addMetric(f("销售额", {
        alias: "按列累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byColumn()
    }))
    .addMetric(f("销售额", {
        alias: "按行累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byRow()
    }))
    .addMetric(f("销售额", {
        alias: "地区组内累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byField(region)
    }))
    .addMetric(f("销售额", {
        alias: "订单日期月累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderDate, RunningTotalGranularity.MONTH)
    }));
```

常用 API：
- `runningTotal.byColumn()`：按列累计，生成 `calcRangeType: "COLUMN"`
- `runningTotal.byRow()`：按行累计，生成 `calcRangeType: "ROW"`
- `runningTotal.byField(field)`：按非日期维度字段累计，`field` 必须已在行/列区域
- `runningTotal.byDateField(field, granularity)`：按日期字段累计，`field` 必须已在行/列区域且为 `DATE` / `TIMESTAMP` / `SUB_DATE`

常用枚举：
- `RunningTotalGranularity.DAY`：日累计
- `RunningTotalGranularity.WEEK`：周累计
- `RunningTotalGranularity.MONTH`：月累计
- `RunningTotalGranularity.QUARTER`：季度累计
- `RunningTotalGranularity.YEAR`：当年累计
- `RunningTotalGranularity.ALL_YEARS` / `RunningTotalGranularity.NONE`：历年累计

约束：
- 仅支持表格/透视表类图表，这是 guanvis MVP 限制，不是 BI 原生能力上限。
- 至少需要一个行/列维度；历史 BI payload 中存在无维度累计，但 guanvis 当前不新建。
- 日期累计必须用 `byDateField()`；`byField(dateField)` 会报错。
- 最后一个日期维度不能选择自身最细粒度。例如最后一个 `DAY` 日期不能选 `DAY`，最后一个 `MONTH` 子日期不能选 `MONTH`。如果该日期字段后面还有可选维度，则可以选择自身最细粒度。
- `advValue.aggrType` 固定输出 `SUM`。后端存在更底层能力，但原生累计菜单固定写 `SUM`。
- 指标自身 `aggrType` 也必须是 `AggrType.SUM`；当前 MVP 不生成“外层 AVG、累计内部 SUM”的混合 payload。

### 排名高级计算

优先使用 BI 原生排名高级计算 builder，不要用 `calcField()` 手拼窗口函数。当前范围对应界面「高级计算 → 排名」：
- 排名范围：按列、按行、维度组内、维度项
- 排名方式：`RANK`、`DENSE_RANK`、`ROW_NUMBER`
- 顺序：从高到低、从低到高
- Top N：全部数据、自定义条数；条数范围 1-100，当前只支持 `COUNT`

示例：

```javascript
var region = f("大区");
var year = f("年");

createCard(ChartType.PIVOT_TABLE, "销售排名")
    .bindDataset(DS)
    .addRow(region)
    .addRow(f("省份"))
    .addColumn(year)
    .addMetric(f("销售额", {
        alias: "按列排名",
        aggrType: AggrType.SUM,
        advCalc: rank.byColumn({
            rankType: RankType.RANK,
            order: SortOrder.DESC
        })
    }))
    .addMetric(f("销售额", {
        alias: "大区组内排名",
        aggrType: AggrType.SUM,
        advCalc: rank.byField(region, {
            rankType: RankType.DENSE_RANK,
            order: SortOrder.ASC
        })
    }))
    .addMetric(f("销售额", {
        alias: "年份维度项 Top5",
        aggrType: AggrType.SUM,
        advCalc: rank.byDimensionItem(year, {
            rankType: RankType.ROW_NUMBER,
            order: SortOrder.DESC,
            topN: rank.topN(5, { applyToSubtotal: false })
        })
    }));
```

常用 API：
- `rank.byColumn(opts)`：按列排名，生成 `calDimension: "COLUMN"`
- `rank.byRow(opts)`：按行排名，生成 `calDimension: "ROW"`
- `rank.byField(field, opts)`：维度组内排名，`field` 必须已在行/列区域
- `rank.byDimensionItem(field, opts)`：维度项排名，`field` 必须已在行/列区域；行/列区域至少需要两个维度，否则 builder 会拒绝导出，避免 BI 降级为行/列排名
- `rank.topN(count, { applyToSubtotal })`：自定义 Top N，`count` 为 1-100 整数，`applyToSubtotal` 默认 true
- `rank.all()`：全部数据，等价于默认 TopN 配置

常用枚举：
- `RankType.RANK`：重复排名，后续名次跳号
- `RankType.DENSE_RANK`：重复排名，后续名次连续
- `RankType.ROW_NUMBER`：不并列，逐行连续编号
- `SortOrder.DESC` / `SortOrder.ASC`：从高到低 / 从低到高；builder 会写出 BI 需要的 `desc` / `asc`

### 占比高级计算

优先使用 BI 原生占比高级计算 builder，不要用 `calcField()` 手拼窗口函数。当前范围对应界面「高级计算 → 占比」：
- 按列：`measureOnDimRow: true`
- 按行：`measureOnDimRow: false`；真实 UI 只在存在列维度时展示该选项
- 指定维度：目标字段必须在行/列区域，且不能是该轴最后一个非 MPH 维度
- 支持表格行/列结构图表；`DETAIL_TABLE` 没有可用于占比上下文的行/列层级，不支持原生占比高级计算
- 默认数据格式：若未显式配置格式，builder 自动补百分比格式、保留 2 位小数

示例：

```javascript
var region = f("大区");
var province = f("省份");
var category = f("类别");
var subcategory = f("子类别");

createCard(ChartType.PIVOT_TABLE, "销售占比")
    .bindDataset(DS)
    .addRow(region)
    .addRow(province)
    .addColumn(category)
    .addColumn(subcategory)
    .addMetric(f("销售额", {
        alias: "按列占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byColumn()
    }))
    .addMetric(f("销售额", {
        alias: "按行占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byRow()
    }))
    .addMetric(f("销售额", {
        alias: "大区层级占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byField(region)
    }))
    .addMetric(f("销售额", {
        alias: "类别层级占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byField(category)
    }));
```

常用 API：
- `percentage.byColumn()`：按列占比，生成 `measureOnDimRow: true`
- `percentage.byRow()`：按行占比，生成 `measureOnDimRow: false`
- `percentage.byField(field, opts)`：按指定维度层级占比；builder 会在卡片 zone 上下文中根据字段属于 row/column 回填 `measureOnDimRow`
  - 同一个字段同时出现在行、列区域时，用 `opts.axis: "row" | "column"` 显式指定轴向，例如 `percentage.byField(region, { axis: "column" })`
  - 日期维度带粒度时直接传同一个 field 引用，例如 `var month = f("日期", { granularity: Granularity.MONTH })`，builder 会写出 BI zone 中的粒度字段 ID

支持聚合类型：`SUM`、`CNT`、`MAX`、`MIN`、`AVG`、`CNT_DISTINCT`、`NUL`。JS DSL 中 `NUL` 对应 `AggrType.FIRST_NOT_NULL`，没有 `AggrType.NUL` 这个枚举名；如果后端环境已移除 `NUL` 支持，以目标环境实际 `AggrType.percentSupportedTypes` 为准。

**常用 Spark SQL 函数示例**（适用于 Excel/CSV 数据集）：
```javascript
// 日期差
calcField("发货天数", "datediff([Ship Date],[Order Date])")
// 条件判断
calcField("Ship Status", "case when datediff([Ship Date],[Order Date]) > 6 then 'Late' else 'On Time' end", { fdType: "STRING" })
// 字符串拼接
calcField("全名", "concat([First Name], ' ', [Last Name])", { fdType: "STRING" })
// 窗口函数
calcField("类别销售占比", "sum([Sales]) over(partition by [Category])", { calculationType: "window" })
```

**高级 zoneData 透传**：当要还原精品应用里的同环比、自定义排序、特殊字段格式时，不要手工 patch zip，直接把这些字段放在 `field()` / `calcField()` 的 overrides 中：

```javascript
var yoyRate = calcField("同比", "SUM([销售额])", {
    aggrType: AggrType.FIRST_NOT_NULL,
    advCalc: {
        advType: "COMPARATIVE",
        advValue: {
            advType: "COMPARATIVE",
            dateFdId: "date_fd",
            valueType: "RATE",
            offset: 1,
            offsetType: "YEAR",
            granularity: "DAY",
            mode: "FILTER_BASED"
        }
    },
    fieldFormat: {
        numberFormat: { formatType: "PERCENTAGE", decimalPlaces: 2 }
    }
});

createCard(ChartType.PIVOT_TABLE, "品牌同比分析")
    .bindDataset(DS)
    .addRow(f("品牌"))
    .addMetric(yoyRate)
    .addSort(f("品牌", {
        ordering: "ASC",
        customSort: {
            turnedOn: true,
            sortOrder: ["华东", "华南", "华北"]
        }
    }));
```

### 卡片级筛选器 (Filters Zone)

通过 `.addFilter()` 在卡片上添加固定筛选条件，有三种写法：

```javascript
// 写法1: filterField() 工厂函数（推荐，最简洁）
.addFilter(filterField(DS, "地区", FilterType.IN, ["华东", "华北"]))
.addFilter(filterField(DS, "销售额", FilterType.GT, ["10000"]))

// 写法2: addFilter 三参数快捷语法
.addFilter(field(DS, "地区"), FilterType.IN, ["华东", "华北"])

// 写法3: 对象语法（需要 filterLevel 时）
.addFilter(filterField(DS, "订单日期", FilterType.BT, ["2024-01-01", "2024-12-31"], { filterLevel: FilterLevel.AGGREGATION }))
```

`filterField(dsId, fieldName, filterType, filterValue?, opts?)` — 与 `field()` 和 `calcField()` 模式一致。

枚举 `FilterType`：`IN`, `NOT_IN`, `GT`, `GE`, `LT`, `LE`, `EQ`, `NE`, `BT`（区间）, `CONTAINS`, `NOT_CONTAINS`, `STARTSWITH`, `ENDSWITH`, `IS_NULL`, `NOT_NULL`

枚举 `FilterLevel`：`DETAIL`（明细筛选，默认）, `AGGREGATION`（聚合筛选）, `RESULT`（结果筛选）
