var region = f("地区");
var province = f("省/自治区");
var category = f("类别");

var rangeCard = createCard(ChartType.PIVOT_TABLE, "L3 排名高级计算 范围")
    .setId("r3f01a02b03c04d05e06f07a")
    .bindDataset(DS)
    .addRow(region)
    .addRow(province)
    .addColumn(category)
    .addMetric(f("销售额", {
        alias: "按列RANK降序",
        aggrType: AggrType.SUM,
        advCalc: rank.byColumn({ rankType: RankType.RANK, order: SortOrder.DESC })
    }))
    .addMetric(f("销售额", {
        alias: "按行DENSE升序",
        aggrType: AggrType.SUM,
        advCalc: rank.byRow({ rankType: RankType.DENSE_RANK, order: SortOrder.ASC })
    }))
    .addMetric(f("销售额", {
        alias: "地区组内ROW_NUMBER降序",
        aggrType: AggrType.SUM,
        advCalc: rank.byField(region, { rankType: RankType.ROW_NUMBER, order: SortOrder.DESC })
    }))
    .addMetric(f("销售额", {
        alias: "类别维度项RANK升序",
        aggrType: AggrType.SUM,
        advCalc: rank.byDimensionItem(category, { rankType: RankType.RANK, order: SortOrder.ASC })
    }));

registerCard(rangeCard.build());

var topNCard = createCard(ChartType.PIVOT_TABLE, "L3 排名高级计算 TopN")
    .setId("r4f01a02b03c04d05e06f08a")
    .bindDataset(DS)
    .addRow(region)
    .addRow(province)
    .addColumn(category)
    .addMetric(f("利润", {
        alias: "Top3适用小计",
        aggrType: AggrType.SUM,
        advCalc: rank.byColumn({
            rankType: RankType.RANK,
            order: SortOrder.DESC,
            topN: rank.topN(3, { applyToSubtotal: true })
        })
    }))
    .addMetric(f("利润", {
        alias: "Top5不适用小计",
        aggrType: AggrType.SUM,
        advCalc: rank.byDimensionItem(region, {
            rankType: RankType.DENSE_RANK,
            order: SortOrder.DESC,
            topN: rank.topN(5, { applyToSubtotal: false })
        })
    }));

registerCard(topNCard.build());
