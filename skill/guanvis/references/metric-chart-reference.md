# 指标平台指标卡片（MetricChart）创建指引

本指引用于创建“用指标平台已有指标创建的卡片”，后端类型为 `CARD_TYPE.METRIC_CHART` / `cdType=13`。它不同于普通数据集字段的 `SINGLE_VALUE` / `KPI_CARD`。

## 固定流程

1. 查询指标 ID：

```bash
guancli metric search '销售额年同比增长率'
```

`guancli metric search --name-like ...` 不是当前 CLI 参数；搜索词用位置参数。

2. 生成指标快照：

```bash
guanvis metric-init <metricId1> <metricId2> -d ./my_dashboard/
```

3. 编写 `card_*.js`：

```javascript
var card = createMetricChart(ChartType.PIVOT_TABLE, "销售指标分析")
    .setId("card12345678901234567890")
    .addRow(metricDim("销售额", "区域"))
    .addMetric(metric("销售额"));

registerMetricChart(card.build());
```

4. 本地验证用 `guanvis preview/pack`。发布后若 `guancli card get/preview` 对 `METRIC_CHART` 报 `None.get`，不要据此判断卡片失败；优先使用指标卡编辑态数据接口或页面访问验证数据返回。

## 兼容约束

- `MetricChartMeta.defaultView` 不要写 `"chart"`；后端 `ChartView` 不包含该值，导入后查询会报 `ChartView does not contain 'chart'`。
- `PIVOT_TABLE` 的 `column` 区域必须包含 `metaType: "MPH"` 的“度量名”占位列。guanvis 会在未显式添加 column 时自动补齐。
- `PIVOT_TABLE` 的 `metric` / `sorting` zoneInfo 需要 `needAggregation: true`；普通维度、筛选 zone 不聚合。
- 指标字段使用 `id` 表示 metric id；维度字段使用 `fdId` + `dsId` / `publicDimensionId`。不要把 metric id 当普通数据集 `fdId` 使用。
- `preview` / `pack` / `publish` 会像普通数据集卡片一样给 MetricChart 注入主题视觉配置，只写 `settings` 与 `meta.chartMain.props`，不会修改 `zoneData`、`dsInfo`、`defaultView`。显式通过 `.setProps()` / `.setTableSetting()` / `.setAxis()` 等写入的配置优先保留。

## 顶层内容参数

| 路径 | 中文含义 | 说明 |
|---|---|---|
| `chartType` | 图表类型 | 使用 `ChartType.PIVOT_TABLE`、`BASIC_COLUMN`、`BASIC_LINE` 等枚举 |
| `metricIds` | 卡片引用的指标 ID 列表 | 由 `.addMetric(metric(...))` 自动收集；后端用它维护 card-metric 关系 |
| `metrics` | 指标详情列表 | 后端编辑态会补充；资源包创建通常不手写 |
| `columns` | 卡片级字段列表 | 指标卡片临时/动态字段可放这里；默认空数组 |
| `meta.chartMain.zoneInfo` | 区域规格 | 描述 row/column/metric/filter/sort 等区域的标题、数量限制、是否聚合 |
| `meta.chartMain.zoneData` | 区域字段 | 真实拖入的维度、指标、筛选、排序等字段 |
| `meta.chartMain.props` | 图表属性 | 透视表设置、图例、数据标签、坐标轴、主题色、辅助线等 |
| `meta.chartMain.config` | 图表配置 | 汇总阈值、自由钻取、KPI 趋势默认值等 |
| `meta.chartMain.dynamicZoneInfo` | 动态字段配置 | 动态维度/指标映射；复杂场景可通过 `.setRawConfig` / `.setProps` 透传 |
| `meta.summary` | 汇总配置 | 汇总字段、标签、位置和汇总类型 |
| `hasDrill` / `drillViews` | 钻取配置 | 是否有钻取与钻取路径；普通创建可先不写 |

