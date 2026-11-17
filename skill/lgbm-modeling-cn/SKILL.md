---
name: lgbm-modeling-cn
description: 基于LightGBM的中文二分类风控建模全流程。当用户需要构建预测模型（权益购买预测、违约预测、风控评分等），涉及变量筛选（高基数、覆盖率、PSI、重要性、IV衰减、Bad Rate一致性、相关性）、模型训练（Optuna调参、变量精简、定稿）、bivar分析、模型报告生成时使用此skill。
version: 1.0.0
---

# LightGBM 中文二分类风控建模

## 用途

端到端风控建模流程：数据加载 → 变量筛选 → 模型训练 → 效果评估 → 部署产出物。适用于信贷/风控等二分类预测场景，处理中文数据和大规模特征。

## 流程步骤

### Phase A: 变量筛选（7步顺序执行）

1. **高基数分类变量剔除** - 类别数>20的分类变量
2. **低覆盖率剔除** - 非缺失覆盖率<2%的变量
3. **PSI筛选** - PSI>阈值(0.1/0.15/0.2)的变量
4. **零重要性剔除** - LGBM训练后重要性=0的变量
5. **IV衰减筛选** - IV值by月衰减率>0.5的变量（排除6月）
6. **Bad Rate一致性** - Spearman相关系数>=0.5（正向，不用abs）
7. **皮尔逊相关性** - abs(相关系数)>0.9的变量对，剔除重要性较低的

每步输出作为下一步输入，详细代码见 references/code_templates.md。

### Phase B: 模型训练（3步）

1. **Optuna调参** - 80 trials, 300 trees, 最大化Valid AUC
2. **变量精简**（可选）- 每轮剔除10个最低重要性，监控Valid AUC下降>0.005时停止
3. **模型定稿** - 全量Train训练，输出模型/变量清单/评估指标/清洗逻辑

## 使用方式

### 样本划分

```python
Train: M1 + M2 月份全部样本（调参时80/20分层抽样为Train/Valid）
OOT:   M3 + M4 月份全部样本（时间外样本）
login_month: 字符串格式，如 "2026-03"
```

### 数据加载（PyArrow加速）

对600+列×80万行数据，pyarrow table-level cast比pandas astype快10倍：

```python
import pyarrow.parquet as pq
import pyarrow as pa

table = pq.read_table(DATA_PATH, columns=cols_needed)
new_fields = [pa.field(f.name, pa.float64()) if f.name in model_vars else f
              for f in table.schema]
df = table.cast(pa.schema(new_fields)).to_pandas()
```

### 缺失值处理

仅替换数值型缺失值，LGBM原生支持NaN：

```python
MISSING_VALUES = [-99, -8888, -9999997, -9999, -98, -97, -96]
for col in model_vars:
    df[col] = df[col].replace(MISSING_VALUES, np.nan)
```

### LightGBM训练（4.6.0 API）

```python
import lightgbm as lgb
from lightgbm import LGBMClassifier

model = LGBMClassifier(**params)
model.fit(X_train, y_train,
    eval_set=[(X_valid, y_valid)],
    eval_metric="auc",
    callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(50)])
pred = model.predict_proba(X, num_iteration=model.best_iteration_)[:, 1]
```

### Optuna调参

```python
import optuna
from sklearn.metrics import roc_auc_score

def objective(trial):
    params = {
        "num_leaves": trial.suggest_int("num_leaves", 15, 63),
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.01, 10, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.01, 10, log=True),
        "n_estimators": 300,
        "objective": "binary",
        "metric": "auc",
        "random_state": 42,
        "verbose": -1
    }
    model = LGBMClassifier(**params)
    model.fit(X_train, y_train,
        eval_set=[(X_valid, y_valid)],
        eval_metric="auc",
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
    pred_valid = model.predict_proba(X_valid, num_iteration=model.best_iteration_)[:, 1]
    return roc_auc_score(y_valid, pred_valid)

study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
study.optimize(objective, n_trials=80, show_progress_bar=True)
```

### Bivar图格式

- 5箱等频分箱（基于Train非缺失值）
- 缺失值单独成一箱，标注"缺失值"，置于首位
- 蓝色柱状图 = 样本数，红色折线 = Bad Rate
- figsize=(16, 6)，左右两个子图（Train vs OOT）
- 使用Train的分箱边界对OOT分箱

### 中文支持

```python
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
```

### Lift定义
```
Lift = 该箱bad_rate / 整体bad_rate
```
**不是**相对于最低箱的倍数。

## 示例

**示例 1: 变量筛选流程**

- 输入：628个变量的parquet文件，4个月数据（2026-03至2026-06）
- 输出：119个入模变量，附带PSI/IV/重要性等指标
- 过程：7步顺序筛选，每步输出中间结果CSV

**示例 2: 模型定稿**

- 输入：119个入模变量列表 + Optuna调参结果
- 输出：
  - 模型文件：model.pkl
  - 变量清单：variables.csv
  - 评估指标：eval.json（AUC/KS/PSI）
  - 清洗逻辑：cleaning_logic.md
  - 模型报告：Excel格式（含Gains Table/PSI分布/bivar图）

**示例 3: 月度分析**

- 输入：入模变量列表 + 4个月数据
- 输出：monthly_analysis.xlsx
  - 每个变量：分箱区间、3月bad_rate、3月lift、3-6月各箱占比
  - 条件格式：bad_rate（红色）、lift（绿色）、占比（蓝/橙/灰/黄）

## 依赖

- Python 3.8+
- pandas, numpy, pyarrow, lightgbm (>=4.0), optuna, scikit-learn, scipy, matplotlib, openpyxl
- 中文字体：SimHei或Microsoft YaHei
- 数据格式：Parquet，login_month为字符串

## 注意事项

1. **login_month是字符串** - 比较时用"2026-03"，不是整数202603
2. **Spearman >= 0.5, 不用abs()** - abs()会错误引入反向趋势变量
3. **Pearson abs() > 0.9** - 高相关（正向或反向）均为冗余，剔除重要性较低的
4. **Optuna log=True下界必须>0** - 如0.01，不能是0
5. **缺失值仅数值型** - 所有变量已转float64时，不要加入字符串缺失值
6. **best_iteration_可能为None** - 未触发early stopping时需fallback到n_estimators
7. **Notebook生成格式** - code cell的source必须是list，每行一个元素加换行符\\n
8. **Zero-inflated变量** - 大量为0的变量（如赎回类）需值域分箱而非等频分箱
9. **提交前验证代码** - 检查变量名、数据类型、文件路径
10. **PyArrow cast加速** - 600+列×80万行数据，table.cast比astype快10倍

## 关键指导

### Progressive Disclosure

- SKILL.md 控制在500行以内
- 详细代码模板在 references/code_templates.md
- 踩坑指南在 references/pitfalls.md
- 遇到具体步骤实现时，读取对应reference文件

### 交互模式

1. **生成notebook而非inline代码** - 用户偏好.ipynb文件在Jupyter中交互执行
2. **提交前验证** - 检查类型匹配、API兼容性、变量引用
3. **中文环境** - 所有标签/报告使用中文，确保matplotlib字体支持
4. **不要在chat中输出代码** - 直接生成文件

### 附属资源

```
lgbm-modeling-cn/
├── SKILL.md                      # 本文档（177行）
├── references/
│   ├── code_templates.md          # 各步骤完整代码模板
│   └── pitfalls.md                # 踩坑指南与调试手册
```
