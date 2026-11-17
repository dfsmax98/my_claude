var dateField = f("订单日期");

var normalCard = createCard(ChartType.PIVOT_TABLE, "L3 同环比 MVP 默认日期筛选模式")
    .setId("p3bc51ab664e095ab2dff402")
    .bindDataset(DS)
    .addFilter(filterField(DS, "订单日期", FilterType.BT, ["2024-01-01", "2025-12-31"]))
    .addFilter(filterField(DS, "订单日期", FilterType.BT, ["2025-01-01", "2025-12-31"]))
    .addMetric(f("销售额", {
        alias: "月同比对比值",
        aggrType: AggrType.SUM,
        advCalc: comparative.monthOverMonth(dateField, ComparativeOutput.COMPARE_VALUE)
    }))
    .addMetric(f("销售额", {
        alias: "季同比增长值",
        aggrType: AggrType.SUM,
        advCalc: comparative.quarterOverQuarter(dateField, ComparativeOutput.GROWTH_VALUE, { replenishDimData: true })
    }))
    .addMetric(f("销售额", {
        alias: "年同比增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYear(dateField, { replenishDimData: true })
    }))
    .addMetric(f("销售额", {
        alias: "上月末增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.periodEnd(dateField, ComparativePeriodEnd.MONTH_END, ComparativeOutput.GROWTH_RATE)
    }))
    .addMetric(f("销售额", {
        alias: "上季度末增长值",
        aggrType: AggrType.SUM,
        advCalc: comparative.periodEnd(dateField, ComparativePeriodEnd.QUARTER_END, ComparativeOutput.GROWTH_VALUE)
    }))
    .addMetric(f("销售额", {
        alias: "上年末对比值",
        aggrType: AggrType.SUM,
        advCalc: comparative.periodEnd(dateField, ComparativePeriodEnd.YEAR_END, ComparativeOutput.COMPARE_VALUE)
    }));

registerCard(normalCard.build());

var filterBasedCard = createCard(ChartType.PIVOT_TABLE, "L3 同环比 MVP 日期筛选模式")
    .setId("o360e50afb73bcc998353c13")
    .bindDataset(DS)
    .addFilter(filterField(DS, "订单日期", FilterType.BT, ["2024-01-01", "2025-12-31"]))
    .addFilter(filterField(DS, "订单日期", FilterType.BT, ["2025-01-01", "2025-12-31"]))
    .addMetric(f("销售额", {
        alias: "日环比增长值",
        aggrType: AggrType.SUM,
        advCalc: comparative.dayOverDay(dateField, ComparativeOutput.GROWTH_VALUE, { mode: ComparativeMode.FILTER_BASED })
    }))
    .addMetric(f("销售额", {
        alias: "周同比增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.weekOverWeek(dateField, ComparativeOutput.GROWTH_RATE, { mode: ComparativeMode.FILTER_BASED })
    }))
    .addMetric(f("销售额", {
        alias: "默认年同比增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYear(dateField)
    }))
    .addMetric(f("销售额", {
        alias: "年同比按周对比值",
        aggrType: AggrType.SUM,
        advCalc: comparative.yearOverYearByWeek(dateField, ComparativeOutput.COMPARE_VALUE, { mode: ComparativeMode.FILTER_BASED })
    }))
    .addMetric(f("销售额", {
        alias: "自定义后移增长率",
        aggrType: AggrType.SUM,
        advCalc: comparative.customMonthShift(dateField, -1, ComparativeOutput.GROWTH_RATE)
    }));

registerCard(filterBasedCard.build());
