# 反欺诈特征挖掘 Pipeline 改造方案

> 目标：用一句大白话（如"进行 applist 特征挖掘"）驱动 agent 自动跑完 5 步全流程，最终产出美观的 Excel 报告。
> 定位：`fraud-feature-pipeline` 重写为**真正的编排层**，串联 table-explorer / strategy-mining / DDViz / strategy-analysis。
> 状态：方案草案，待确认后分步实施。

---

## 一、目标流程（用户大白话 → agent 执行 5 步）

以"进行 applist 特征挖掘"为例：

| 步骤 | 动作 | 承接 skill / 工具 | 产出 |
|------|------|-------------------|------|
| **1 查字典** | 检查特征字典，看已有 app 相关特征 | strategy-mining: `references/feature-index.md` + `*_dictionary.csv` | 已有特征清单（避免重复衍生） |
| **2 查表+脑暴** | 查 app 相关表结构，头脑风暴衍生新特征 | table-explorer 探表 + fraud-strategy-brainstorm + agent 生成 YAML 配置 | 特征衍生 YAML 配置 |
| **3 建4张表** | 执行建表 SQL | strategy-mining（labeled/recent7d × preloan/inloan） | 贷前(fpd_k30表现)、贷前(近7天)、贷中(fpd_k30表现)、贷中(近7天) |
| **4 特征评估** | 分月、分客群评估 PSI/IV/Lift/KS | **复用 DDViz `out_all_in_one`** | 10-sheet 美观 Excel（对齐 ddv 模板） |
| **5 策略分析** | 上线策略对 y 标签 + 拒绝率的影响 | strategy-analysis | 策略报告：y影响(取labeled表) + 拒绝率影响(取recent7d表) |

**双表分工**（关键）：
- Step4 特征评估 + Step5 的 **y 标签影响** → 用 **labeled 表**（有 fpd_k30 表现）
- Step5 的 **拒绝率影响** → 用 **recent7d 表**（近7天，反映当前通过率）

---

## 二、已确认的决策

1. ✅ **第4步评估复用 DDViz**，不在 strategy-analysis 重造 KS/分组透视轮子。
2. ✅ **DDViz 作为依赖模块**复制进 skill（`skill/lib/ddviz.py` 或 `fraud-feature-pipeline/lib/`）。
3. ✅ **分步实施**，每步验收。
4. ✅ 建表结构：贷前/贷中 各 2 表（labeled + recent7d）。
5. ✅ 分客群：`cust_group`（dq/dz）和 `new_old` 都作为分组维度。
6. ✅ 报告格式对齐 `out_all_in_one_template (1).xlsx`（10 sheet：字符/数值变量描述、分组透视、综合指标、空值率、PSI、IV值、KS值、最大风险倍数、分组明细）。

---

## 三、skill 分工（改造后）

```
fraud-feature-pipeline (编排层, 重写)
   ├─ 解析大白话意图 → 确定 feature_group / stage / 场景
   ├─ Step1 → 读 strategy-mining 字典
   ├─ Step2 → 调 table-explorer + 输出脑暴建议(agent 补 YAML)
   ├─ Step3 → 调 strategy-mining 生成+执行 4 表
   ├─ Step4 → 调 DDViz.out_all_in_one 出评估报告
   └─ Step5 → 调 strategy-analysis 出策略报告

strategy-mining      : 特征衍生 + 建表 (已修复复合特征/agg白名单)
table-explorer       : 表结构探查
DDViz (新增依赖模块)  : 特征评估报告 (PSI/IV/KS/分组透视/最大风险倍数)
strategy-analysis    : 策略分析 (y影响 + 拒绝率影响), 保留; 特征评估部分让位给 DDViz
fraud-strategy-brainstorm : 脑暴辅助(agent 读)
```

---

## 四、前置依赖与风险（重要）

DDViz 依赖较重，复用前需确认环境：

| 依赖 | 用途 | 风险 |
|------|------|------|
| `optbinning` | 决策树/单调分箱 | 需 pip 安装，Py3.14 兼容性待验证 |
| `xlwings` | Excel 报告美化 | **需本机装 Excel**，无 Excel 环境会失败 |
| `excel2img` | 报告转图片 | 同上，依赖 Excel COM |
| `seaborn`/`matplotlib`/`statsmodels` | 图表 | 一般可装 |
| `impala` | DDViz 自带取数 | 我们改用已有 db 连接，不用它取数 |

**降级策略**：若 `xlwings`/`excel2img`/`optbinning` 在当前环境装不上，Step4 报告改用 `openpyxl` 输出（纯数据版，无 Excel 美化/图片），保证流程能跑通。这点需实测后定。

---

## 五、分步实施计划（每步验收）

| 阶段 | 内容 | 验收标准 |
|------|------|----------|
| **P0 依赖验证** | 装 optbinning 等，验证 DDViz 能否 import + 跑通一个最小样例 | DDViz 可作模块调用，或确定降级方案 |
| **P1 DDViz 集成** | DDViz 复制进 skill，封装成 `evaluate_features(table, ...)` 接口 | 传入表名 → 出 10-sheet Excel |
| **P2 strategy-mining 建4表** | 确认 labeled/recent7d × preloan/inloan 建表跑通 | 4 张表 SQL 正确、防穿越 |
| **P3 strategy-analysis 改造** | 调整为"y影响取labeled表 + 拒绝率取recent7d表"，修通过率硬编码bug | 两个影响指标计算正确 |
| **P4 pipeline 编排** | 重写 fraud-feature-pipeline，串起 5 步，支持大白话入口 | 一句话跑完整流程 |
| **P5 结构清理** | 提嵌套、修 README/SKILL、清文档 IP、补 frontmatter | 文档与实现一致 |

---

## 六、遗留问题（实施中确认）

- [ ] DDViz 的 y 标签列名（`fpd30`/`mob3_k30`）与样本表实际字段（`fpd_k30`）的映射
- [ ] DDViz 取数：改用 skill 现有 db 连接把表读成 DataFrame 再传给 `out_all_in_one`，不用 DDViz 自带 impala
- [ ] "参考 ddv 报告格式"：以 `out_all_in_one_template (1).xlsx` 为准
- [ ] Step5 拒绝率的决策字段真实取值（修 evaluator 的 `'N'/'Y'` 硬编码 → 实际 `pass/reject`）
- [ ] strategy-analysis 已加的 PSI/KS 逻辑：与 DDViz 分工后，是否回退（避免重复维护）

---

*本方案确认后按 P0→P5 分步实施，每步验收。*
