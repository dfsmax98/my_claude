# 变量筛选代码模板

各步骤完整代码模板。根据项目实际情况修改路径和参数。

## 数据加载模板（PyArrow 加速）

```python
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import time

DATA_PATH = r'<parquet文件路径>'
TARGET = '<目标变量列名>'
EXCLUDE_COLS = ['cust_no', 'close_date', 'login_date', 'login_month', '<旧目标变量>']

# 读取 schema 获取所有列名
parquet_file = pq.ParquetFile(DATA_PATH)
all_cols = [f.name for f in parquet_file.schema_arrow]
model_cols = [c for c in all_cols if c not in EXCLUDE_COLS + [TARGET]]

# 使用 pyarrow cast 快速加载（比 pandas astype 快 10 倍）
cols_needed = model_cols + ['login_month', TARGET]
table = pq.read_table(DATA_PATH, columns=cols_needed)
new_fields = []
for f in table.schema:
    if f.name in model_cols:
        new_fields.append(pa.field(f.name, pa.float64()))
    else:
        new_fields.append(f)
df = table.cast(pa.schema(new_fields)).to_pandas()

# 仅替换数值型缺失值（LGBM 原生支持 NaN）
MISSING_VALUES = [-99, -8888, -9999997, -9999, -98, -97, -96]
for col in model_cols:
    df[col] = df[col].replace(MISSING_VALUES, np.nan)
```

## 样本划分模板

```python
# login_month 是字符串：'2026-03', '2026-04' 等
train_months = ['<M1>', '<M2>']  # 例：['2026-03', '2026-04']
oot_months = ['<M3>', '<M4>']    # 例：['2026-05', '2026-06']

df_train_all = df[df['login_month'].isin(train_months)].copy()
df_oot = df[df['login_month'].isin(oot_months)].copy()

from sklearn.model_selection import train_test_split
train_idx, valid_idx = train_test_split(
    range(len(df_train_all)), test_size=0.2, random_state=42,
    stratify=df_train_all[TARGET]
)
df_train = df_train_all.iloc[train_idx].copy()
df_valid = df_train_all.iloc[valid_idx].copy()
```

## PSI 计算模板

```python
def calc_psi_per_variable(base_arr, test_arr, n_bins=10):
    """计算单个变量的 PSI。base_arr 和 test_arr 为一维 numpy 数组。"""
    base_valid = base_arr[~np.isnan(base_arr)]
    if len(base_valid) < 100:
        return np.nan
    
    bp = np.unique(np.quantile(base_valid, np.linspace(0, 1, n_bins + 1)))
    if len(bp) < 3:
        return np.nan
    
    base_hist, _ = np.histogram(base_valid, bins=bp)
    base_pct = np.clip(base_hist / len(base_valid), 1e-4, None)
    
    test_valid = test_arr[~np.isnan(test_arr)]
    if len(test_valid) < 100:
        return np.nan
    
    test_hist, _ = np.histogram(test_valid, bins=bp)
    test_pct = np.clip(test_hist / len(test_valid), 1e-4, None)
    
    return np.sum((test_pct - base_pct) * np.log(test_pct / base_pct))
```

## IV 计算模板

```python
def calculate_iv(x, y, n_bins=10):
    """计算单个变量的 Information Value（IV 值）。"""
    try:
        bins = pd.qcut(x, n_bins, duplicates="drop")
    except ValueError:
        return 0.0
    
    df_temp = pd.DataFrame({'x': bins, 'y': y})
    grouped = df_temp.groupby('x')['y'].agg(['sum', 'count'])
    grouped.columns = ['bad', 'total']
    
    total_bad = grouped['bad'].sum()
    total_good = grouped['total'].sum() - total_bad
    if total_bad == 0 or total_good == 0:
        return 0.0
    
    grouped['bad_pct'] = np.clip(grouped['bad'] / total_bad, 1e-4, None)
    grouped['good_pct'] = np.clip((grouped['total'] - grouped['bad']) / total_good, 1e-4, None)
    grouped['woe'] = np.log(grouped['good_pct'] / grouped['bad_pct'])
    grouped['iv'] = (grouped['good_pct'] - grouped['bad_pct']) * grouped['woe']
    return grouped['iv'].sum()
```

## Bad Rate 一致性检验模板

```python
from scipy.stats import spearmanr

def calc_bad_rate_consistency(train_vals, oot_vals, train_label, oot_label, n_bins=10):
    """检验 Train 与 OOT 的 bad_rate 趋势是否一致。"""
    valid_mask = ~np.isnan(train_vals)
    if valid_mask.sum() < 100:
        return None
    
    valid_train = train_vals[valid_mask]
    edges = np.unique(np.percentile(valid_train, np.linspace(0, 100, n_bins + 1)))
    if len(edges) < 4:
        return None
    
    train_bin = np.digitize(train_vals, edges[1:-1])
    oot_bin = np.digitize(oot_vals, edges[1:-1])
    
    train_br, oot_br = [], []
    n_bins_actual = int(max(train_bin.max(), oot_bin.max())) + 1
    for b in range(n_bins_actual):
        t_mask = (train_bin == b) & (~np.isnan(train_vals))
        o_mask = (oot_bin == b) & (~np.isnan(oot_vals))
        if t_mask.sum() < 10 or o_mask.sum() < 10:
            continue
        train_br.append(train_label[t_mask].mean())
        oot_br.append(oot_label[o_mask].mean())
    
    if len(train_br) < 4:
        return None
    
    rho, pval = spearmanr(train_br, oot_br)
    return {'spearman_corr': rho, 'p_value': pval, 'n_bins': len(train_br)}

# 关键：使用 rho >= 0.5（仅正向），不要使用 abs(rho) >= 0.5
passed = result_df[result_df['spearman_corr'] >= 0.5]
```

