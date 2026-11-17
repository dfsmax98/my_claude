## 验证规则

pack/publish 时分两层自动检查：

### JS 层（脚本执行时，面向 AI 生成的脚本质量）

- **数据集绑定**：是否调用了 `.bindDataset()`，dsId 是否在 `defineDataset()` 中注册
- **Zone 配置**：必填 zone 是否有字段、字段数量是否超过 maxCount、是否使用了不支持的 zone
- **字段完整性**：fdId/name 非空、fdType 合法（FieldType 枚举）、field() 引用的字段名是否存在
- **聚合类型**：metric/compare/target zone 中非明细表图表必须有 aggrType；aggrType 值必须合法（AggrType 枚举）
- **明细表计算字段**：`DETAIL_TABLE` / `SCROLL_TABLE` 禁止 `calculationType: "aggregation"` / `"window"` 的 `calcField()`，并拦截明显的 `OVER(...)` 窗口子句；明细表只做行级展示，行级公式使用 `{ calculationType: "normal" }`，聚合需求优先改用非明细图表的原生指标 `aggrType`，复杂聚合改用非明细图表的 aggregation calcField 或 ETL 预计算。跨方言 SQL 聚合函数由 skill 生成规范约束，不在本地校验中维护函数名白/黑名单
- **排序**：sorting zone 中 sortType 必须是 ASC/DESC（使用 SortOrder 枚举）
- **重复检测**：同一 zone 中相同 fdId+alias+aggrType 组合会产生 warning
- **空卡片**：没有任何字段的卡片会报错
- **Page 布局**：cardIndex 越界、宽度超限（非精细 1-12，精细导出后 1-60）、溢出检测

### Go 层（payload 生成后，面向后端导入兼容性）

- **结构完整性**：chartType 非空、dsId 非空、dsInfo 非空且含 dsId/columns、meta JSON 合法
- **meta 结构**：chartMain/summary 存在、zoneData/zoneInfo 中 zoneId 合法
- **字段合法性**：fdType/aggrType 值合法、metric zone 字段有 aggrType
- **Page 关联**：layout 中 card ID 引用合法、pageCardRels 引用合法
- **筛选器**：cdType=6 的卡片跳过 chartType/chartMain 检查，验证 source.field 存在

### column zone 与 colorBy zone 的区别

**column zone**（`.addColumn()`）：接受**维度字段**，用于按维度分组着色。例如"按邮寄方式分组堆叠"：

```javascript
createCard(ChartType.STACKED_COLUMN, "类别销售额")
    .addRow(f("类别"))
    .addColumn(f("邮寄方式"))  // 维度分组 → 每种邮寄方式一个颜色
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
```

**colorBy zone**（`.addColorBy()`）：接受**指标字段**，用于按指标值渐变着色。例如"按利润值深浅着色"：

```javascript
createCard(ChartType.BASIC_COLUMN, "类别销售额")
    .addRow(f("类别"))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
    .addColorBy(f("利润", { aggrType: AggrType.SUM }))  // 指标值 → 颜色深浅
```

支持 column zone 的图表：`STACKED_COLUMN`、`GROUPED_COLUMN`、`GROUPED_BAR`、`STACKED_BAR`、`MULTI_LINE`、`STACKED_AREA` 等多指标图表。`BASIC_COLUMN`、`BASIC_BAR`、`BASIC_LINE`、`PIE` 不支持 column zone。

### 特殊图表行为

- **DETAIL_TABLE / SCROLL_TABLE**：`.addColumn()` 自动重定向到 metric zone；metric/sorting zone 的 `needAggregation` 设为 false；不自动添加 aggrType
- **PIVOT_TABLE**：支持 row（行维度）+ column（列维度）+ metric（值）交叉分析
- **BASIC_MAP / WORLD_MAP**：地理维度字段放 `row` zone（1 个），指标放 `colorBy`（渐变着色）或 `metric` zone。后端验证规则：`rowSize == 1 && (colorBySize == 1 || metricSize == 1)`。**不要用** `addLocation()`（已废弃）
- **POINT_MAP / BUBBLE_MAP**：`row` zone 放地名维度（1 个），`metric` zone 放数值指标（POINT_MAP 最多 20 个，BUBBLE_MAP 无限制）。后端验证规则：`rowSize == 1 && metricSize >= 1`

### 图表类型 Zone 配置速查表

`-1` 或 `∞` 表示不限数量。**必填** zone 标记 `*`。省略的 zone（filters/sorting/tooltip）所有图表都支持。

