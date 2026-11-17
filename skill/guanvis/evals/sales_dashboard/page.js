var page = createPage("销售分析仪表板")
    .setId("a67a1cddb97678851fe1317f")
    .setDescription("综合销售数据分析看板")
    .setBackgroundColor("#f5f5f5")
    .setCardMargin(8)
    .placeCard(2, 0, 0, 4, 4)
    .placeCard(3, 4, 0, 8, 4)
    .addFullWidthCard(0, 6)
    .addFullWidthCard(1, 6);

registerPage(page.build());
