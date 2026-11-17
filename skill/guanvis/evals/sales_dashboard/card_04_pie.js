var card = createCard(ChartType.PIE, "产品分布")
    .setId("s1fa6bd1b68a4974f7ad0202")
    .bindDataset(DS)
    .addRow(f("产品"))
    .addMetric(f("营收", { aggrType: AggrType.SUM }))
    .setDataLabel({ show: true, showPercentage: true, showCategory: true })
    .setPieSetting({ innerRadius: 0 });

registerCard(card.build());
