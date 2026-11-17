// WORLD_MAP: 世界国家级地图（内置 Highmaps）
// row zone 放国家名维度，colorBy zone 放渐变着色指标

var card = createCard(ChartType.WORLD_MAP, "全球销售分布")
    .setId("b22222222222222222222220")
    .bindDataset(DS)
    .addRow(f("省/自治区"))
    .addColorBy(f("销售额", { aggrType: AggrType.SUM }));

registerCard(card.build());
