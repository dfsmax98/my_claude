# Comparative MVP Round-Trip

This eval verifies the L3 native BI `COMPARATIVE` advanced calculation MVP against a real `default` BI environment.

It intentionally uses BI menu-facing cases:

- 日环比: 增长值
- 周同比: 增长率
- 月同比: 对比值
- 季同比: 增长值
- 年同比: 默认增长率 + 默认日期筛选模式
- 年同比(按周): 对比值
- 期末值: 上月末增长率、上季度末增长值、上年末对比值
- 自定义: 后移 1 个月增长率
- 普通模式兼容性由 exporter 单测覆盖；round-trip eval 使用日期筛选上下文保证线上 preview 有可验证结果

Run from `guanvis/`:

```bash
./evals/comparative_mvp_roundtrip/verify_default_roundtrip.sh
```

The script publishes fixed resource IDs to `default`, then verifies:

- `advCalc` is preserved in `zoneData.metric[*].advCalc`.
- No metric silently degrades to a formula.
- `card preview` succeeds.
- Each target metric has at least one non-empty preview value.

Runtime outputs are written to `.roundtrip/` and ignored by git.
