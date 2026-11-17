var orderDate = f("订单日期");
var orderMonth = f("订单日期", { granularity: Granularity.MONTH });
var region = f("地区");
var province = f("省/自治区");
var category = f("类别");

var rangeCard = createCard(ChartType.PIVOT_TABLE, "L3 累计高级计算 范围")
    .setId("t3f01a02b03c04d05e06f07a")
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
        alias: "订单日期日累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderDate, RunningTotalGranularity.DAY)
    }))
    .addMetric(f("销售额", {
        alias: "订单日期周累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderDate, RunningTotalGranularity.WEEK)
    }))
    .addMetric(f("销售额", {
        alias: "订单日期月累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderDate, RunningTotalGranularity.MONTH)
    }))
    .addMetric(f("销售额", {
        alias: "订单日期当年累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderDate, RunningTotalGranularity.YEAR)
    }))
    .addMetric(f("销售额", {
        alias: "订单日期历年累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderDate, RunningTotalGranularity.ALL_YEARS)
    }));

registerCard(rangeCard.build());

var subDateCard = createCard(ChartType.PIVOT_TABLE, "L3 累计高级计算 子日期")
    .setId("t4f01a02b03c04d05e06f08a")
    .bindDataset(DS)
    .addRow(orderMonth)
    .addRow(region)
    .addColumn(category)
    .addMetric(f("利润", {
        alias: "订单月季度累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderMonth, RunningTotalGranularity.QUARTER)
    }))
    .addMetric(f("利润", {
        alias: "订单月历年累计",
        aggrType: AggrType.SUM,
        advCalc: runningTotal.byDateField(orderMonth, RunningTotalGranularity.ALL_YEARS)
    }));

registerCard(subDateCard.build());
