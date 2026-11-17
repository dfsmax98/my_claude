var card = createCard(ChartType.GROUPED_COLUMN, "区域营收分析")
    .setId("qe122aaf82e38c1fa369325e")
    .bindDataset(DS)
    .addRow(f("区域"))
    .addMetric(f("营收", { aggrType: AggrType.SUM, numberFormat: NumberFormat.currency("¥", 0) }))
    .addColumn(f("产品"))
    .setShowLegend(true, "right")
    .setDataLabel({ show: true, showNumber: true });

registerCard(card.build());
