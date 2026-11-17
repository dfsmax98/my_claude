## Tableau 迁移 Checklist

从 Tableau 迁移仪表板到观远BI时，必须按以下清单逐项检查：

### 迁移前

1. **解析 Tableau 仪表板结构**：用 `tableau-skill db <file> <dashboard_name> -f json` 获取完整结构
2. **识别所有交互元素**：Dashboard JSON 中 `IsFilter=true` 的 zone 是筛选器，`IsParam=true` 的 zone 是参数控件
3. **识别计算字段**：用 `tableau-skill calc <file> -f json` 获取所有计算字段，判断迁移策略

### 筛选器翻译（必做）

Tableau 仪表板上的 filter zone 必须翻译为观远的 `createSelector()`：

| Tableau FilterMode | 观远 Selector 配置 |
|---|---|
| `typeinlist` / `typeinmulti` | `setMultiSelect(true)` + `setDisplayType(SelectorDisplay.SEARCH_BOX)` |
| `typeinsingle` | `setMultiSelect(false)` + `setDisplayType(SelectorDisplay.SEARCH_LIST)` |
| 日期范围筛选 | `.setSelectorType(SelectorType.CALENDAR)` 或 `.setSelectorType(SelectorType.DS_INTERVAL)` |
| 相对日期筛选（Relative date） | `.setTimeMacroOptions([{ name: "最近7天", expr: ["LAST_7_DAY"] }, ...])` |
| 数值范围筛选（利润率、金额等连续值） | `.setSelectorType(SelectorType.DS_INTERVAL)`（默认 BT 区间，起始值-结束值输入框） |
| 数值精确筛选 | `.setSelectorType(SelectorType.DS_INTERVAL).setFilterType("EQ")` |

**关键**：连续数值字段（如利润率、折扣率、金额等）**必须**使用 `DS_INTERVAL`，不要用 `DS_ELEMENTS`（列表选择会列出所有离散值，对连续数值没有意义）。

所有 selector 必须调用 `.linkToAll()` 实现联动。

### 计算字段迁移决策树

| Tableau 计算类型 | 观远实现方式 | 说明 |
|---|---|---|
| 行级计算（如 `利润/销售额`） | **数据集计算字段**（`guands dataset calc-field add`） | 所有卡片和筛选器都能引用，推荐 |
| 聚合计算（如 `SUM(利润)/SUM(销售额)`） | **卡片级 calcField** | 仅在单个卡片内有效 |
| LOD 表达式（FIXED/INCLUDE/EXCLUDE） | **ETL** 或 **卡片级 window calcField** | 需要根据具体语义判断 |
| 原生高级计算（Running Total、Rank） | **原生 advCalc builder** | 优先用 `runningTotal.*` / `rank.*`，不要手写 window calcField |
| 其他表计算 | **卡片级 window calcField** | 当前无原生 builder 时再用 `calculationType: "window"` |
| 多表 JOIN + 计算 | **ETL**（guanetl） | 需要先合表再计算 |

**重要**：如果需要在筛选器中引用计算字段（如"利润率"筛选器），必须使用**数据集计算字段**而非卡片级 calcField，因为 selector 只能绑定数据集上的物理字段。

### calcField 命名规则

- calcField 的 name **不能与数据集已有字段同名**，否则观远BI会报 warning 并默认取数据集字段
- 如果数据集已有"利润率"字段，卡片级 calcField 应命名为"利润率_agg"或"利润率_calc"等
- `pack`/`publish` 时的验证会自动检查重名并输出 warning

### 无法迁移内容的处理（必做）

如果有无法 1:1 迁移的 Tableau 元素，**必须**在页面最底部添加一个全宽文本卡片说明：

```javascript
var note = createTextCard("迁移说明")
    .setId("<genid>")
    .addMarkdown(
        "---\n" +
        "### Tableau 迁移说明\n\n" +
        "本页面从 Tableau 工作簿 `<workbook_name>` 的 `<dashboard_name>` 迁移而来。\n\n" +
        "**未迁移的内容：**\n" +
        "- <列出未迁移项及原因>\n\n" +
        "**与原始 Tableau 的差异：**\n" +
        "- <列出差异>\n"
    );
registerTextCard(note.build());

// 在 page.js 中将说明卡片放在最底部
page.addFullWidthCard(<noteCardIndex>, 3);
```

需要说明的典型内容：
- Tableau 参数控件（观远用筛选器替代）
- LOD 表达式的近似实现
- 颜色/格式的差异
- 交互行为的差异（如 Tableau 的 highlight action）
