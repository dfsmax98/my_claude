var card = createCard(ChartType.SINGLE_VALUE, "总营收")
    .setId("eeeeeeeeeeeeeeeeeeeeeeee")
    .bindDataset(DS)
    .addMetric(f("营收", { aggrType: AggrType.SUM, numberFormat: NumberFormat.currency("¥", 0) }));

registerCard(card.build());
