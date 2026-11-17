var sel = createSelector("区域筛选")
    .setId("ssssssssssssssssssssssss")
    .bindField(f("区域"))
    .setMultiSelect(true)
    .linkToAll()
    .build();

registerSelector(sel);