| ChartType | metric | row | column | colorBy | 其他 | 典型场景 |
|---|---|---|---|---|---|---|
| BASIC_COLUMN/BAR/LINE | 1* | ∞ | - | 1 | split(1) | 单指标柱/条/折线 |
| GROUPED_COLUMN/BAR | ∞* | ∞ | 1 | 1 | split(1) | 多指标分组柱/条 |
| STACKED_COLUMN/BAR | ∞* | ∞ | 1 | 1 | split(1) | 堆叠柱/条 |
| MULTI_LINE | ∞* | ∞ | 1 | 1 | split(1) | 多指标折线 |
| *_WITH_LINE (组合图) | ∞* | **1** | 1 | 1 | metricAdditional(20), split(1) | 柱+线组合。metric=柱形(主轴)，metricAdditional=折线(副轴) |
| PIE / TREE_MAP | 1* | ∞ | - | 1 | - | 饼图/矩形树图 |
| KPI_CARD | 1* | - | - | - | compare(∞) | 单指标 KPI |
| PIVOT_TABLE | 124* | ∞ | ∞ | - | - | 交叉表 |
| DETAIL_TABLE | ∞* | - | - | - | - | 明细表 |
| SCROLL_TABLE | ∞* | ∞ | - | - | - | 滚动表 |
| BASIC_SCATTER_PLOT | 2* | 1 | - | 1 | sizeBy(1) | 散点图（X/Y 两个 metric） |
| BASIC_MAP | 1 | 1* | - | 1 | - | 中国地图（row 放地理维度） |
| FUNNEL | ∞* | 1 | - | - | - | 漏斗 |
| PROGRESS_BAR | 2* | 0-1 | - | - | - | 进度条，默认用两个 metric（当前值/目标值） |
| HEAT_MAP | 1* | 1* | 1* | - | - | 热力图（row+column+metric 都必填） |
| RADAR_LINE | ∞* | 1 | - | 1 | - | 雷达图 |
| SANKEY | 1 | ∞* | - | - | - | 桑基图 |

### 图表选型补充（非通识部分）

以下仅列出观远 BI 特有的、容易选错的图表区分规则：

| 场景 | 正确选择 | 避免混淆 |
|------|---------|---------|
| KPI 只展示一个数字 | `SINGLE_VALUE` | 不要用 `KPI_CARD` |
| KPI 需要同环比对比 | `KPI_CARD`（有 compare zone） | `SINGLE_VALUE` 无 compare zone |
| 折线图只有 1 个指标 | `BASIC_LINE` | 不要用 `MULTI_LINE` |
| 折线图有 2+ 指标 | `MULTI_LINE` | 不要用 `BASIC_LINE`（仅支持 1 metric + colorBy 拆分） |
| 明细逐行展示（不聚合） | `DETAIL_TABLE` | `PIVOT_TABLE` 会聚合 |
| 行列交叉汇总 | `PIVOT_TABLE`（有 row + column + metric 三个 zone） | `DETAIL_TABLE` 无 column zone |
| 按维度分组着色（如按地区着色） | 使用 `.addColumn(f("地区"))` | **不要用** `.addColorBy()`，colorBy 是按指标值渐变着色 |
| 分组+组成双维度对比 | `STACKED_SPLIT_COLUMN` | `GROUPED_COLUMN` 无堆积、`STACKED_COLUMN` 无分组 |
| 柱线组合图（主轴柱形+副轴折线） | `GROUPED_COLUMN_WITH_LINE`（metric=柱, metricAdditional=线） | 不要把所有指标都放 metric，副轴指标用 `.addMetricAdditional()` |
| 目标达成率 | `BULLET_COLUMN` / `BULLET_BAR` | 不要用普通柱形图叠加辅助线 |
| 占比分析类别 >5 | `TREE_MAP` 或 `RISING_SUN` | `PIE` 限 2-5 个分类，否则难以辨读 |
| 完成度/进度展示 | `KPI_CARD` + 数值格式 | `SOLID_GAUGE` 占空间大但信息密度低，优先用指标卡 |
| 中国省/市级地图 | `BASIC_MAP`（内置 Highmaps） | **不要用自定义图表**，内置地图自带 GeoJSON、地名编码匹配 |
| 全球国家级地图 | `WORLD_MAP`（内置 Highmaps） | 同上 |
| 标记地图（地名+多指标） | `POINT_MAP`（标记）或 `BUBBLE_MAP`（气泡） | row zone 放 1 个地名维度，metric zone 放多个指标 |
| 美国各州/加拿大等非中国区域详细地图 | 自定义图表（Vega-Lite geoshape） | 内置 `WORLD_MAP` 只精确到国家级，州/省级需自定义 |

