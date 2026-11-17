var card = createCard(ChartType.GROUPED_COLUMN, "利润率-计算字段测试")
    .setId("te122aaf82e38c1fa3693250")
    .bindDataset(DS)
    .addRow(f("区域"))
    .addMetric(f("营收", { aggrType: AggrType.SUM }))
    .addMetric(calcField("利润", "(SUM([营收])-SUM([成本]))", { calculationType: "aggregation" }))
    .addMetric(calcField("毛利率", "(SUM([营收])-SUM([成本]))/SUM([营收])", {
        calculationType: "aggregation",
        numberFormat: NumberFormat.percentage(1)
    }));

registerCard(card.build());
