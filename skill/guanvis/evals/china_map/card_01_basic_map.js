// BASIC_MAP: 中国省级行政地图（内置 Highmaps）
// row zone 放地理维度（省/自治区名），colorBy zone 放渐变着色指标
// 后端验证：rowSize == 1 && (colorBySize == 1 | metricSize == 1)

var card = createCard(ChartType.BASIC_MAP, "各省利润率")
    .setId("b11111111111111111111110")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addColorBy(calcField("利润率", "SUM([利润])/SUM([销售额])", {
        numberFormat: NumberFormat.percentage(1)
    }));

registerCard(card.build());
