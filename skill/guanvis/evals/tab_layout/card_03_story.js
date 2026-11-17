var text = createTextCard("Tab 使用说明")
    .setId("cccccccccccccccccccccccc")
    .addMarkdown(
        "### Tab 布局示例\n\n" +
        "- `createTab()` 创建容器\n" +
        "- `addPanel(name, callback)` 创建页面上可切换的标签\n" +
        "- panel 内通过 cardIndex 放置图表/文本等卡片，也可以用 selector 字符串 ID 放置筛选器\n\n" +
        "> 未放入画布布局的筛选器会进入筛选器栏；用 `placeCard(\"selectorId\")` 放入 panel/root/cardGroup 后，同页筛选器栏不再重复展示。"
    );

registerTextCard(text.build());
