"""
信贷行业数据分析核心Python代码
包含数据清洗、探索性分析、特征工程、模型训练等完整流程
适用于信贷风险分析、客户细分、违约预测等场景
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (classification_report, confusion_matrix,
                           roc_auc_score, roc_curve, precision_recall_curve)
import warnings
warnings.filterwarnings('ignore')

# 设置中文显示和图形样式
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")

# ============================================================================
# 1. 数据加载与清洗
# ============================================================================

def load_credit_data(file_path, sample_size=None):
    """
    加载信贷数据文件

    参数:
    file_path: 数据文件路径（支持CSV、Excel等格式）
    sample_size: 抽样大小（用于大数据集快速测试）

    返回:
    df: 加载的DataFrame
    """
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith('.xlsx') or file_path.endswith('.xls'):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("仅支持CSV和Excel格式文件")

    if sample_size and len(df) > sample_size:
        df = df.sample(sample_size, random_state=42)

    print(f"✅ 数据加载完成，形状: {df.shape}")
    print(f"📊 列名: {df.columns.tolist()}")
    return df


def explore_data(df, max_categories=20):
    """
    数据探索性分析

    参数:
    df: DataFrame
    max_categories: 分类变量最大类别数
    """
    print("=" * 60)
    print("数据探索性分析报告")
    print("=" * 60)

    # 基本统计信息
    print("\n📈 1. 数据基本信息:")
    print(f"   行数: {df.shape[0]}, 列数: {df.shape[1]}")
    print(f"   内存使用: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

    # 数据类型分布
    print("\n📊 2. 数据类型分布:")
    dtype_counts = df.dtypes.value_counts()
    for dtype, count in dtype_counts.items():
        print(f"   {dtype}: {count}列")

    # 缺失值分析
    print("\n⚠️ 3. 缺失值分析:")
    missing_stats = df.isnull().sum()
    missing_stats = missing_stats[missing_stats > 0]
    if len(missing_stats) > 0:
        for col, count in missing_stats.items():
            percentage = count / len(df) * 100
            print(f"   {col}: {count}个缺失值 ({percentage:.2f}%)")
    else:
        print("   无缺失值 ✓")

    # 数值型变量统计
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) > 0:
        print(f"\n🔢 4. 数值型变量 ({len(numeric_cols)}个):")
        numeric_stats = df[numeric_cols].describe().T
        print(numeric_stats[['mean', 'std', 'min', '50%', 'max']].round(2))

    # 分类变量统计
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns
    if len(categorical_cols) > 0:
        print(f"\n🏷️ 5. 分类变量 ({len(categorical_cols)}个):")
        for col in categorical_cols:
            unique_count = df[col].nunique()
            if unique_count <= max_categories:
                print(f"   {col}: {unique_count}个唯一值")
                print(f"     最常见值: {df[col].mode().iloc[0]} ({df[col].value_counts().iloc[0]/len(df)*100:.1f}%)")
            else:
                print(f"   {col}: {unique_count}个唯一值 (太多，可能为ID或文本字段)")

    return {
        'numeric_cols': list(numeric_cols),
        'categorical_cols': list(categorical_cols),
        'missing_cols': list(missing_stats.index)
    }


def clean_credit_data(df, target_col=None):
    """
    清洗信贷数据

    参数:
    df: 原始DataFrame
    target_col: 目标变量列名

    返回:
    cleaned_df: 清洗后的DataFrame
    """
    cleaned_df = df.copy()
    original_shape = cleaned_df.shape

    print("=" * 60)
    print("数据清洗流程")
    print("=" * 60)

    # 1. 处理缺失值
    print("\n1️⃣ 处理缺失值:")
    for col in cleaned_df.columns:
        if cleaned_df[col].isnull().sum() > 0:
            # 根据数据类型选择填充方法
            if cleaned_df[col].dtype in [np.float64, np.int64]:
                if col == target_col and target_col is not None:
                    # 目标变量有缺失，删除这些行
                    cleaned_df = cleaned_df.dropna(subset=[col])
                    print(f"   {col}: 删除目标变量缺失的行")
                else:
                    # 数值变量用中位数填充
                    median_val = cleaned_df[col].median()
                    cleaned_df[col].fillna(median_val, inplace=True)
                    print(f"   {col}: 用中位数填充 ({median_val:.2f})")
            else:
                # 分类变量用众数填充
                mode_val = cleaned_df[col].mode()[0] if not cleaned_df[col].mode().empty else 'Unknown'
                cleaned_df[col].fillna(mode_val, inplace=True)
                print(f"   {col}: 用众数填充 ('{mode_val}')")

    # 2. 处理异常值（仅对数值变量）
    print("\n2️⃣ 处理异常值 (IQR方法):")
    numeric_cols = cleaned_df.select_dtypes(include=[np.number]).columns
    outliers_count = 0

    for col in numeric_cols:
        if col == target_col:
            continue

        Q1 = cleaned_df[col].quantile(0.25)
        Q3 = cleaned_df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        # 检测异常值数量
        outliers = cleaned_df[(cleaned_df[col] < lower_bound) | (cleaned_df[col] > upper_bound)]
        if len(outliers) > 0:
            outliers_count += len(outliers)
            # 将异常值缩放到边界
            cleaned_df[col] = cleaned_df[col].clip(lower_bound, upper_bound)
            print(f"   {col}: 发现{len(outliers)}个异常值，已缩放到边界")

    if outliers_count == 0:
        print("   未发现明显异常值")

    # 3. 删除常量列
    print("\n3️⃣ 删除常量列:")
    constant_cols = []
    for col in cleaned_df.columns:
        if cleaned_df[col].nunique() <= 1:
            constant_cols.append(col)

    if constant_cols:
        cleaned_df = cleaned_df.drop(columns=constant_cols)
        print(f"   删除常量列: {constant_cols}")
    else:
        print("   无常量列")

    # 4. 删除高基数分类变量（可选）
    print("\n4️⃣ 处理高基数分类变量:")
    categorical_cols = cleaned_df.select_dtypes(include=['object']).columns
    high_cardinality_cols = []

    for col in categorical_cols:
        unique_count = cleaned_df[col].nunique()
        if unique_count > 50:  # 阈值可调整
            high_cardinality_cols.append((col, unique_count))

    if high_cardinality_cols:
        print("   高基数分类变量:")
        for col, count in high_cardinality_cols:
            print(f"     {col}: {count}个唯一值")
        print("   建议: 考虑编码或删除这些列")

    print(f"\n✅ 清洗完成:")
    print(f"   原始形状: {original_shape}")
    print(f"   清洗后形状: {cleaned_df.shape}")
    print(f"   缺失值总数: {cleaned_df.isnull().sum().sum()}")

    return cleaned_df


# ============================================================================
# 2. 探索性数据分析 (EDA)
# ============================================================================

def plot_target_distribution(df, target_col='default'):
    """
    绘制目标变量分布

    参数:
    df: DataFrame
    target_col: 目标变量列名
    """
    if target_col not in df.columns:
        print(f"警告: 目标变量 '{target_col}' 不存在")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 饼图
    target_counts = df[target_col].value_counts()
    colors = ['#4CAF50', '#F44336'] if len(target_counts) == 2 else None
    axes[0].pie(target_counts.values, labels=target_counts.index,
                autopct='%1.1f%%', colors=colors, startangle=90)
    axes[0].set_title(f'{target_col} 分布')

    # 条形图
    bars = axes[1].bar(target_counts.index.astype(str), target_counts.values)
    axes[1].set_xlabel(target_col)
    axes[1].set_ylabel('计数')
    axes[1].set_title(f'{target_col} 计数分布')

    # 在条形上添加数值
    for bar in bars:
        height = bar.get_height()
        axes[1].text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{int(height)}', ha='center', va='bottom')

    plt.tight_layout()
    plt.show()

    # 打印统计信息
    print(f"{target_col} 分布:")
    for value, count in target_counts.items():
        percentage = count / len(df) * 100
        label = '违约' if value == 1 else '正常' if value == 0 else str(value)
        print(f"  {label}: {count} ({percentage:.2f}%)")


def plot_numeric_distributions(df, numeric_cols=None, max_cols=6):
    """
    绘制数值变量分布

    参数:
    df: DataFrame
    numeric_cols: 数值变量列表（如为None，则自动选择）
    max_cols: 最大显示列数
    """
    if numeric_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    # 限制显示的列数
    if len(numeric_cols) > max_cols:
        print(f"数值变量过多 ({len(numeric_cols)})，仅显示前{max_cols}个")
        numeric_cols = numeric_cols[:max_cols]

    n_cols = min(3, len(numeric_cols))
    n_rows = (len(numeric_cols) + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5*n_cols, 4*n_rows))
    axes = axes.flatten() if n_rows > 1 or n_cols > 1 else [axes]

    for idx, col in enumerate(numeric_cols):
        if idx >= len(axes):
            break

        # 直方图
        axes[idx].hist(df[col].dropna(), bins=30, edgecolor='black', alpha=0.7, color='skyblue')
        axes[idx].set_xlabel(col)
        axes[idx].set_ylabel('频数')
        axes[idx].set_title(f'{col} 分布')

        # 添加统计线
        mean_val = df[col].mean()
        median_val = df[col].median()
        axes[idx].axvline(mean_val, color='red', linestyle='--', linewidth=1, label=f'均值: {mean_val:.2f}')
        axes[idx].axvline(median_val, color='green', linestyle='--', linewidth=1, label=f'中位数: {median_val:.2f}')
        axes[idx].legend(fontsize=8)

    # 隐藏多余的子图
    for idx in range(len(numeric_cols), len(axes)):
        axes[idx].set_visible(False)

    plt.tight_layout()
    plt.show()


def plot_correlation_heatmap(df, numeric_cols=None):
    """
    绘制相关性热力图

    参数:
    df: DataFrame
    numeric_cols: 数值变量列表
    """
    if numeric_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if len(numeric_cols) < 2:
        print("数值变量不足，无法计算相关性")
        return

    corr_matrix = df[numeric_cols].corr()

    plt.figure(figsize=(10, 8))
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
    sns.heatmap(corr_matrix, mask=mask, annot=True, fmt='.2f',
                cmap='coolwarm', center=0, square=True,
                cbar_kws={"shrink": 0.8})
    plt.title('特征相关性热力图')
    plt.tight_layout()
    plt.show()

    # 找出强相关特征对
    print("强相关特征对 (|r| > 0.7):")
    strong_corr_pairs = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i+1, len(corr_matrix.columns)):
            corr_value = corr_matrix.iloc[i, j]
            if abs(corr_value) > 0.7:
                col1, col2 = corr_matrix.columns[i], corr_matrix.columns[j]
                strong_corr_pairs.append((col1, col2, corr_value))

    if strong_corr_pairs:
        for col1, col2, corr_value in strong_corr_pairs:
            print(f"  {col1} - {col2}: {corr_value:.3f}")
    else:
        print("  无强相关特征对")


def plot_feature_vs_target(df, feature_col, target_col='default', plot_type='box'):
    """
    绘制特征与目标变量的关系

    参数:
    df: DataFrame
    feature_col: 特征列名
    target_col: 目标变量列名
    plot_type: 图形类型 ('box', 'violin', 'hist')
    """
    if feature_col not in df.columns or target_col not in df.columns:
        print(f"警告: 列 '{feature_col}' 或 '{target_col}' 不存在")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 检查特征类型
    if df[feature_col].dtype in [np.float64, np.int64]:
        # 数值特征

        if plot_type == 'box':
            # 箱线图
            data_to_plot = []
            labels = []
            for target_value in sorted(df[target_col].unique()):
                data = df[df[target_col] == target_value][feature_col].dropna()
                data_to_plot.append(data)
                labels.append(f'{target_col}={target_value}')

            axes[0].boxplot(data_to_plot, labels=labels)
            axes[0].set_ylabel(feature_col)
            axes[0].set_title(f'{feature_col} 按 {target_col} 分组箱线图')

        elif plot_type == 'violin':
            # 小提琴图
            data_to_plot = []
            labels = []
            for target_value in sorted(df[target_col].unique()):
                data = df[df[target_col] == target_value][feature_col].dropna()
                data_to_plot.append(data)
                labels.append(f'{target_col}={target_value}')

            axes[0].violinplot(data_to_plot, showmeans=True, showmedians=True)
            axes[0].set_xticks(range(1, len(labels)+1))
            axes[0].set_xticklabels(labels)
            axes[0].set_ylabel(feature_col)
            axes[0].set_title(f'{feature_col} 按 {target_col} 分组小提琴图')

        # 密度图
        for target_value in sorted(df[target_col].unique()):
            subset = df[df[target_col] == target_value][feature_col].dropna()
            sns.kdeplot(subset, label=f'{target_col}={target_value}', ax=axes[1])

        axes[1].set_xlabel(feature_col)
        axes[1].set_ylabel('密度')
        axes[1].set_title(f'{feature_col} 按 {target_col} 分组密度图')
        axes[1].legend()

    else:
        # 分类特征 - 条形图
        cross_tab = pd.crosstab(df[feature_col], df[target_col], normalize='index')
        cross_tab.plot(kind='bar', stacked=True, ax=axes[0])
        axes[0].set_xlabel(feature_col)
        axes[0].set_ylabel('比例')
        axes[0].set_title(f'{feature_col} 与 {target_col} 关系')
        axes[0].legend(title=target_col)

        # 分类特征 - 频率图
        value_counts = df[feature_col].value_counts().head(10)  # 显示前10个
        bars = axes[1].bar(range(len(value_counts)), value_counts.values)
        axes[1].set_xticks(range(len(value_counts)))
        axes[1].set_xticklabels(value_counts.index, rotation=45, ha='right')
        axes[1].set_xlabel(feature_col)
        axes[1].set_ylabel('计数')
        axes[1].set_title(f'{feature_col} 频数分布 (前10)')

    plt.tight_layout()
    plt.show()


def perform_comprehensive_eda(df, target_col='default', sample_size=10000):
    """
    执行全面的探索性数据分析

    参数:
    df: DataFrame
    target_col: 目标变量列名
    sample_size: 抽样大小（大数据集时使用）
    """
    print("=" * 60)
    print("探索性数据分析 (EDA)")
    print("=" * 60)

    # 抽样（如果数据太大）
    if len(df) > sample_size:
        print(f"数据过大 ({len(df)}行)，使用{sample_size}行样本进行分析")
        df_sample = df.sample(sample_size, random_state=42)
    else:
        df_sample = df

    # 1. 目标变量分析
    if target_col in df_sample.columns:
        print(f"\n🎯 目标变量分析: {target_col}")
        plot_target_distribution(df_sample, target_col)

    # 2. 数值变量分析
    numeric_cols = df_sample.select_dtypes(include=[np.number]).columns.tolist()
    if target_col in numeric_cols:
        numeric_cols.remove(target_col)

    if numeric_cols:
        print(f"\n🔢 数值变量分析 ({len(numeric_cols)}个变量)")
        plot_numeric_distributions(df_sample, numeric_cols)

        # 选择几个重要特征与目标变量关系
        if target_col in df_sample.columns and len(numeric_cols) > 0:
            print(f"\n📊 重要特征与 {target_col} 关系:")
            important_features = numeric_cols[:min(4, len(numeric_cols))]
            for feature in important_features:
                plot_feature_vs_target(df_sample, feature, target_col, plot_type='box')

    # 3. 相关性分析
    if len(numeric_cols) >= 2:
        print(f"\n🔗 相关性分析")
        plot_correlation_heatmap(df_sample, numeric_cols)

    # 4. 分类变量分析
    categorical_cols = df_sample.select_dtypes(include=['object', 'category']).columns.tolist()
    if categorical_cols:
        print(f"\n🏷️ 分类变量分析 ({len(categorical_cols)}个变量)")

        # 显示每个分类变量的基本信息
        for col in categorical_cols[:5]:  # 只显示前5个
            unique_count = df_sample[col].nunique()
            print(f"  {col}: {unique_count}个唯一值")

            if unique_count <= 10 and target_col in df_sample.columns:
                plot_feature_vs_target(df_sample, col, target_col)

    print("\n✅ EDA完成")


# ============================================================================
# 3. 特征工程
# ============================================================================

def create_credit_features(df, target_col='default'):
    """
    创建信贷业务相关特征

    参数:
    df: DataFrame
    target_col: 目标变量列名

    返回:
    df_with_features: 包含新特征的DataFrame
    """
    df_with_features = df.copy()
    original_cols = set(df.columns)

    print("=" * 60)
    print("特征工程")
    print("=" * 60)

    # 1. 基础比率特征
    print("\n1️⃣ 创建比率特征:")

    # 负债收入比 (DTI)
    if all(col in df.columns for col in ['monthly_debt', 'monthly_income']):
        df_with_features['dti_ratio'] = df_with_features['monthly_debt'] / df_with_features['monthly_income']
        df_with_features['dti_ratio'] = df_with_features['dti_ratio'].replace([np.inf, -np.inf], np.nan)
        df_with_features['dti_ratio'].fillna(df_with_features['dti_ratio'].median(), inplace=True)
        print(f"  负债收入比 (DTI): 已创建")

    # 贷款收入比 (LTI)
    if all(col in df.columns for col in ['loan_amount', 'monthly_income']):
        df_with_features['lti_ratio'] = df_with_features['loan_amount'] / df_with_features['monthly_income']
        df_with_features['lti_ratio'] = df_with_features['lti_ratio'].replace([np.inf, -np.inf], np.nan)
        df_with_features['lti_ratio'].fillna(df_with_features['lti_ratio'].median(), inplace=True)
        print(f"  贷款收入比 (LTI): 已创建")

    # 月供收入比 (PTI)
    if all(col in df.columns for col in ['monthly_payment', 'monthly_income']):
        df_with_features['pti_ratio'] = df_with_features['monthly_payment'] / df_with_features['monthly_income']
        df_with_features['pti_ratio'] = df_with_features['pti_ratio'].replace([np.inf, -np.inf], np.nan)
        df_with_features['pti_ratio'].fillna(df_with_features['pti_ratio'].median(), inplace=True)
        print(f"  月供收入比 (PTI): 已创建")

    # 2. 分组特征
    print("\n2️⃣ 创建分组特征:")

    # 年龄分组
    if 'age' in df.columns:
        bins = [0, 25, 35, 45, 55, 65, 100]
        labels = ['18-25', '26-35', '36-45', '46-55', '56-65', '65+']
        df_with_features['age_group'] = pd.cut(df_with_features['age'], bins=bins, labels=labels, right=False)
        print(f"  年龄分组: 已创建")

    # 收入分组
    if 'monthly_income' in df.columns:
        income_bins = [0, 3000, 6000, 10000, 20000, 50000, float('inf')]
        income_labels = ['<3k', '3k-6k', '6k-10k', '10k-20k', '20k-50k', '>50k']
        df_with_features['income_group'] = pd.cut(df_with_features['monthly_income'],
                                                  bins=income_bins,
                                                  labels=income_labels)
        print(f"  收入分组: 已创建")

    # 贷款金额分组
    if 'loan_amount' in df.columns:
        loan_bins = [0, 10000, 50000, 100000, 200000, 500000, float('inf')]
        loan_labels = ['<10k', '10k-50k', '50k-100k', '100k-200k', '200k-500k', '>500k']
        df_with_features['loan_group'] = pd.cut(df_with_features['loan_amount'],
                                                bins=loan_bins,
                                                labels=loan_labels)
        print(f"  贷款金额分组: 已创建")

    # 3. 时间相关特征
    print("\n3️⃣ 创建时间特征:")

    # 如果存在日期字段
    date_columns = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
    for date_col in date_columns[:2]:  # 只处理前两个日期字段
        try:
            if df[date_col].dtype == 'object':
                df_with_features[date_col] = pd.to_datetime(df_with_features[date_col], errors='coerce')

            if df_with_features[date_col].dtype == 'datetime64[ns]':
                # 提取日期组件
                df_with_features[f'{date_col}_year'] = df_with_features[date_col].dt.year
                df_with_features[f'{date_col}_month'] = df_with_features[date_col].dt.month
                df_with_features[f'{date_col}_day'] = df_with_features[date_col].dt.day
                df_with_features[f'{date_col}_weekday'] = df_with_features[date_col].dt.weekday

                print(f"  从 {date_col} 提取时间特征: 年、月、日、星期")
        except:
            print(f"  无法从 {date_col} 提取时间特征")

    # 4. 交互特征
    print("\n4️⃣ 创建交互特征:")

    # 年龄与收入的交互
    if 'age' in df.columns and 'monthly_income' in df.columns:
        df_with_features['age_income_interaction'] = df_with_features['age'] * df_with_features['monthly_income']
        print(f"  年龄×收入交互: 已创建")

    # 贷款金额与期限的交互
    if 'loan_amount' in df.columns and 'loan_term' in df.columns:
        df_with_features['loan_amount_term_interaction'] = df_with_features['loan_amount'] * df_with_features['loan_term']
        print(f"  贷款金额×期限交互: 已创建")

    # 5. 统计特征
    print("\n5️⃣ 创建统计特征:")

    # 如果有多个数值特征，可以创建聚合统计
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if target_col in numeric_cols:
        numeric_cols.remove(target_col)

    if len(numeric_cols) > 3:
        df_with_features['numeric_features_mean'] = df_with_features[numeric_cols].mean(axis=1)
        df_with_features['numeric_features_std'] = df_with_features[numeric_cols].std(axis=1)
        print(f"  数值特征均值和标准差: 已创建")

    # 计算新增特征数量
    new_features = [col for col in df_with_features.columns if col not in original_cols]
    print(f"\n✅ 特征工程完成:")
    print(f"   新增特征数量: {len(new_features)}")
    print(f"   特征总数: {len(df_with_features.columns)}")
    print(f"   新增特征: {new_features}")

    return df_with_features


def encode_categorical_features(df, categorical_cols=None, method='label'):
    """
    编码分类特征

    参数:
    df: DataFrame
    categorical_cols: 分类特征列表（如为None，则自动选择）
    method: 编码方法 ('label', 'onehot', 'target')

    返回:
    encoded_df: 编码后的DataFrame
    encoder: 编码器对象（用于后续数据）
    """
    encoded_df = df.copy()
    encoders = {}

    if categorical_cols is None:
        categorical_cols = encoded_df.select_dtypes(include=['object', 'category']).columns.tolist()

    if not categorical_cols:
        print("无分类特征需要编码")
        return encoded_df, None

    print(f"编码 {len(categorical_cols)} 个分类特征，使用 {method} 编码:")

    for col in categorical_cols:
        if col not in encoded_df.columns:
            print(f"  警告: {col} 不在DataFrame中")
            continue

        if method == 'label':
            # 标签编码
            encoder = LabelEncoder()
            encoded_df[col] = encoder.fit_transform(encoded_df[col].astype(str))
            encoders[col] = encoder
            print(f"  {col}: 标签编码完成 ({encoded_df[col].nunique()}个类别)")

        elif method == 'onehot':
            # One-Hot编码（注意：会创建新列）
            dummies = pd.get_dummies(encoded_df[col], prefix=col, drop_first=True)
            encoded_df = pd.concat([encoded_df.drop(columns=[col]), dummies], axis=1)
            encoders[col] = 'onehot'
            print(f"  {col}: One-Hot编码完成 ({dummies.shape[1]}个新列)")

        elif method == 'target':
            # 目标编码（需要目标变量）
            print(f"  {col}: 目标编码需要目标变量，跳过")

    print(f"\n✅ 编码完成，形状: {encoded_df.shape}")
    return encoded_df, encoders


# ============================================================================
# 4. 模型训练与评估
# ============================================================================

def prepare_model_data(df, target_col='default', test_size=0.2, random_state=42):
    """
    准备模型训练数据

    参数:
    df: DataFrame
    target_col: 目标变量列名
    test_size: 测试集比例
    random_state: 随机种子

    返回:
    X_train, X_test, y_train, y_test, feature_cols
    """
    if target_col not in df.columns:
        raise ValueError(f"目标变量 '{target_col}' 不存在")

    # 选择特征列（排除目标变量和非数值列）
    feature_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if target_col in feature_cols:
        feature_cols.remove(target_col)

    # 确保有足够特征
    if len(feature_cols) < 1:
        # 尝试编码分类特征
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        if categorical_cols:
            df_encoded, _ = encode_categorical_features(df, categorical_cols, method='label')
            feature_cols = df_encoded.select_dtypes(include=[np.number]).columns.tolist()
            if target_col in feature_cols:
                feature_cols.remove(target_col)
            df = df_encoded
        else:
            raise ValueError("无可用特征列")

    print(f"使用 {len(feature_cols)} 个特征: {feature_cols}")

    # 准备数据
    X = df[feature_cols]
    y = df[target_col]

    # 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    print(f"数据划分:")
    print(f"  训练集: {X_train.shape[0]} 样本")
    print(f"  测试集: {X_test.shape[0]} 样本")
    print(f"  特征数: {X_train.shape[1]}")
    print(f"  目标变量分布 - 训练集: {pd.Series(y_train).value_counts().to_dict()}")
    print(f"  目标变量分布 - 测试集: {pd.Series(y_test).value_counts().to_dict()}")

    return X_train, X_test, y_train, y_test, feature_cols


def train_logistic_regression(X_train, X_test, y_train, y_test, feature_cols=None):
    """
    训练逻辑回归模型

    参数:
    X_train, X_test, y_train, y_test: 训练和测试数据
    feature_cols: 特征列名列表

    返回:
    model: 训练好的模型
    scaler: 标准化器
    metrics: 评估指标
    """
    print("=" * 60)
    print("训练逻辑回归模型")
    print("=" * 60)

    # 特征标准化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 训练模型
    model = LogisticRegression(random_state=42, max_iter=1000, class_weight='balanced')
    model.fit(X_train_scaled, y_train)

    # 预测
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)
    y_test_prob = model.predict_proba(X_test_scaled)[:, 1]

    # 评估指标
    metrics = {
        'train_report': classification_report(y_train, y_train_pred, output_dict=True),
        'test_report': classification_report(y_test, y_test_pred, output_dict=True),
        'confusion_matrix': confusion_matrix(y_test, y_test_pred),
        'auc_score': roc_auc_score(y_test, y_test_prob),
        'feature_importance': None
    }

    # 特征重要性（逻辑回归的系数）
    if feature_cols is not None:
        feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'coefficient': model.coef_[0],
            'abs_coefficient': abs(model.coef_[0])
        }).sort_values('abs_coefficient', ascending=False)

        metrics['feature_importance'] = feature_importance

    # 打印结果
    print("\n📊 训练集性能:")
    print(classification_report(y_train, y_train_pred, target_names=['正常', '违约']))

    print("\n📊 测试集性能:")
    print(classification_report(y_test, y_test_pred, target_names=['正常', '违约']))

    print(f"\n📈 AUC分数: {metrics['auc_score']:.4f}")

    if metrics['feature_importance'] is not None:
        print("\n📋 特征重要性 (前10):")
        print(metrics['feature_importance'].head(10))

    # 绘制ROC曲线
    plot_roc_curve(y_test, y_test_prob, model_name='逻辑回归')

    return model, scaler, metrics


def train_random_forest(X_train, X_test, y_train, y_test, feature_cols=None, n_estimators=100):
    """
    训练随机森林模型

    参数:
    X_train, X_test, y_train, y_test: 训练和测试数据
    feature_cols: 特征列名列表
    n_estimators: 树的数量

    返回:
    model: 训练好的模型
    metrics: 评估指标
    """
    print("=" * 60)
    print("训练随机森林模型")
    print("=" * 60)

    # 训练模型
    model = RandomForestClassifier(
        n_estimators=n_estimators,
        random_state=42,
        class_weight='balanced',
        n_jobs=-1
    )
    model.fit(X_train, y_train)

    # 预测
    y_train_pred = model.predict(X_train)
    y_test_pred = model.predict(X_test)
    y_test_prob = model.predict_proba(X_test)[:, 1]

    # 评估指标
    metrics = {
        'train_report': classification_report(y_train, y_train_pred, output_dict=True),
        'test_report': classification_report(y_test, y_test_pred, output_dict=True),
        'confusion_matrix': confusion_matrix(y_test, y_test_pred),
        'auc_score': roc_auc_score(y_test, y_test_prob),
        'feature_importance': None
    }

    # 特征重要性
    if feature_cols is not None:
        feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)

        metrics['feature_importance'] = feature_importance

    # 打印结果
    print("\n📊 训练集性能:")
    print(classification_report(y_train, y_train_pred, target_names=['正常', '违约']))

    print("\n📊 测试集性能:")
    print(classification_report(y_test, y_test_pred, target_names=['正常', '违约']))

    print(f"\n📈 AUC分数: {metrics['auc_score']:.4f}")

    if metrics['feature_importance'] is not None:
        print("\n📋 特征重要性 (前10):")
        print(metrics['feature_importance'].head(10))

        # 绘制特征重要性图
        plot_feature_importance(metrics['feature_importance'], model_name='随机森林')

    # 绘制ROC曲线
    plot_roc_curve(y_test, y_test_prob, model_name='随机森林')

    return model, metrics


def plot_roc_curve(y_true, y_prob, model_name='模型'):
    """
    绘制ROC曲线

    参数:
    y_true: 真实标签
    y_prob: 预测概率
    model_name: 模型名称
    """
    fpr, tpr, thresholds = roc_curve(y_true, y_prob)
    auc_score = roc_auc_score(y_true, y_prob)

    plt.figure(figsize=(8, 6))
    plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC曲线 (AUC = {auc_score:.3f})')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--', label='随机猜测')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('假正率 (FPR)')
    plt.ylabel('真正率 (TPR)')
    plt.title(f'{model_name} - ROC曲线')
    plt.legend(loc="lower right")
    plt.grid(True, alpha=0.3)
    plt.show()


def plot_feature_importance(feature_importance_df, top_n=15, model_name='模型'):
    """
    绘制特征重要性图

    参数:
    feature_importance_df: 特征重要性DataFrame
    top_n: 显示前N个特征
    model_name: 模型名称
    """
    # 取前top_n个特征
    top_features = feature_importance_df.head(top_n)

    plt.figure(figsize=(10, 6))
    bars = plt.barh(range(len(top_features)), top_features['importance'].values)
    plt.yticks(range(len(top_features)), top_features['feature'].values)
    plt.xlabel('特征重要性')
    plt.title(f'{model_name} - 特征重要性 (前{top_n})')
    plt.gca().invert_yaxis()  # 重要性从高到低显示

    # 为条形添加数值标签
    for i, bar in enumerate(bars):
        width = bar.get_width()
        plt.text(width + 0.001, bar.get_y() + bar.get_height()/2,
                f'{width:.4f}', ha='left', va='center', fontsize=9)

    plt.tight_layout()
    plt.show()


def compare_models(models_metrics):
    """
    比较多个模型的性能

    参数:
    models_metrics: 字典，格式为 {'模型名': metrics_dict}
    """
    comparison_data = []

    for model_name, metrics in models_metrics.items():
        test_report = metrics['test_report']
        if '1' in test_report:  # 违约类（通常为1）
            precision = test_report['1']['precision']
            recall = test_report['1']['recall']
            f1 = test_report['1']['f1-score']
        else:
            # 如果类别标签不同
            for key in test_report:
                if key not in ['accuracy', 'macro avg', 'weighted avg']:
                    precision = test_report[key]['precision']
                    recall = test_report[key]['recall']
                    f1 = test_report[key]['f1-score']
                    break

        comparison_data.append({
            '模型': model_name,
            'AUC': metrics['auc_score'],
            '精确率': precision,
            '召回率': recall,
            'F1分数': f1
        })

    comparison_df = pd.DataFrame(comparison_data)
    comparison_df = comparison_df.sort_values('AUC', ascending=False)

    print("=" * 60)
    print("模型性能比较")
    print("=" * 60)
    print(comparison_df.to_string(index=False))

    # 绘制比较图
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # AUC比较
    axes[0, 0].bar(comparison_df['模型'], comparison_df['AUC'], color='skyblue')
    axes[0, 0].set_ylabel('AUC')
    axes[0, 0].set_title('模型AUC比较')
    axes[0, 0].tick_params(axis='x', rotation=45)

    # 精确率比较
    axes[0, 1].bar(comparison_df['模型'], comparison_df['精确率'], color='lightgreen')
    axes[0, 1].set_ylabel('精确率')
    axes[0, 1].set_title('模型精确率比较')
    axes[0, 1].tick_params(axis='x', rotation=45)

    # 召回率比较
    axes[1, 0].bar(comparison_df['模型'], comparison_df['召回率'], color='lightcoral')
    axes[1, 0].set_ylabel('召回率')
    axes[1, 0].set_title('模型召回率比较')
    axes[1, 0].tick_params(axis='x', rotation=45)

    # F1分数比较
    axes[1, 1].bar(comparison_df['模型'], comparison_df['F1分数'], color='gold')
    axes[1, 1].set_ylabel('F1分数')
    axes[1, 1].set_title('模型F1分数比较')
    axes[1, 1].tick_params(axis='x', rotation=45)

    plt.tight_layout()
    plt.show()

    return comparison_df


# ============================================================================
# 5. 信贷业务特定分析
# ============================================================================

def analyze_loan_portfolio(df, loan_amount_col='loan_amount', default_col='default'):
    """
    分析贷款组合质量

    参数:
    df: DataFrame
    loan_amount_col: 贷款金额列名
    default_col: 违约标志列名

    返回:
    portfolio_metrics: 组合指标字典
    """
    if loan_amount_col not in df.columns or default_col not in df.columns:
        print(f"缺少必要列: {loan_amount_col} 或 {default_col}")
        return None

    print("=" * 60)
    print("贷款组合质量分析")
    print("=" * 60)

    # 基础指标
    total_loans = df[loan_amount_col].sum()
    total_count = len(df)
    default_count = df[default_col].sum()
    default_amount = df[df[default_col] == 1][loan_amount_col].sum()

    # 违约率
    default_rate_count = default_count / total_count
    default_rate_amount = default_amount / total_loans

    print(f"贷款总数: {total_count:,}")
    print(f"总贷款金额: {total_loans:,.2f}")
    print(f"\n违约贷款数: {default_count:,}")
    print(f"违约贷款金额: {default_amount:,.2f}")
    print(f"\n数量违约率: {default_rate_count:.2%}")
    print(f"金额违约率: {default_rate_amount:.2%}")

    # 分组分析
    portfolio_metrics = {
        'total_loans': total_loans,
        'total_count': total_count,
        'default_count': default_count,
        'default_amount': default_amount,
        'default_rate_count': default_rate_count,
        'default_rate_amount': default_rate_amount
    }

    # 如果有分组字段，进行细分分析
    grouping_cols = []
    for col in ['loan_group', 'income_group', 'age_group']:
        if col in df.columns:
            grouping_cols.append(col)

    for group_col in grouping_cols[:2]:  # 只分析前两个分组
        print(f"\n📊 按 {group_col} 分组分析:")

        group_analysis = df.groupby(group_col).agg({
            loan_amount_col: ['count', 'sum', 'mean'],
            default_col: ['sum', 'mean']
        }).round(2)

        # 重命名列
        group_analysis.columns = ['贷款数', '总金额', '平均金额', '违约数', '违约率']
        print(group_analysis)

        portfolio_metrics[f'group_analysis_{group_col}'] = group_analysis

    return portfolio_metrics


def calculate_risk_metrics(df, default_col='default',
                          recovery_rate=0.4, interest_rate=0.06):
    """
    计算风险指标（PD, LGD, EL）

    参数:
    df: DataFrame
    default_col: 违约标志列名
    recovery_rate: 回收率（假设值，通常为40%）
    interest_rate: 平均利率（假设值，通常为6%）

    返回:
    risk_metrics: 风险指标字典
    """
    if default_col not in df.columns:
        print(f"缺少违约列: {default_col}")
        return None

    print("=" * 60)
    print("风险指标计算")
    print("=" * 60)

    # PD（违约概率）
    pd_value = df[default_col].mean()

    # LGD（违约损失率）
    lgd_value = 1 - recovery_rate

    # EL（预期损失）
    el_value = pd_value * lgd_value * interest_rate

    # 风险调整后收益
    if 'interest_rate' in df.columns:
        avg_interest = df['interest_rate'].mean()
        risk_adjusted_return = avg_interest - el_value
    else:
        risk_adjusted_return = interest_rate - el_value

    print(f"PD (违约概率): {pd_value:.4f} ({pd_value*100:.2f}%)")
    print(f"LGD (违约损失率): {lgd_value:.4f} ({lgd_value*100:.2f}%)")
    print(f"EL (预期损失): {el_value:.4f} ({el_value*100:.2f}%)")
    print(f"风险调整后收益: {risk_adjusted_return:.4f} ({risk_adjusted_return*100:.2f}%)")

    # 风险等级划分
    risk_level = '低风险' if pd_value < 0.02 else '中风险' if pd_value < 0.05 else '高风险'
    print(f"\n📊 风险等级: {risk_level}")

    risk_metrics = {
        'PD': pd_value,
        'LGD': lgd_value,
        'EL': el_value,
        'risk_adjusted_return': risk_adjusted_return,
        'risk_level': risk_level
    }

    return risk_metrics


def customer_segmentation_analysis(df, segment_cols=None):
    """
    客户细分分析

    参数:
    df: DataFrame
    segment_cols: 细分字段列表（如为None，则使用默认字段）

    返回:
    segmentation_results: 细分分析结果
    """
    if segment_cols is None:
        segment_cols = []
        for col in ['age_group', 'income_group', 'loan_group']:
            if col in df.columns:
                segment_cols.append(col)

    if not segment_cols:
        print("无细分字段可用")
        return None

    print("=" * 60)
    print("客户细分分析")
    print("=" * 60)

    segmentation_results = {}

    for segment_col in segment_cols:
        if segment_col not in df.columns:
            continue

        print(f"\n🎯 按 {segment_col} 细分:")

        # 基本统计
        segment_stats = df.groupby(segment_col).agg({
            'customer_id': 'count',
            'loan_amount': ['sum', 'mean'],
            'monthly_income': 'mean',
            'default': ['sum', 'mean']
        }).round(2)

        # 重命名列
        segment_stats.columns = ['客户数', '总贷款额', '平均贷款额', '平均收入', '违约数', '违约率']

        # 计算占比
        segment_stats['客户占比'] = (segment_stats['客户数'] / len(df) * 100).round(1)
        segment_stats['金额占比'] = (segment_stats['总贷款额'] / df['loan_amount'].sum() * 100).round(1)

        print(segment_stats)
        segmentation_results[segment_col] = segment_stats

        # 可视化
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        # 客户数分布
        segment_stats['客户数'].plot(kind='bar', ax=axes[0], color='skyblue')
        axes[0].set_xlabel(segment_col)
        axes[0].set_ylabel('客户数')
        axes[0].set_title(f'按 {segment_col} 客户数分布')
        axes[0].tick_params(axis='x', rotation=45)

        # 违约率分布
        segment_stats['违约率'].plot(kind='bar', ax=axes[1], color='lightcoral')
        axes[1].set_xlabel(segment_col)
        axes[1].set_ylabel('违约率')
        axes[1].set_title(f'按 {segment_col} 违约率分布')
        axes[1].tick_params(axis='x', rotation=45)

        plt.tight_layout()
        plt.show()

    return segmentation_results


# ============================================================================
# 6. 主函数与示例
# ============================================================================

def run_credit_analysis_pipeline(data_path=None, sample_data=True):
    """
    运行完整的信贷分析流程

    参数:
    data_path: 数据文件路径（如为None，则生成示例数据）
    sample_data: 是否生成示例数据
    """
    print("=" * 60)
    print("信贷数据分析流程")
    print("=" * 60)

    # 1. 数据准备
    if data_path and os.path.exists(data_path):
        print(f"\n1️⃣ 加载数据: {data_path}")
        df = load_credit_data(data_path)
    elif sample_data:
        print("\n1️⃣ 生成示例数据")
        np.random.seed(42)
        n_samples = 5000

        df = pd.DataFrame({
            'customer_id': range(1, n_samples + 1),
            'age': np.random.randint(18, 70, n_samples),
            'monthly_income': np.random.normal(8000, 3000, n_samples).clip(2000, 50000),
            'monthly_debt': np.random.normal(2000, 800, n_samples).clip(500, 10000),
            'loan_amount': np.random.normal(50000, 20000, n_samples).clip(5000, 200000),
            'loan_term': np.random.choice([12, 24, 36, 48, 60], n_samples, p=[0.1, 0.2, 0.3, 0.25, 0.15]),
            'interest_rate': np.random.normal(0.06, 0.02, n_samples).clip(0.03, 0.15),
            'credit_score': np.random.randint(300, 850, n_samples),
            'employment_years': np.random.exponential(5, n_samples).clip(0, 30),
            'monthly_payment': np.random.normal(1500, 500, n_samples).clip(300, 5000),
            'default': np.random.choice([0, 1], n_samples, p=[0.85, 0.15])
        })

        # 保存示例数据
        df.to_csv('example_credit_data.csv', index=False)
        print(f"   示例数据已保存到: example_credit_data.csv")
    else:
        print("❌ 无数据可用")
        return

    # 2. 数据探索
    print("\n2️⃣ 数据探索")
    explore_data(df)

    # 3. 数据清洗
    print("\n3️⃣ 数据清洗")
    cleaned_df = clean_credit_data(df, target_col='default')

    # 4. EDA
    print("\n4️⃣ 探索性数据分析 (EDA)")
    perform_comprehensive_eda(cleaned_df, target_col='default', sample_size=3000)

    # 5. 特征工程
    print("\n5️⃣ 特征工程")
    df_with_features = create_credit_features(cleaned_df, target_col='default')

    # 6. 编码分类特征
    print("\n6️⃣ 编码分类特征")
    categorical_cols = df_with_features.select_dtypes(include=['object', 'category']).columns.tolist()
    df_encoded, _ = encode_categorical_features(df_with_features, categorical_cols, method='label')

    # 7. 准备模型数据
    print("\n7️⃣ 准备模型数据")
    X_train, X_test, y_train, y_test, feature_cols = prepare_model_data(
        df_encoded, target_col='default', test_size=0.2
    )

    # 8. 训练模型
    print("\n8️⃣ 模型训练")
    models_metrics = {}

    # 逻辑回归
    lr_model, lr_scaler, lr_metrics = train_logistic_regression(
        X_train, X_test, y_train, y_test, feature_cols
    )
    models_metrics['逻辑回归'] = lr_metrics

    # 随机森林
    rf_model, rf_metrics = train_random_forest(
        X_train, X_test, y_train, y_test, feature_cols, n_estimators=100
    )
    models_metrics['随机森林'] = rf_metrics

    # 9. 模型比较
    print("\n9️⃣ 模型比较")
    comparison_df = compare_models(models_metrics)

    # 10. 业务分析
    print("\n🔟 业务分析")

    # 贷款组合分析
    portfolio_metrics = analyze_loan_portfolio(df_with_features)

    # 风险指标计算
    risk_metrics = calculate_risk_metrics(df_with_features)

    # 客户细分分析
    segmentation_results = customer_segmentation_analysis(df_with_features)

    print("\n" + "=" * 60)
    print("✅ 分析流程完成")
    print("=" * 60)

    # 保存结果
    results = {
        'data': df_encoded,
        'features': feature_cols,
        'models': {
            '逻辑回归': lr_model,
            '随机森林': rf_model
        },
        'metrics': models_metrics,
        'comparison': comparison_df,
        'portfolio': portfolio_metrics,
        'risk': risk_metrics,
        'segmentation': segmentation_results
    }

    # 保存到文件
    import pickle
    with open('credit_analysis_results.pkl', 'wb') as f:
        pickle.dump(results, f)

    print("📁 结果已保存到: credit_analysis_results.pkl")

    return results


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    import os

    print("🚀 开始信贷数据分析")
    print("提示: 请确保已安装必要的库: pandas, numpy, matplotlib, seaborn, scikit-learn")
    print("-" * 60)

    # 检查依赖
    try:
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        print("✅ 依赖检查通过")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install pandas numpy matplotlib seaborn scikit-learn")
        exit(1)

    # 运行完整流程
    try:
        results = run_credit_analysis_pipeline(
            data_path=None,  # 设置为实际数据文件路径
            sample_data=True  # 生成示例数据
        )

        if results:
            print("\n🎉 分析成功完成!")
            print("\n下一步建议:")
            print("1. 使用真实数据替换示例数据")
            print("2. 尝试更多模型和超参数调优")
            print("3. 部署最佳模型到生产环境")
            print("4. 定期监控模型性能")

    except Exception as e:
        print(f"\n❌ 分析过程中出现错误: {e}")
        import traceback
        traceback.print_exc()