## zoneData 区域

| 区域 | 中文 | 可放字段 | 常见用途 |
|---|---|---|---|
| `row` | 维度/行 | 公共维度、适用维度、动态维度、MPH | 分组维度、X 轴、透视表行 |
| `column` | 对比/列 | 公共维度、适用维度、动态维度、MPH | 透视表列、系列拆分；透视表默认需要 MPH |
| `metric` | 数值 | 指标字段 | 主指标 |
| `metric_additional` | 副轴数值 | 指标字段 | 组合图副轴、双轴图 |
| `colorBy` | 颜色 | 指标字段 | 数值渐变着色 |
| `sizeBy` | 大小 | 指标字段 | 气泡大小 |
| `tooltip` | 更多提示 | 指标字段 | tooltip 附加指标 |
| `filters` | 筛选 | 维度或指标 | 明细筛选、聚合筛选、结果筛选 |
| `sorting` | 排序 | 维度或指标 | 升序/降序、自定义排序 |
| `split` | 拆分 | 公共维度 | 小多图拆分 |
| `ignoreFilters` | 忽略筛选 | 筛选字段 | 忽略外部联动筛选 |

## 字段参数

### 维度字段（DimensionZoneObj）

| 参数 | 中文含义 |
|---|---|
| `dsId` | 数据集 ID |
| `fdId` | 字段 ID |
| `name` / `alias` | 字段名 / 显示别名 |
| `fdType` | 字段类型，如 `STRING`、`DATE`、`LONG` |
| `metaType` | 元类型，维度为 `DIM`，度量名占位为 `MPH` |
| `granularity` / `parentFdName` | 日期粒度 / 原日期字段名 |
| `formula` | 卡片级字段公式 |
| `consolidation` | 公共维度归并信息 |
| `alignedDimension` | 指标 level 计算字段的对齐维度 |
| `baseFdType` / `timeFormat` | 技术字段类型 / 字符串时间解析格式 |
| `fieldFormat.numberFormat` | 数值格式 |
| `fieldFormat.headerFormat` | 表头格式 |
| `fieldFormat.conditionFormat` | 条件格式 |
| `fieldFormat.linkFormat` | 链接格式 |
| `hasSubTotal` | 是否显示小计 |
| `key` | 前端字段实例 key；guanvis 自动生成 |
| `subZoneId` / `dzId` | 子区域 ID / 动态字段 ID |
| `publicDimensionId` | 公共维度 ID |
| `isDrill` | 是否为自由钻取字段 |
| `annotation` | 字段释义 |
| `isHidden` | 是否隐藏 |

### 指标字段（MetricZoneObj）

| 参数 | 中文含义 |
|---|---|
| `id` | 指标 ID |
| `name` / `alias` | 指标名 / 显示别名 |
| `fdType` | 值类型 |
| `metaType` | 固定为 `METRIC` |
| `fieldFormat.numberFormat` | 数据格式 |
| `fieldFormat.conditionFormat` | 条件格式 |
| `fieldFormat.headerFormat` | 表头格式 |
| `fieldFormat.itemSetting` | 颜色/项目设置，常用于 `colorBy` |
| `subtotalSetting.isDisplayed` | 小计/总计是否显示 |
| `subtotalSetting.isAggrDsBased` | 小计是否基于聚合数据集 |
| `subtotalSetting.aggrType` | 小计聚合方式 |
| `advCalc` | 高级计算，如排名、占比 |
| `filter` | 指标业务限定 |
| `miniChart` | 表格内迷你图 |
| `formula` / `formulaField` | 复合/原子拆分公式 |
| `parentFdName` / `granularity` | 日期派生字段信息 |
| `key` / `subZoneId` / `dzId` | 字段实例 key / 子区域 / 动态字段 |
| `isDrill` | 是否钻取字段 |
| `isHidden` | 是否隐藏 |

