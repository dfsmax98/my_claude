// Selector: Region filter with auto-link to all cards
var sel = createSelector("区域筛选")
    .setId("j423ad9cedf3b4bb1336fd6b")
    .bindField(f("区域"))
    .setMultiSelect(true)
    .setDefaultType(SelectorDefaultType.FIRST_PICK)
    .linkToAll()
    .build();

registerSelector(sel);
