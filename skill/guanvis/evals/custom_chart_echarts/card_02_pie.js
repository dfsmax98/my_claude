var dataView = createCard(ChartType.DATA_GRID, "产品成本数据")
    .setId("b000000000000000000child")
    .bindDataset(DS)
    .addRow(f("产品"))
    .addMetric(f("成本", { aggrType: AggrType.SUM }));

var chart = createCustomChart("产品成本饼图")
    .setId("b000000000000000000chart")
    .setSubType(CustomChartSubType.ECHARTS_LITE)
    .loadContent("charts/pie")
    .addDataView(dataView);

registerCustomChart(chart.build());
