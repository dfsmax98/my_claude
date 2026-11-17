# 反欺诈特征挖掘 Skill 套件

> 目标：用一句大白话（如"进行 applist 特征挖掘"）驱动 agent 自动跑完
> **查字典 → 查表脑暴 → 建4表 → 特征评估 → 策略分析**，产出美观 Excel 报告。

---

## Skill 清单

| Skill / 模块 | 目录 | 职责 |
|--------------|------|------|
| **fraud-feature-pipeline** | `fraud-feature-pipeline/` | 编排层：agent 读 SKILL.md 按 5 步串起全流程 |
| **strategy-mining** | `strategy-mining/` | 配置驱动特征衍生 + 建表（单源聚合 + 复合特征合并层）|
| **strategy-analysis** | `strategy-analysis/` | 策略挖掘（决策树，单/多变量）+ y影响 + 拒绝率影响 |
| **table-explorer** | `table-explorer/` | 表结构探查 → Markdown 文档 |
| **fraud-strategy-brainstorm** | `fraud-strategy-brainstorm/` | 特征设计思维框架（agent 参考）|
| lib/feature_eval.py | `lib/` | 特征评估：IV/KS/PSI/最大风险倍数，分月+分客群，决策树/等频分箱 |
| lib/db_router.py, lib/env_loader.py | `lib/` | 数据库连接路由 + .env 加载 |

---

## 前置：配置数据库凭证（一次）

凭证走 `.env`，脚本自动加载，agent 调用零手动步骤，且不进 git、不随 skill 分发。

```bash
cp .env.example .env
# 编辑 .env 填入真实 host/user/password
```

`.env` 已在 `.gitignore` 中。生产环境也可直接用真正的环境变量覆盖（env_loader 不覆盖已存在的变量）。

### 依赖

```bash
pip install pandas numpy scikit-learn openpyxl pymysql pyyaml
# 特征评估与策略挖掘不依赖 optbinning/xlwings；table-explorer 需 impala 时另装 impyla
```

---

## 五步流程（fraud-feature-pipeline）

详见 `fraud-feature-pipeline/SKILL.md`。概览：

| 步骤 | 谁做 | 动作 |
|------|------|------|
| 1 查字典 | agent | 读 strategy-mining 字典，看已有特征，避免重复 |
| 2 查表+脑暴+写配置 | agent | table-explorer 探表 → 设计特征 → 写 strategy-mining YAML |
| 3 建4表 | 脚本 | labeled/recent7d × preloan/inloan |
| 4 特征评估 | 脚本 | feature_eval 对 labeled 表算 IV/KS/PSI/lift |
| 5 策略分析 | 脚本 | 决策树挖单/多变量策略；y影响取labeled表，拒绝率取recent7d表 |

**双表分工**：特征评估 + 策略 y 影响 → labeled 表（有 fpd_k30）；拒绝率影响 → recent7d 表（近7天）。

### 一条命令串完 3→5 步

```bash
python fraud-feature-pipeline/scripts/run_pipeline.py \
    --config <你写的特征配置.yaml> --stage preloan \
    --steps build,eval,analyze \
    --labeled-table <labeled表名> --recent7d-table <recent7d表名> \
    --output-dir ./pipeline_out
```

- 只想生成 SQL 供 review：`--steps build --dry-run`
- 表已建好只跑评估+策略：`--steps eval,analyze`

---

## 单独调用各 Skill

```bash
# 表结构探查
python table-explorer/scripts/explore_table.py <表名>

# 特征衍生：从 YAML 生成 SQL（labeled/recent7d × preloan/inloan）
python strategy-mining/scripts/generate_feature_sql.py \
    --config strategy-mining/configs/<你的配置>.yaml \
    --output strategy-mining/assets/ --stages preloan inloan --modes labeled recent7d

# 特征评估（Python）
python -c "import sys; sys.path.insert(0,'lib'); import feature_eval as fe; \
  fe.evaluate_features(df, features, y_list=['fpd_k30'], dt_col='close_datetime', \
  group_cols=['cust_group_dq'], output_path='eval.xlsx', bin_method='tree')"

# 策略分析（Python）
python -c "import sys; sys.path.insert(0,'strategy-analysis'); \
  from src.analyzer import StrategyAnalyzer; \
  a=StrategyAnalyzer(scene='dq'); a.run_full('<特征表>', output_prefix='reports/x')"
```

---

## 关键设计约定

- **凭证**：只从 `.env` 读，代码/文档不含明文账号 IP。
- **防穿越**：特征时间 < 样本时间，由 generate_feature_sql 强制。
- **聚合白名单**：只允许 COUNT/COUNT_DISTINCT/SUM/AVG/MAX/MIN/STDDEV 等；未知函数（如伪函数 DATEDIFF_MAX）直接报错，需改用 composite 特征。
- **复合特征**：`type: composite` + `logic`，在合并层 JOIN 各源表后计算，支持 composite 间依赖。
- **策略挖掘**：决策树，单变量（每特征一棵树）+ 多变量（特征组合建树，根到叶=AND规则）。
- **拒绝率**：按 pass/reject 真实取值识别（不再硬编码 N/Y）。

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 连不上库 | .env 没配 | `cp .env.example .env` 填真值 |
| Column cannot be resolved | 配置字段与真实表不符 | 先 explore_table 确认字段名 |
| 未知聚合函数报错 | agg 不在白名单 | 改用白名单函数或 composite 特征 |
| 报告无 Excel 美化 | 用 openpyxl（无需本机 Excel）| 正常，数据完整 |

---

*本套件由 agent 直接调用为设计目标。改动脚本/接口后，请同步更新对应 SKILL.md。*
