---
name: sample-feature-join-sql
description: Use when joining a sample/label table to a wide online-feature table and need group-by SQL that keeps all sample columns and takes max() of each feature (dedup) renamed to the same name — risk/fraud strategy feature pulling from a feature dictionary, pre-loan/in-loan samples, StarRocks. Triggers include "样本表关联特征表", "取特征max去重", "线上特征字典", "保留样本字段 group by".
---

# 样本表 × 特征宽表 关联聚合 SQL 生成

## Overview

反欺诈/风控策略分析的固定动作：样本表（贷前/贷中，含主键+时间+y标签）关联线上特征宽表，**保留样本全字段做 group by，对每个特征取 `max()` 去重并重命名为同名**。特征常有几百上千个，手写不现实——用配置驱动的生成器从特征字典自动拼 SQL。

核心 SQL 形态（StarRocks）：
```sql
SELECT s.<样本全字段>, max(f.特征) AS 特征, ...
FROM 样本表 s
LEFT JOIN 特征宽表 f ON s.<关联键> = f.<关联键>
GROUP BY s.<样本全字段>;
```

## When to Use

- 样本表关联线上特征表，取特征 `max()` 去重，保留样本字段 group by
- 特征来自一份「特征名→含义」的字典文件，需筛子集（如异常行为、时间窗≤N天）
- 贷前/贷中多套样本，关联键不同，要批量产出多份 SQL

不适用：特征只有几个（直接手写）；需要 join 后做复杂衍生（本 skill 只做 max 去重聚合）。

## Workflow

1. **复制配置**：把 `example_config.py` 复制到工作目录，改成本次任务的 `CONFIG`。
2. **填 5 件事**（每个 target）：`sample_table` / `feat_table` / `join_keys` / `sample_cols`（样本全字段）/ `out`。注意输出路径 = 顶层 `out_dir` + target `out` 拼接（`os.path.join`），`out` 只是文件名；要落到指定目录必须同时设对 `out_dir`。
3. **可选筛选**：`filters.window_max_days`（时间窗上限）、`include_regex`（白名单）、`exclude_regex`（黑名单）。整个 `filters` 删掉 = 取字典全量。
4. **运行**：`python gen_feature_join.py <你的config.py>`，产出每个 target 一份 SQL + 命中特征清单。
5. **防 unknown column（强烈建议）**：对每张特征表跑 `desc`/导出列名到文件，在 target 里设 `column_file`，生成器会与真实列**取交集**，避免字典里有、表里没有的列导致 SQL 报错。

## Quick Reference

| 需求 | 配置项 |
|------|--------|
| 取字典全量特征 | 删掉 `filters` 整块 |
| 只留 ≤30 天窗口 | `filters.window_max_days: 30` |
| 只留某类特征 | `filters.include_regex: [...]` |
| 排除某些特征 | `filters.exclude_regex: [...]` |
| 联合关联键 | `join_keys: [(s1,f1),(s2,f2)]` |
| 换去重函数 | `agg: "max"`（可 min/sum） |
| 防止列不存在报错 | target `column_file: 列名文件` |
| 样本侧过滤 | target `sample_where: "dt='${dt}'"` |

## Files

- `gen_feature_join.py` — 通用生成器（配置驱动，勿改逻辑，改配置即可）
- `example_config.py` — 配置模板，复制后修改

## Common Mistakes

- **字典≠特征表全集**：字典是全量清单，pcr/rms 等宽表通常各含一部分。不取列交集 → `unknown column`。务必用 `column_file`，或先小范围试跑。
- **关联键基数未确认**：样本主键若有重复，结果行数=样本去重行数；特征表一键多行时 `max()` 跨行取最大（这正是“去重取max”的本意），但需确认符合预期。
- **时间窗后缀识别**：生成器按 `_Nd/_Nh/_today` 后缀判断窗口；非标准命名的窗口需在 `include_regex` 里显式处理。
- **样本全字段要真全**：`sample_cols` 漏列会导致 group by 丢字段。以样本表 `desc` 为准，别凭记忆列。
- **无窗口标志位的取舍**：设了 `window_max_days` 后，**无 `_Nd/_Nh/_today` 后缀**的特征默认被剔除，除非命中 `nowindow_keep_regex`。若有重要的无窗口标志位（如 `is_paste_*`、`if_foreign_*`），务必加进 `nowindow_keep_regex`，否则会被时间窗过滤误杀。