### 拆分图（Trellis/Facet）

将一个图表按维度值拆分成多个小图表并排展示。使用 `addSplit(field)` 指定拆分维度，可选 `setSplitSetting` 控制行列数：

```javascript
var card = createCard(ChartType.STACKED_AREA, "各类别月销售趋势")
    .bindDataset(DS)
    .addRow(f("订单日期", { granularity: "MONTH" }))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }))
    .addSplit(f("产品类别"))
    .setSplitSetting({ rows: 2, columns: 3 });
```

不调用 `setSplitSetting` 时默认 3 行 3 列。支持拆分的图表类型：`BASIC_COLUMN`、`BASIC_BAR`、`BASIC_LINE`、`STACKED_AREA`、`GROUPED_COLUMN`、`STACKED_COLUMN`、`MULTI_LINE` 等所有带 split zone 的图表。

### 地图图表用法

**BASIC_MAP（中国行政地图）**：内置 Highmaps，自动加载中国省市 GeoJSON。地理维度字段放 `row` zone，指标放 `colorBy`（渐变着色）或 `metric` zone。BI 后端通过 `GeoCodeUtil` 自动将地名（如"北京市""浙江省"）映射为行政区编码。

```javascript
var card = createCard(ChartType.BASIC_MAP, "各省利润率")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addColorBy(calcField("利润率", "SUM([利润])/SUM([销售额])", {
        numberFormat: NumberFormat.percentage(1)
    }));

registerCard(card.build());
```

如果数据集中已有利润率字段，可直接引用（无需 calcField）：
```javascript
    .addColorBy(f("利润率", { aggrType: AggrType.AVG }));
```

**自定义 colorBy 渐变色**：默认为主题色单色渐变。要设置自定义渐变色，使用 `setColorByColors`，支持两种方式：

1. **预设色板名称**（推荐）：`setColorByColors(ColorByPreset.RedGreen)`
2. **自定义 hex 颜色**：`setColorByColors({ startColor: "#hex", endColor: "#hex", middleColor?: "#hex", steps?: 5 })`

可用 `ColorByPreset` 值：

| 预设名称 | 类型 | 颜色 |
|---|---|---|
| `TrafficLight` | 发散 | `#F54F2A` → `#F1DB8B` → `#00A376` |
| `RedGreen` | 发散 | `#EC4F4F` → `#E0ECF0` → `#009688` |
| `HeatCold` | 发散 | `#0E64A8` → `#F7F6F6` → `#C53D18` |
| `Blue` | 顺序 | `#A3CCF8` → `#547CCE` |
| `Golden` | 顺序 | `#FADA61` → `#F76B1C` |
| `Green` | 顺序 | `#E0E6B7` → `#0D9347` |
| `Grey` | 顺序 | `#CBD3DA` → `#5B6A7C` |
| `Pink` | 顺序 | `#FFA9A9` → `#EF6065` |
| `Purple` | 顺序 | `#D3C3DB` → `#7260AF` |

```javascript
// 预设色板
var card = createCard(ChartType.BASIC_MAP, "利润率地图")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addColorBy(calcField("利润率", "SUM([利润])/SUM([销售额])", {
        numberFormat: NumberFormat.percentage(1)
    }))
    .setColorByColors(ColorByPreset.RedGreen);

// 自定义 hex 颜色
    .setColorByColors({ startColor: "#EC4F4F", middleColor: "#E0ECF0", endColor: "#009688", steps: 5 });
```

**WORLD_MAP（世界地图）**：

```javascript
var card = createCard(ChartType.WORLD_MAP, "全球销售分布")
    .bindDataset(DS)
    .addRow(f("国家"))
    .addColorBy(f("销售额", { aggrType: AggrType.SUM }));

registerCard(card.build());
```

**POINT_MAP（标记地图）**：row zone 放地名维度（1 个），metric zone 放指标（支持多个，最多 20 个）。

```javascript
var card = createCard(ChartType.POINT_MAP, "各省门店数")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addMetric(f("门店数", { aggrType: AggrType.SUM }))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));

registerCard(card.build());
```

**仪表板编排**：KPI 指标卡放最前，趋势/对比图表居中，明细表放最后。每页主 KPI 不超过 5-7 个。

### Field 对象

通过 `f("字段名")` 或 `field(DS, "字段名")` 从 schema 自动构造，无需手写 fdId/fdType。可通过 overrides 叠加属性：

```javascript
f("营收", {
    aggrType: AggrType.SUM,
    alias: "总营收",
    numberFormat: NumberFormat.currency("¥"),
    sortType: SortOrder.DESC
})
```
