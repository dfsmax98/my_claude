var card = createCard(ChartType.MULTI_LINE, "月度营收成本趋势")
    .setId("bbbbbbbbbbbbbbbbbbbbbbbb")
    .bindDataset(DS)
    .addRow(f("月份"))
    .addMetric(f("营收", { aggrType: AggrType.SUM, numberFormat: NumberFormat.auto("万") }))
    .addMetric(f("成本", { aggrType: AggrType.SUM, numberFormat: NumberFormat.auto("万") }))
    .setShowLegend(true, "bottom");

registerCard(card.build());
