var scrollRegion = f("地区");

var scrollPercentageCard = createCard(ChartType.SCROLL_TABLE, "L3 占比高级计算 Scroll")
    .setId("pct02a02b03c04d05e06f07g")
    .bindDataset(DS)
    .addRow(scrollRegion)
    .addMetric(f("销售额", {
        alias: "滚动表默认聚合占比",
        advCalc: percentage.byColumn()
    }));

registerCard(scrollPercentageCard.build());
