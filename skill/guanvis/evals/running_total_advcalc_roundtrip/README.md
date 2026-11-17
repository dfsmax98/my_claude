This eval verifies the L3 native BI `RUNNING_TOTAL` advanced calculation builder against a real `default` BI environment.

It publishes fixed card/page IDs, reads the created cards back, and verifies:

- `COLUMN` accumulation.
- `ROW` accumulation.
- `FIELD` accumulation by a non-date dimension.
- date field accumulation with `DAY`, `WEEK`, `MONTH`, `YEAR`, and `NONE`.
- sub-date field accumulation with `QUARTER` and `NONE`.
- `advCalc` is preserved in `zoneData.metric[*].advCalc`.
- preview returns non-empty accumulated metric values.

The default-environment roundtrip runner is intentionally not committed with this eval.
Its command sequence and assertions are recorded in the knowledge base:
`01-Projects/L3-running-total-advcalc-golden-answer.md`.
