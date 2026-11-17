# 常见踩坑与调试指南

来自权益购买预测模型项目的真实经验。以下均为开发过程中实际遇到的问题。

## 数据类型问题

### login_month 是字符串，不是整数
```python
# 错误写法 — 结果为空 DataFrame：
df[df['login_month'].isin([202603, 202604])]

# 正确写法：
df[df['login_month'].isin(['2026-03', '2026-04'])]
```
**症状**：`train_test_split` 报 `n_samples=0` 错误，或训练集为空。

### PyArrow cast vs Pandas astype
600+ 列 × 80 万行数据，`df.astype('float64')` 可能需要 10 分钟以上。

```python
# 慢（大数据集 10 分钟以上）：
for col in model_cols:
    df[col] = df[col].astype('float64')

# 快（几秒完成）：
table = pq.read_table(DATA_PATH, columns=cols_needed)
new_fields = [pa.field(f.name, pa.float64()) if f.name in model_cols else f 
              for f in table.schema]
df = table.cast(pa.schema(new_fields)).to_pandas()
```

### Schema 列名校验
使用 pyarrow 读取指定列时，必须先检查 schema 中列是否存在：
```python
# 可能失败：列不存在时直接报错
table = pq.read_table(DATA_PATH, columns=['col1', 'nonexistent_col'])

# 安全写法：
parquet_file = pq.ParquetFile(DATA_PATH)
available_cols = [f.name for f in parquet_file.schema_arrow]
cols_needed = [c for c in desired_cols if c in available_cols]
```

## 缺失值处理

### 仅处理数值型 — 不要添加字符串类别
当所有模型变量已转为 float64 时，仅替换数值型缺失值：

```python
# 正确 — 仅数值型缺失值：
MISSING_VALUES = [-99, -8888, -9999997, -9999, -98, -97, -96]
df = df.replace(MISSING_VALUES, np.nan)

# 错误 — 数据已是 float64 时混入字符串类别：
MISSING_VALUES = ['nan', 'missing', 'NA', -99, -8888, ...]
# 会导致类型问题和无意义的替换
```

## 统计筛选逻辑

### Spearman 相关性：使用 >= 0.5，不要用 abs() >= 0.5
**这是项目中实际发现的关键 bug。**

```python
# 错误 — 会放过反向趋势变量（rho 接近 -1）：
passed = result_df[result_df['spearman_corr'].abs() >= 0.5]

# 正确 — 仅保留正向一致的变量：
passed = result_df[result_df['spearman_corr'] >= 0.5]
```

**症状**：Bivar 图中 Train 和 OOT 的 bad_rate 趋势方向相反。
**根因**：`abs(-0.9) = 0.9 >= 0.5` 会把强负相关变量也放过。

### Pearson 相关性：使用 abs() > 0.9
高相关（正向或反向）均表示变量冗余，应剔除重要性较低的一方。

```python
# 正确 — 无论正负方向，高相关对均为冗余：
if abs(corr_matrix.iloc[i, j]) > 0.9:
    # 剔除重要性较低的变量

# 注意：与 Spearman（Step 6）不同，Spearman 用 >= 0.5 不加 abs()。
# Spearman 检验 Train-OOT 趋势一致性（方向重要）。
# Pearson 检验特征冗余性（幅度重要，方向不重要）。
```

### 步骤顺序：Step 7 必须在 Step 6 之后
相关性筛选（Step 7）必须基于通过一致性检验（Step 6）的变量集合执行。
在错误的输入集上执行 Step 7 会导致变量计数不正确。

## LightGBM API 兼容性

### Early Stopping（旧版 vs 4.6.0+）
```python
# 4.6.0+ 正确写法（使用 callbacks）：
import lightgbm as lgb
model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)],
          eval_metric='auc',
          callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(50)])

# 旧版写法（Anaconda Automan 等环境，callbacks 对象不存在）：
model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)],
          eval_metric='auc', early_stopping_rounds=50, verbose=0)

# 错误写法 — 旧版中这些对象不存在：
from lightgbm import early_stopping, log_evaluation  # ImportError!
callbacks=[early_stopping(50), log_evaluation(50)]     # AttributeError!

# 也是错误写法 — 传 dict 给 callbacks：
callbacks=[{'early_stopping_rounds': 50}]  # 'dict' has no attribute '__dict__'
```

### 预测时使用 best_iteration_
```python
# Early stopping 后预测务必使用 best_iteration_：
pred = model.predict_proba(X, num_iteration=model.best_iteration_)[:, 1]
```

## Optuna 调参

### 对数尺度下界必须 > 0
```python
# 错误 — 会触发 ValueError：
trial.suggest_float('reg_alpha', 0, 10, log=True)  # 对数尺度不允许 low=0

# 正确：
trial.suggest_float('reg_alpha', 0.01, 10, log=True)
```

### 调参耗时预估
- 80 trials × 300 trees ≈ 10-20 分钟（170 变量 × 20 万训练样本）
- 进度条初期可能长时间显示 0% — 这是正常的（第一个 trial 在编译）

## Lift 计算

**项目中此定义被用户多次纠正。**

```python
# 正确 — Lift 相对于整体 bad_rate：
lift = bin_bad_rate / overall_bad_rate

# 错误 — Lift 相对于最低箱：
lift = bin_bad_rate / min_bin_bad_rate
```

适用于：Gains Table、月度分析、PSI 分布表。

## Notebook 生成

### 多行代码单元格
程序化生成 .ipynb 文件时，`source` 字段必须是列表，每个元素为一行：

```python
# 正确 — 每行一个元素：
"source": [
    "import pandas as pd\n",
    "import numpy as np\n",
    "\n",
    "DATA_PATH = r'path/to/data.parquet'\n"
]

# 错误 — 所有代码塞进一个字符串（Jupyter 中显示为一行）：
"source": ["import pandas as pd\nimport numpy as np\n\nDATA_PATH = r'path/to/data.parquet'\n"]
```

### 在 Jupyter 中打开 Notebook
```powershell
# 使用 Start-Process，隐藏窗口：
Start-Process "jupyter" -ArgumentList "notebook","path/to/file.ipynb" -WindowStyle Hidden
```

## 模型评估

### Bivar 图坐标轴
- 蓝色柱 = 样本数，左侧 Y 轴
- 红色线 = Bad Rate，右侧 Y 轴
- 不要搞反（初期曾犯过此错误）

### Bivar 图中的缺失值
始终将缺失值作为单独一箱，标注"缺失值"，置于首位（在所有数值箱之前）。

### Train vs OOT 分箱
始终使用 Train 的分箱边界对 OOT 分箱，确保可比性：
```python
# 仅从 Train 计算分箱边界
edges = np.percentile(train_vals[~np.isnan(train_vals)], np.linspace(0, 100, n_bins + 1))
# 用相同边界对 OOT 分箱
oot_bin = np.digitize(oot_vals, edges[1:-1])
```