### 筛选字段（FilterZoneObj）

| 参数 | 中文含义 |
|---|---|
| `id` | 指标 ID；当筛选指标时使用 |
| `dsId` / `fdId` | 数据集 ID / 字段 ID；当筛选维度时使用 |
| `filterType` | 筛选类型，如 `IN`、`NI`、`GT`、`GE`、`LT`、`LE`、`EQ`、`NE`、`BT` |
| `filterValue` | 筛选值数组；`BT` 需要两个值 |
| `filterLevel` | 筛选层级：`DETAIL` 明细、`AGGREGATION` 聚合、`RESULT` 结果 |
| `fieldFilterSettings` | 字段筛选器设置 |
| `compareColumn` | 是否对比列 |
| `advFilter` / `advFilterContent` | 高级筛选表达式及内容 |
| `refKey` | 关联来源 metric 字段 key，用于带业务限定指标筛选 |

### 排序字段（SortingZoneObj）

| 参数 | 中文含义 |
|---|---|
| `id` | 指标 ID；指标排序时使用 |
| `dsId` / `fdId` | 维度字段来源 |
| `ordering` | 排序方向：`ASC` / `DESC` |
| `customSort.turnedOn` | 是否启用自定义排序 |
| `customSort.sortOrder` | 自定义排序值列表 |
| `isPinYinOrder` | 是否按拼音排序 |
| `associateFieldSorting` | 关联字段排序 |
| `advCalc` | 按高级计算结果排序 |
| `refKey` | 关联来源 metric 字段 key |

## DSL 方法

| 方法 | 中文含义 |
|---|---|
| `createMetricChart(chartType, name)` | 创建指标卡片 |
| `.addMetric(metric(...))` | 添加主指标 |
| `.addMetricAdditional(metric(...))` | 添加副轴指标 |
| `.addRow(metricDim(...))` | 添加行/类目维度 |
| `.addColumn(metricDim(...))` | 添加列/对比维度 |
| `.addFilter(field, type, values)` | 添加筛选 |
| `.addSort(field)` | 添加排序 |
| `.addColorBy(metric(...))` | 添加颜色指标 |
| `.addSize(metric(...))` | 添加大小指标 |
| `.addTooltip(metric(...))` | 添加 tooltip 指标 |
| `.addSplit(metricDim(...))` | 添加拆分维度 |
| `.setProps(obj)` / `.setRawProps(key, value)` | 设置 `chartMain.props` |
| `.setConfig(obj)` / `.setRawConfig(key, value)` | 设置 `chartMain.config` |
| `.setSummary(obj)` | 设置 `meta.summary` |
| `.setColumns(columns)` | 设置 `content.columns` 与 dsInfo.columns |
| `.setTableSetting(obj)` | 设置 `props.miscPivotTableSetting` |
| `.setFreeDrill(enabled, position)` | 设置 `config.freeDrillConfig` |
| `.setRowThreshold(thresholds)` | 设置 `config.rowThreshold` |

复杂配置可直接放到 `metric()` / `metricDim()` 的 overrides 中：

```javascript
var card = createMetricChart(ChartType.PIVOT_TABLE, "复杂指标透视表")
    .addRow(metricDim("销售额", "区域", {
        hasSubTotal: true,
        fieldFormat: { headerFormat: { alignment: "center" } }
    }))
    .addMetric(metric("销售额", {
        alias: "销售额",
        subtotalSetting: { isDisplayed: true, isAggrDsBased: true, aggrType: "SUM" },
        fieldFormat: { numberFormat: NumberFormat.currency("¥", 0) }
    }))
    .addSort(metric("销售额", { ordering: SortOrder.DESC }))
    .setTableSetting({ fixedHeaderInfo: { X: false }, isDefaultExpandedGroupedTable: true, defaultExpandCols: 0 })
    .setConfig({ rowThreshold: [] });

registerMetricChart(card.build());
```
