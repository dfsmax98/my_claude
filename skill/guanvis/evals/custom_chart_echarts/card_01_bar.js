var dataView = createCard(ChartType.DATA_GRID, "区域营收数据")
    .setId("a000000000000000000child")
    .bindDataset(DS)
    .addRow(f("区域"))
    .addMetric(f("营收", { aggrType: AggrType.SUM }));

var chart = createCustomChart("区域营收柱状图")
    .setId("a000000000000000000chart")
    .setSubType(CustomChartSubType.ECHARTS_LITE)
    .loadContent("charts/bar")
    .addDataView(dataView);

registerCustomChart(chart.build());
