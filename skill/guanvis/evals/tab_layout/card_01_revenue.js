var card = createCard(ChartType.GROUPED_COLUMN, "区域产品营收")
    .setId("aaaaaaaaaaaaaaaaaaaaaaaa")
    .bindDataset(DS)
    .addRow(f("区域"))
    .addColumn(f("产品"))
    .addMetric(f("营收", { aggrType: AggrType.SUM, numberFormat: NumberFormat.currency("¥", 0) }))
    .setShowLegend(true, "right")
    .setDataLabel({ show: true, showNumber: true });

registerCard(card.build());