## Pearson 相关性筛选模板

```python
# 计算相关系数矩阵
corr_matrix = df[passed_vars].corr(method='pearson')

# 提取上三角变量对
pairs = []
for i in range(len(passed_vars)):
    for j in range(i + 1, len(passed_vars)):
        if abs(corr_matrix.iloc[i, j]) > 0.9:
            pairs.append((passed_vars[i], passed_vars[j], corr_matrix.iloc[i, j]))

# 每对中剔除重要性较低的变量
importance_dict = dict(zip(imp_df['variable'], imp_df['importance']))
to_drop = set()
for v1, v2, corr in sorted(pairs, key=lambda x: -abs(x[2])):
    if v1 not in to_drop and v2 not in to_drop:
        if importance_dict.get(v1, 0) < importance_dict.get(v2, 0):
            to_drop.add(v1)
        else:
            to_drop.add(v2)

final_vars = [v for v in passed_vars if v not in to_drop]
```

## 变量精简模板

```python
import lightgbm as lgb
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score

# 构建变量名到列索引的映射
var_idx = {v: i for i, v in enumerate(all_model_vars)}

def train_and_eval(vars_list):
    """训练 LGBM 并返回模型 + 各数据集 AUC。"""
    params = best_params.copy()
    params.update({'objective': 'binary', 'metric': 'auc', 'boosting_type': 'gbdt',
                   'n_estimators': 300, 'random_state': 42, 'verbose': -1})
    mdl = LGBMClassifier(**params)
    col_idx = [var_idx[v] for v in vars_list]
    mdl.fit(X_tr[:, col_idx], y_tr,
            eval_set=[(X_va[:, col_idx], y_va)],
            eval_metric='auc',
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)])
    pred_tr = mdl.predict_proba(X_tr[:, col_idx],
                                 num_iteration=mdl.best_iteration_)[:, 1]
    pred_va = mdl.predict_proba(X_va[:, col_idx],
                                 num_iteration=mdl.best_iteration_)[:, 1]
    pred_oo = mdl.predict_proba(X_oo[:, col_idx],
                                 num_iteration=mdl.best_iteration_)[:, 1]
    return mdl, roc_auc_score(y_tr, pred_tr), roc_auc_score(y_va, pred_va), roc_auc_score(y_oo, pred_oo)

DROP_PER_ROUND = 10
AUC_DROP_THRESHOLD = 0.005

current_vars = model_vars.copy()
prev_auc = None
while len(current_vars) > 20:
    dropped = current_vars[-DROP_PER_ROUND:]
    test_vars = current_vars[:-DROP_PER_ROUND]
    _, auc_tr, auc_va, auc_oo = train_and_eval(test_vars)
    if prev_auc is not None:
        auc_drop = prev_auc - auc_va
        if auc_drop > AUC_DROP_THRESHOLD:
            break  # 保留当前变量集
    prev_auc = auc_va
    current_vars = test_vars
```

## Bivar 分析图模板

```python
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

def plot_bivar(df_train, df_oot, var, cn_name, target, n_bins=5):
    """绘制 bivar 分析图：Train vs OOT，蓝色柱=样本数，红色线=Bad Rate。
    NaN 值不参与分箱，单独显示为"缺失值"箱。
    """
    train_vals = df_train[var].values
    valid_mask = ~np.isnan(train_vals)
    if valid_mask.sum() < 50:
        return None
    
    edges = np.unique(np.percentile(train_vals[valid_mask], np.linspace(0, 100, n_bins + 1)))
    if len(edges) < 3:
        return None
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    for ax, vals, label_vals, title in [
        (ax1, train_vals, df_train[target].values, 'Train'),
        (ax2, df_oot[var].values.astype(float), df_oot[target].values, 'OOT')
    ]:
        stats = []
        nan_mask = np.isnan(vals)
        
        # 缺失值箱置于首位
        if nan_mask.sum() > 0:
            stats.append(('缺失值', int(nan_mask.sum()), float(label_vals[nan_mask].mean())))
        
        # 仅对非 NaN 值执行 digitize，避免 NaN 被错误归入第一个数值箱（双重计数）
        valid_vals = vals[~nan_mask]
        valid_labels = label_vals[~nan_mask]
        bin_idx = np.digitize(valid_vals, edges[1:-1])
        
        for b in range(len(edges) - 1):
            mask = bin_idx == b
            if mask.sum() < 1:
                continue
            lo, hi = edges[b], edges[b + 1]
            bracket = ']' if b == len(edges) - 2 else ')'
            label = f'[{lo:.4g}, {hi:.4g}{bracket}'
            stats.append((label, int(mask.sum()), float(valid_labels[mask].mean())))
        
        if not stats:
            continue
        
        labels, counts, bad_rates = zip(*stats)
        x = range(len(stats))
        
        ax_twin = ax.twinx()
        ax.bar(x, counts, alpha=0.6, color='steelblue', label='样本数')
        ax_twin.plot(x, bad_rates, color='red', marker='o', linewidth=2, label='Bad Rate')
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=9)
        ax.set_ylabel('样本数')
        ax_twin.set_ylabel('Bad Rate', color='red')
        ax.set_title(f'{var} ({cn_name}) - {title}', fontsize=12)
    
    plt.tight_layout()
    return fig
```