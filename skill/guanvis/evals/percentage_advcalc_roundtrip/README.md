# Percentage Advanced Calc Round-Trip

This eval verifies the L3 native BI `LEVEL_PERCENTAGE` advanced calculation builder against a real `default` BI environment.

It covers:

- 按列：`SUM`
- 按行：`SUM` with a column dimension, matching the UI-created path
- 指定行维度：`SUM`
- 指定列维度：`SUM`
- 去重计数：`CNT_DISTINCT`
- 平均值：`AVG`, covering the backend SUM/CNT auxiliary denominator path

Local payload preview from `guanvis/`:

```bash
go run ./cmd/guanvis preview ./evals/percentage_advcalc_roundtrip
```

Default-environment publish/readback commands intentionally live in the project golden-answer note rather than this PR, because they publish fixed resource IDs to the shared `default` environment. The manual verification checks:

- `advCalc` is preserved in `zoneData.metric[*].advCalc`.
- No metric silently degrades to a formula.
- Each expected `measureOnDimRow` / `tfdId` / `auto` field round-trips.
- Percentage number format is present with two decimal places.
- `card preview` succeeds and percentage aliases have non-empty values.
