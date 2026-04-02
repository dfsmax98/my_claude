# 信贷数据分析工具集

专为信贷行业数据分析师设计的Python和SQL工具集合，包含数据清洗、探索性分析、特征工程、模型训练和业务分析等完整流程。

## 目录结构

```
credit_analysis_demo/
├── README.md                    # 项目说明文档
├── requirements.txt             # Python依赖包列表
├── credit_analysis.py           # Python数据分析核心代码
├── credit_sql_queries.sql       # SQL查询集合
├── generate_sample_data.py      # 示例数据生成脚本
└── example_credit_data.csv      # 示例数据文件（运行后生成）
```

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt

# 或者手动安装核心依赖
pip install pandas numpy matplotlib seaborn scikit-learn
```

### 2. 运行完整分析流程

```python
# 在Python中运行
python credit_analysis.py
```

这将：
1. 生成示例信贷数据
2. 执行完整的数据分析流程
3. 训练违约预测模型
4. 生成可视化图表
5. 保存分析结果

### 3. 使用SQL查询

将 `credit_sql_queries.sql` 中的查询复制到数据库管理工具中执行，或使用Python连接数据库运行。

## 核心功能

### Python模块 (`credit_analysis.py`)

#### 1. 数据加载与清洗
- `load_credit_data()` - 加载CSV/Excel格式数据
- `explore_data()` - 数据探索性分析
- `clean_credit_data()` - 数据清洗（缺失值、异常值处理）

#### 2. 探索性数据分析 (EDA)
- `plot_target_distribution()` - 目标变量分布可视化
- `plot_numeric_distributions()` - 数值变量分布分析
- `plot_correlation_heatmap()` - 特征相关性分析
- `perform_comprehensive_eda()` - 全面EDA分析

#### 3. 特征工程
- `create_credit_features()` - 创建信贷业务特征（DTI、LTI、分组特征等）
- `encode_categorical_features()` - 分类特征编码

#### 4. 模型训练与评估
- `train_logistic_regression()` - 逻辑回归模型
- `train_random_forest()` - 随机森林模型
- `compare_models()` - 模型性能比较

#### 5. 信贷业务分析
- `analyze_loan_portfolio()` - 贷款组合质量分析
- `calculate_risk_metrics()` - 风险指标计算（PD、LGD、EL）
- `customer_segmentation_analysis()` - 客户细分分析

#### 6. 完整流程
- `run_credit_analysis_pipeline()` - 运行完整分析流程

### SQL查询集合 (`credit_sql_queries.sql`)

#### 1. 基础查询
- 表结构查看
- 数据探索
- 基本统计

#### 2. 业务指标计算
- 总体业务指标
- 时间维度分析
- 客户特征分析

#### 3. 风险分析
- 负债收入比(DTI)分析
- 风险评分模型
- 风险集中度分析

#### 4. 高级分析
- 窗口函数应用
- 移动窗口分析
- 排名分析

#### 5. 多表关联
- 客户信息关联分析
- 还款记录分析

#### 6. 数据质量检查
- 缺失值检测
- 异常值检测
- 数据一致性检查

#### 7. KPI与仪表板
- 每日业务仪表板
- 月度KPI汇总
- 风险KPI监控

## 示例数据

项目包含示例数据生成功能，模拟真实信贷数据场景：

- **客户信息**：年龄、收入、信用评分等
- **贷款信息**：金额、期限、利率、违约标志
- **时间信息**：贷款日期、还款记录
- **风险指标**：违约概率、损失率等

### 生成示例数据

```python
python generate_sample_data.py
```

这将生成 `example_credit_data.csv` 文件，包含5000条模拟记录。

## 信贷业务知识

### 关键指标解释

1. **PD (违约概率)** - 借款人违约的可能性
2. **LGD (违约损失率)** - 违约后无法收回的贷款比例
3. **EL (预期损失)** - PD × LGD × 风险敞口
4. **DTI (负债收入比)** - 月负债 / 月收入
5. **LTI (贷款收入比)** - 贷款金额 / 年收入

### 风险等级划分

| 风险等级 | PD范围 | 信用评分 | 建议措施 |
|---------|--------|----------|----------|
| 低风险 | <2% | >750 | 优先审批，优惠利率 |
| 中风险 | 2%-5% | 650-750 | 正常审批，标准利率 |
| 高风险 | 5%-10% | 550-650 | 严格审核，提高利率 |
| 极高风险 | >10% | <550 | 拒绝或要求担保 |

## 实际应用场景

### 1. 贷前审批
- 客户信用评分
- 还款能力评估
- 风险等级划分

### 2. 贷中监控
- 客户行为分析
- 风险预警
- 额度调整

### 3. 贷后管理
- 违约预测
- 催收策略
- 损失准备金计算

### 4. 业务决策
- 产品定价
- 营销策略
- 风险政策制定

## 自定义配置

### 修改数据源

```python
# 使用自己的数据文件
results = run_credit_analysis_pipeline(
    data_path='your_data.csv',  # 替换为实际文件路径
    sample_data=False           # 不使用示例数据
)
```

### 调整模型参数

```python
# 在credit_analysis.py中修改
model = RandomForestClassifier(
    n_estimators=200,      # 增加树的数量
    max_depth=10,          # 调整树深度
    min_samples_split=5,   # 调整分裂最小样本数
    random_state=42
)
```

### 添加新特征

```python
# 在create_credit_features函数中添加
def create_credit_features(df, target_col='default'):
    # ... 现有代码 ...
    
    # 添加自定义特征
    if all(col in df.columns for col in ['feature1', 'feature2']):
        df_with_features['custom_feature'] = df['feature1'] / df['feature2']
    
    return df_with_features
