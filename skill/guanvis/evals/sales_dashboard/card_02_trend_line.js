var card = createCard(ChartType.MULTI_LINE, "月度趋势")
    .setId("p3e20cf5d750ee644259f7b8")
    .bindDataset(DS)
    .addRow(f("月份"))
    .addMetric(f("营收", { aggrType: AggrType.SUM, numberFormat: NumberFormat.auto("万") }))
    .addMetric(f("成本", { aggrType: AggrType.SUM, numberFormat: NumberFormat.auto("万") }))
    .setShowLegend(true, "bottom");

registerCard(card.build());
