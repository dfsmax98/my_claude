var card = createCard(ChartType.KPI_CARD, "总营收")
    .setId("o1c1e4431cc0c6dcc30663a1")
    .bindDataset(DS)
    .addMetric(f("营收", { aggrType: AggrType.SUM, numberFormat: NumberFormat.currency("¥", 0) }));

registerCard(card.build());
