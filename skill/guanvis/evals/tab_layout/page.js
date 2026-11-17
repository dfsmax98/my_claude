var salesTab = createTab("销售分析")
    .setId("tab_AbCdEf")
    .setLabelStyle(TabLabelStyle.CAPSULE)
    .setAlignment(TabAlignment.CENTER)
    .addPanel("区域分析", function(panel) {
        panel
            .setId("panel_GhIjKl")
            .addRow([{ card: 1, w: 6 }, { card: 3, w: 6 }], 6);
    })
    .addPanel("趋势分析", function(panel) {
        panel
            .setId("panel_MnOpQr")
            .addFullWidthCard(2, 7);
    });

var page = createPage("Tab Layout 示例")
    .setId("pppppppppppppppppppppppp")
    .setDescription("展示根布局指标卡、tab 容器、panel 内图表/文本卡片，以及 selector 可默认进入筛选器栏或用字符串 ID 放入画布。")
    .setCardMargin(8)
    .addRow([{ card: 0, w: 4 }], 3)
    .addTab(salesTab);

registerPage(page.build());
