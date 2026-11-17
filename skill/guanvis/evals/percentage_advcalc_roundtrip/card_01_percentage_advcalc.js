var region = f("地区");
var province = f("省/自治区");
var category = f("类别");
var subcategory = f("子类别");

var percentageCard = createCard(ChartType.PIVOT_TABLE, "L3 占比高级计算")
    .setId("pct01a02b03c04d05e06f07g")
    .bindDataset(DS)
    .addRow(region)
    .addRow(province)
    .addColumn(category)
    .addColumn(subcategory)
    .addMetric(f("销售额", {
        alias: "按列SUM占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byColumn()
    }))
    .addMetric(f("销售额", {
        alias: "按行SUM占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byRow()
    }))
    .addMetric(f("销售额", {
        alias: "地区层级SUM占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byField(region)
    }))
    .addMetric(f("销售额", {
        alias: "类别层级SUM占比",
        aggrType: AggrType.SUM,
        advCalc: percentage.byField(category)
    }))
    .addMetric(f("客户 ID", {
        alias: "客户去重按列占比",
        aggrType: AggrType.COUNT_DISTINCT,
        advCalc: percentage.byColumn()
    }))
    .addMetric(f("折扣", {
        alias: "折扣AVG地区占比",
        aggrType: AggrType.AVG,
        advCalc: percentage.byField(region)
    }));

registerCard(percentageCard.build());
