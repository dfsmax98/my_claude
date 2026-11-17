---
name: fraud-feature-pipeline
description: 反欺诈特征挖掘全流程编排。当用户用大白话说"进行XX特征挖掘/衍生"(如applist/通讯录/设备特征)时, 按本skill依次执行: 查字典→查表脑暴→建4表→特征评估→策略分析, 最终产出美观Excel报告。串联 table-explorer / strategy-mining / feature_eval / strategy-analysis。
---

# 反欺诈特征挖掘全流程编排

这是一个 **agent 编排型 skill**: agent 读本文档, 按 5 步流程依次执行。
其中确定性步骤(建表/评估/策略)由脚本完成, 创造性步骤(特征设计)由 agent 完成。

## 触发

用户说类似这些话时启动本流程:
- "进行 applist 特征挖掘" / "衍生通讯录特征并评估" / "设备特征从头跑一遍"

## 前置

- 数据库凭证: skill 根目录 `.env`(由 `.env.example` 复制填写), 脚本自动加载, 无需手动 export。
- 依赖: pandas / numpy / scikit-learn / openpyxl / pymysql (评估与策略不依赖 optbinning/xlwings)。

## 五步流程

### Step 1 查特征字典 (agent 做)
查已有特征, 避免重复衍生。
- 读 `strategy-mining/references/feature-index.md` 和 `strategy-mining/assets/*_dictionary.csv`
- 向用户说明已有哪些相关特征

### Step 2 查表 + 头脑风暴 + 写配置 (agent 做, 核心创造性步骤)
1. 用 table-explorer 探查相关源表结构:
   ```bash
   python table-explorer/scripts/explore_table.py <表名>
   ```
   查看 `table-explorer/output/<表名>.md` 确认真实字段名(防止字段名猜错)。
2. 参考 `fraud-strategy-brainstorm` 的思维框架设计特征方向。
3. **写出 strategy-mining 配置 YAML**(参考 `strategy-mining/configs/contact_risk_schema_based.yaml` 的 schema):
   - `sample_table` 用真实样本表, `data_sources` 字段必须来自 table-explorer 输出
   - 基础特征用 `agg`(COUNT/COUNT_DISTINCT/SUM/AVG/MAX/MIN 等白名单函数)
   - 派生特征用 `type: composite` + `logic`(会在合并层计算)
   - 防穿越: 时间过滤由生成器自动加(特征时间 < 样本时间)

### Step 3 建 4 张表 (脚本做)
按 labeled(有fpd_k30表现) / recent7d(近7天) × preloan / inloan 建表:
```bash
python fraud-feature-pipeline/scripts/run_pipeline.py \
    --config <你写的配置.yaml> --stage preloan \
    --steps build --output-dir ./pipeline_out
# 先加 --dry-run 只生成 SQL 供 review, 确认无误再去掉 --dry-run 执行建表
```
产出: 贷前/贷中 × labeled/recent7d 的特征表 + composite 合并层表。

### Step 4 特征评估 (脚本做)
对 labeled 表算 IV / KS / PSI / 最大风险倍数, 分月 + 分客群, 决策树分箱:
```bash
python fraud-feature-pipeline/scripts/run_pipeline.py \
    --stage preloan --steps eval \
    --labeled-table <labeled表名> --output-dir ./pipeline_out
```
产出: `feature_eval_preloan.xlsx`(综合指标/IV值/KS值/PSI/最大风险倍数/分客群指标/分组明细)。

### Step 5 策略分析 (脚本做)
决策树挖掘单变量 + 多变量策略; **y标签影响取 labeled 表, 拒绝率影响取 recent7d 表**:
```bash
python fraud-feature-pipeline/scripts/run_pipeline.py \
    --stage preloan --steps analyze \
    --labeled-table <labeled表名> --recent7d-table <recent7d表名> \
    --output-dir ./pipeline_out
```
产出: `strategy_dq_step1.xlsx`(策略+y影响) + `strategy_dq_step2.xlsx`(拒绝率影响)。

## 一次跑完 3→5 步
表配置就绪后, 可一条命令串完:
```bash
python fraud-feature-pipeline/scripts/run_pipeline.py \
    --config <配置.yaml> --stage preloan --steps build,eval,analyze \
    --labeled-table <labeled表> --recent7d-table <recent7d表> \
    --output-dir ./pipeline_out
```

## 子 skill 分工

| skill / 模块 | 职责 | 用在 |
|--------------|------|------|
| table-explorer | 表结构探查 | Step2 |
| fraud-strategy-brainstorm | 特征设计思路 | Step2 |
| strategy-mining | 特征衍生 + 建表 | Step3 |
| lib/feature_eval.py | 特征评估(IV/KS/PSI/lift, 分月分客群) | Step4 |
| strategy-analysis | 策略挖掘(决策树,单/多变量) + y影响 + 拒绝率影响 | Step5 |

## 质量红线

- 防穿越: 特征时间 < 样本时间(生成器强制)
- 分客群: 贷前 cust_group_dq, 贷中 cust_group_dz + new_old
- 决策字段: 拒绝率影响按 pass/reject 真实取值识别
- 凭证: 只从 .env 读, 不硬编码
