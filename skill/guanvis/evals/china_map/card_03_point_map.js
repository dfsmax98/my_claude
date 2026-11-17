// POINT_MAP: 标记地图（内置 Highmaps）
// row zone 放地名维度（1个），metric zone 放数值指标（可多个）
// 后端验证：rowSize == 1 && metricSize >= 1

var card = createCard(ChartType.POINT_MAP, "各省订单与销售额")
    .setId("b33333333333333333333330")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addMetric(f("订单数", { aggrType: AggrType.SUM }))
    .addMetric(f("销售额", { aggrType: AggrType.SUM }));

registerCard(card.build());