```

## 性能优化建议

### Python优化
1. 大数据集使用分块处理
2. 使用向量化操作替代循环
3. 适当使用并行计算
4. 定期清理内存

### SQL优化
1. 为查询字段创建索引
2. 使用EXPLAIN分析查询计划
3. 避免SELECT *，只选择需要的列
4. 大数据表考虑分区

## 常见问题

### Q1: 运行时报错"ModuleNotFoundError"
A: 确保已安装所有依赖包：`pip install -r requirements.txt`

### Q2: 如何连接真实数据库？
A: 使用pandas的数据库连接功能：

```python
import pandas as pd
from sqlalchemy import create_engine

# MySQL连接示例
engine = create_engine('mysql+pymysql://user:password@host/database')
df = pd.read_sql('SELECT * FROM credit_loans', engine)
```

### Q3: 数据量太大，运行缓慢怎么办？
A: 1) 使用数据采样；2) 分批次处理；3) 使用Dask或PySpark

### Q4: 如何部署到生产环境？
A: 1) 将模型保存为.pkl文件；2) 创建API服务；3) 定期重新训练模型

## 学习资源

### 推荐书籍
1. 《信用风险评分卡研究》
2. 《Python金融大数据分析》
3. 《SQL进阶教程》

### 在线课程
1. Coursera: 金融科技与数据分析
2. 网易云课堂: Python数据分析实战
3. 极客时间: SQL必知必会

### 实用工具
1. Jupyter Notebook - 交互式数据分析
2. Tableau/Power BI - 数据可视化
3. Apache Superset - 开源BI工具

## 更新日志

### v1.0 (2024-01-15)
- 初始版本发布
- 包含完整的Python分析流程
- 丰富的SQL查询集合
- 示例数据生成功能

## 贡献指南

欢迎提交Issue和Pull Request！

1. Fork本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开Pull Request

## 许可证

本项目采用MIT许可证 - 查看LICENSE文件了解详情。

## 联系方式

如有问题或建议，请通过以下方式联系：

- 提交GitHub Issue
- 发送邮件至: example@email.com

---

**提示**：本工具集为教育目的设计，实际业务应用前请充分测试和验证。