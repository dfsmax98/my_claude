# Rank Advanced Calc Round-Trip

This eval verifies the L3 native BI `RANK` advanced calculation builder against a real `default` BI environment.

It covers:

- 按列：`RANK` + 从高到低
- 按行：`DENSE_RANK` + 从低到高
- 维度组内：`ROW_NUMBER` + 指定行维度
- 维度项：`RANK` + 指定列维度
- Top N：`CUSTOM_NUMBER` with `applyToSubtotal=true/false`

Run from `guanvis/`:

```bash
./evals/rank_advcalc_roundtrip/verify_default_roundtrip.sh
```

The script publishes fixed resource IDs to `default`, then verifies:

- `advCalc` is preserved in `zoneData.metric[*].advCalc`.
- No metric silently degrades to a formula.
- Each expected `calDimension` / `rankType` / `sorting` / `tfdId` / `topN` field round-trips.
- `card preview` succeeds and ranking aliases have non-empty values.

Runtime outputs are written to `.roundtrip/` and ignored by git.

The eval uses fixed resource IDs and `GUANCLI_PROFILE=default`; reruns overwrite the same test page/cards in the shared default environment.
