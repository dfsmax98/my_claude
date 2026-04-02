"""
信贷示例数据生成器
生成模拟的信贷数据用于测试和分析
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


def generate_credit_data(n_customers=1000, n_loans=5000, start_date='2020-01-01', end_date='2024-01-01'):
    """
    生成模拟信贷数据

    参数:
    n_customers: 客户数量
    n_loans: 贷款记录数量
    start_date: 数据开始日期
    end_date: 数据结束日期

    返回:
    customers_df: 客户信息DataFrame
    loans_df: 贷款信息DataFrame
    """
    np.random.seed(42)

    print(f"生成 {n_customers} 个客户和 {n_loans} 条贷款记录...")

    # ============================================================================
    # 1. 生成客户基本信息
    # ============================================================================

    print("1. 生成客户基本信息...")

    # 客户ID
    customer_ids = list(range(1, n_customers + 1))

    # 基本信息
    genders = np.random.choice(['男', '女'], n_customers, p=[0.55, 0.45])
    ages = np.random.normal(40, 12, n_customers).clip(18, 70).astype(int)

    # 收入分布（模拟真实收入分布，右偏）
    monthly_incomes = np.random.lognormal(8.5, 0.6, n_customers).clip(2000, 50000)

    # 教育程度
    education_levels = np.random.choice(
        ['高中及以下', '大专', '本科', '硕士', '博士'],
        n_customers,
        p=[0.2, 0.3, 0.35, 0.1, 0.05]
    )

    # 婚姻状况
    marital_status = np.random.choice(
        ['未婚', '已婚', '离异', '丧偶'],
        n_customers,
        p=[0.3, 0.55, 0.1, 0.05]
    )

    # 职业
    occupations = np.random.choice(
        ['工人', '职员', '技术人员', '管理人员', '自由职业', '其他'],
        n_customers,
        p=[0.2, 0.25, 0.2, 0.15, 0.1, 0.1]
    )

    # 所在城市（模拟一线、二线、三线城市分布）
    cities = np.random.choice(
        ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '西安', '其他'],
        n_customers,
        p=[0.1, 0.1, 0.08, 0.08, 0.12, 0.12, 0.1, 0.1, 0.2]
    )

    # 加入日期（客户成为银行客户的时间）
    join_dates = []
    start_dt = datetime.strptime('2015-01-01', '%Y-%m-%d')
    end_dt = datetime.strptime('2023-12-31', '%Y-%m-%d')
    for _ in range(n_customers):
        days_diff = (end_dt - start_dt).days
        random_days = np.random.randint(0, days_diff)
        join_date = start_dt + timedelta(days=random_days)
        join_dates.append(join_date.strftime('%Y-%m-%d'))

    # 创建客户DataFrame
    customers_df = pd.DataFrame({
        'customer_id': customer_ids,
        'gender': genders,
        'age': ages,
        'monthly_income': monthly_incomes.round(2),
        'education_level': education_levels,
        'marital_status': marital_status,
        'occupation': occupations,
        'city': cities,
        'join_date': join_dates
    })

    # ============================================================================
    # 2. 生成贷款记录
    # ============================================================================

    print("2. 生成贷款记录...")

    # 贷款ID
    loan_ids = list(range(1, n_loans + 1))

    # 随机分配客户（有些客户可能有多次贷款）
    loan_customer_ids = np.random.choice(customer_ids, n_loans, replace=True)

    # 贷款日期（在客户加入日期之后）
    loan_dates = []
    for customer_id in loan_customer_ids:
        customer_join_date = customers_df.loc[customers_df['customer_id'] == customer_id, 'join_date'].iloc[0]
        join_dt = datetime.strptime(customer_join_date, '%Y-%m-%d')

        # 贷款日期在加入日期之后，在数据结束日期之前
        max_days = (datetime.strptime(end_date, '%Y-%m-%d') - join_dt).days
        if max_days <= 0:
            max_days = 365  # 如果加入日期太晚，默认给一年时间

        random_days = np.random.randint(0, max_days)
        loan_date = join_dt + timedelta(days=random_days)
        loan_dates.append(loan_date.strftime('%Y-%m-%d'))

    # 贷款金额（与收入相关）
    loan_amounts = []
    monthly_debts = []
    for i, customer_id in enumerate(loan_customer_ids):
        customer_income = customers_df.loc[customers_df['customer_id'] == customer_id, 'monthly_income'].iloc[0]

        # 贷款金额基于收入，加入随机性
        base_amount = customer_income * np.random.uniform(3, 12)  # 3-12倍月收入
        # 加入随机波动
        loan_amount = np.random.normal(base_amount, base_amount * 0.3).clip(5000, 500000)
        loan_amounts.append(round(loan_amount, 2))

        # 月负债（包括本次贷款和其他负债）
        other_debt = customer_income * np.random.uniform(0.1, 0.4)  # 其他负债占收入的10-40%
        this_loan_monthly_payment = loan_amount * 0.02  # 简化计算，月供约为贷款金额的2%
        monthly_debt = other_debt + this_loan_monthly_payment
        monthly_debts.append(round(monthly_debt, 2))

    # 贷款期限（月）
    loan_terms = np.random.choice([12, 24, 36, 48, 60], n_loans, p=[0.1, 0.2, 0.3, 0.25, 0.15])

    # 利率（基于客户风险和贷款期限）
    interest_rates = []
    credit_scores = []
    for i, customer_id in enumerate(loan_customer_ids):
        customer_age = customers_df.loc[customers_df['customer_id'] == customer_id, 'age'].iloc[0]
        customer_income = customers_df.loc[customers_df['customer_id'] == customer_id, 'monthly_income'].iloc[0]
        education = customers_df.loc[customers_df['customer_id'] == customer_id, 'education_level'].iloc[0]

        # 模拟信用评分（300-850）
        # 基础分
        base_score = 600

        # 年龄影响（35-55岁最佳）
        if customer_age < 25:
            age_adjustment = -30
        elif customer_age < 35:
            age_adjustment = -10
        elif customer_age < 55:
            age_adjustment = 20
        else:
            age_adjustment = 0

        # 收入影响（收入越高，评分越高）
        income_adjustment = min(50, (customer_income - 5000) / 1000 * 5)

        # 教育影响
        education_map = {'高中及以下': -20, '大专': 0, '本科': 10, '硕士': 20, '博士': 30}
        education_adjustment = education_map.get(education, 0)

        # 随机波动
        random_adjustment = np.random.normal(0, 20)

        # 计算最终信用评分
        credit_score = base_score + age_adjustment + income_adjustment + education_adjustment + random_adjustment
        credit_score = int(np.clip(credit_score, 300, 850))
        credit_scores.append(credit_score)

        # 基于信用评分和贷款期限确定利率
        # 基础利率
        if credit_score >= 750:
            base_rate = 0.045
        elif credit_score >= 650:
            base_rate = 0.065
        elif credit_score >= 550:
            base_rate = 0.085
        else:
            base_rate = 0.105

        # 期限调整（期限越长，利率越高）
        term = loan_terms[i]
        term_adjustment = (term - 12) / 48 * 0.02  # 每增加一年，利率增加0.5%

        # 金额调整（金额越大，利率可能越低）
        amount = loan_amounts[i]
        if amount > 200000:
            amount_adjustment = -0.01
        elif amount > 100000:
            amount_adjustment = -0.005
        else:
            amount_adjustment = 0

        # 随机波动
        random_rate_adjustment = np.random.normal(0, 0.005)

        # 最终利率
        interest_rate = base_rate + term_adjustment + amount_adjustment + random_rate_adjustment
        interest_rate = round(np.clip(interest_rate, 0.03, 0.15), 4)
        interest_rates.append(interest_rate)

    # 月供计算（等额本息简化版）
    monthly_payments = []
    for i in range(n_loans):
        amount = loan_amounts[i]
        rate = interest_rates[i]
        term = loan_terms[i]

        # 等额本息月供计算公式简化版
        monthly_rate = rate / 12
        if monthly_rate == 0:
            monthly_payment = amount / term
        else:
            monthly_payment = amount * monthly_rate * (1 + monthly_rate) ** term / ((1 + monthly_rate) ** term - 1)

        monthly_payments.append(round(monthly_payment, 2))

    # 就业年限
    employment_years = []
    for age in ages_for_loans:
        # 假设18岁开始工作
        start_work_age = np.random.randint(18, 22)
        work_years = max(0, age - start_work_age)
        # 加入随机性（失业、换工作等）
        work_years = np.random.normal(work_years, 2).clip(0, age - 18)
        employment_years.append(round(work_years, 1))

    # 违约标志生成（基于风险因素）
    default_flags = []
    for i in range(n_loans):
        customer_id = loan_customer_ids[i]
        credit_score = credit_scores[i]
        dti_ratio = monthly_debts[i] / customers_df.loc[customers_df['customer_id'] == customer_id, 'monthly_income'].iloc[0]
        loan_amount = loan_amounts[i]
        customer_age = customers_df.loc[customers_df['customer_id'] == customer_id, 'age'].iloc[0]

        # 违约概率计算
        # 基础违约率
        base_default_prob = 0.05

        # 信用评分影响
        if credit_score < 500:
            score_factor = 4.0
        elif credit_score < 600:
            score_factor = 2.0
        elif credit_score < 700:
            score_factor = 1.0
        else:
            score_factor = 0.5

        # DTI影响
        if dti_ratio > 0.6:
            dti_factor = 3.0
        elif dti_ratio > 0.4:
            dti_factor = 1.5
        else:
            dti_factor = 1.0

        # 年龄影响
        if customer_age < 25:
            age_factor = 1.5
        elif customer_age > 60:
            age_factor = 1.3
        else:
            age_factor = 1.0

        # 贷款金额影响（大额贷款违约风险可能不同）
        if loan_amount > 200000:
            amount_factor = 1.2
        elif loan_amount < 20000:
            amount_factor = 0.8
        else:
            amount_factor = 1.0

        # 计算最终违约概率
        default_prob = base_default_prob * score_factor * dti_factor * age_factor * amount_factor
        default_prob = min(default_prob, 0.3)  # 上限30%

        # 生成违约标志
        default_flag = 1 if np.random.random() < default_prob else 0
        default_flags.append(default_flag)

    # 创建贷款DataFrame
    loans_df = pd.DataFrame({
        'loan_id': loan_ids,
        'customer_id': loan_customer_ids,
        'loan_date': loan_dates,
        'loan_amount': loan_amounts,
        'loan_term': loan_terms,
        'interest_rate': interest_rates,
        'monthly_payment': monthly_payments,
        'monthly_debt': monthly_debts,
        'credit_score': credit_scores,
        'employment_years': employment_years,
        'default_flag': default_flags
    })

    # 按贷款日期排序
    loans_df = loans_df.sort_values('loan_date').reset_index(drop=True)

    # ============================================================================
    # 3. 生成还款记录（可选）
    # ============================================================================

    print("3. 生成还款记录（可选）...")

    # 这里简化，不生成详细的还款记录
    # 在实际应用中，可以根据贷款信息生成详细的还款计划

    # 计算已还期数（对于未违约的贷款）
    paid_terms = []
    for i in range(n_loans):
        default_flag = default_flags[i]
        loan_term = loan_terms[i]
        loan_date = datetime.strptime(loan_dates[i], '%Y-%m-%d')

        if default_flag == 1:
            # 违约贷款：随机还了几期后违约
            max_paid = min(loan_term, np.random.randint(1, loan_term // 2 + 1))
            paid_terms.append(max_paid)
        else:
            # 正常贷款：计算从贷款日到数据结束日已还期数
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            months_passed = (end_dt.year - loan_date.year) * 12 + (end_dt.month - loan_date.month)
            paid = min(loan_term, max(0, months_passed))
            paid_terms.append(paid)

    loans_df['paid_terms'] = paid_terms
    loans_df['remaining_terms'] = loans_df['loan_term'] - loans_df['paid_terms']

    # ============================================================================
    # 4. 添加衍生特征
    # ============================================================================

    print("4. 添加衍生特征...")

    # 计算DTI（负债收入比）
    loans_df['dti_ratio'] = loans_df['monthly_debt'] / loans_df['customer_id'].map(
        customers_df.set_index('customer_id')['monthly_income']
    )

    # 计算LTI（贷款收入比）
    loans_df['lti_ratio'] = loans_df['loan_amount'] / loans_df['customer_id'].map(
        customers_df.set_index('customer_id')['monthly_income']
    )

    # 年龄分组
    loans_df['age_group'] = pd.cut(
        loans_df['customer_id'].map(customers_df.set_index('customer_id')['age']),
        bins=[0, 25, 35, 45, 55, 65, 100],
        labels=['18-25', '26-35', '36-45', '46-55', '56-65', '65+']
    )

    # 收入分组
    loans_df['income_group'] = pd.cut(
        loans_df['customer_id'].map(customers_df.set_index('customer_id')['monthly_income']),
        bins=[0, 3000, 6000, 10000, 20000, 50000, float('inf')],
        labels=['<3k', '3k-6k', '6k-10k', '10k-20k', '20k-50k', '>50k']
    )

    # 贷款金额分组
    loans_df['loan_group'] = pd.cut(
        loans_df['loan_amount'],
        bins=[0, 10000, 50000, 100000, 200000, 500000, float('inf')],
        labels=['<10k', '10k-50k', '50k-100k', '100k-200k', '200k-500k', '>500k']
    )

    # 信用评分分组
    loans_df['credit_score_group'] = pd.cut(
        loans_df['credit_score'],
        bins=[0, 500, 600, 700, 800, 850],
        labels=['<500', '500-599', '600-699', '700-799', '800+']
    )

    # ============================================================================
    # 5. 数据验证和统计
    # ============================================================================

    print("5. 数据验证和统计...")

    # 合并客户信息和贷款信息（用于分析）
    merged_df = pd.merge(loans_df, customers_df, on='customer_id', how='left')

    # 打印统计信息
    print("\n" + "=" * 60)
    print("数据生成完成!")
    print("=" * 60)

    print(f"\n📊 客户数据统计:")
    print(f"   客户数量: {len(customers_df)}")
    print(f"   平均年龄: {customers_df['age'].mean():.1f}岁")
    print(f"   平均月收入: {customers_df['monthly_income'].mean():.2f}")
    print(f"   性别分布: 男 {sum(customers_df['gender'] == '男')}人, 女 {sum(customers_df['gender'] == '女')}人")

    print(f"\n📊 贷款数据统计:")
    print(f"   贷款记录数: {len(loans_df)}")
    print(f"   总贷款金额: {loans_df['loan_amount'].sum():,.2f}")
    print(f"   平均贷款金额: {loans_df['loan_amount'].mean():,.2f}")
    print(f"   平均贷款期限: {loans_df['loan_term'].mean():.1f}个月")
    print(f"   平均利率: {loans_df['interest_rate'].mean() * 100:.2f}%")
    print(f"   平均信用评分: {loans_df['credit_score'].mean():.1f}")

    print(f"\n⚠️  风险指标:")
    print(f"   违约贷款数: {loans_df['default_flag'].sum()}")
    print(f"   违约率: {loans_df['default_flag'].mean() * 100:.2f}%")
    print(f"   违约贷款金额: {loans_df[loans_df['default_flag'] == 1]['loan_amount'].sum():,.2f}")
    print(f"   金额违约率: {loans_df[loans_df['default_flag'] == 1]['loan_amount'].sum() / loans_df['loan_amount'].sum() * 100:.2f}%")

    print(f"\n📈 衍生特征统计:")
    print(f"   平均DTI: {loans_df['dti_ratio'].mean() * 100:.1f}%")
    print(f"   平均LTI: {loans_df['lti_ratio'].mean():.2f}")

    print(f"\n📁 数据维度:")
    print(f"   客户表: {customers_df.shape[0]}行 × {customers_df.shape[1]}列")
    print(f"   贷款表: {loans_df.shape[0]}行 × {loans_df.shape[1]}列")

    return customers_df, loans_df, merged_df


def save_data(customers_df, loans_df, merged_df, prefix='credit_data'):
    """
    保存生成的数据到CSV文件

    参数:
    customers_df: 客户数据
    loans_df: 贷款数据
    merged_df: 合并数据
    prefix: 文件前缀
    """
    # 保存客户数据
    customers_file = f"{prefix}_customers.csv"
    customers_df.to_csv(customers_file, index=False, encoding='utf-8-sig')
    print(f"✅ 客户数据保存到: {customers_file}")

    # 保存贷款数据
    loans_file = f"{prefix}_loans.csv"
    loans_df.to_csv(loans_file, index=False, encoding='utf-8-sig')
    print(f"✅ 贷款数据保存到: {loans_file}")

    # 保存合并数据（用于分析）
    merged_file = f"{prefix}_merged.csv"
    merged_df.to_csv(merged_file, index=False, encoding='utf-8-sig')
    print(f"✅ 合并数据保存到: {merged_file}")

    # 创建一个简化的单一文件（用于快速测试）
    simple_file = f"{prefix}_simple.csv"
    # 选择最重要的列
    simple_cols = [
        'customer_id', 'age', 'monthly_income', 'loan_amount', 'loan_term',
        'interest_rate', 'credit_score', 'monthly_debt', 'dti_ratio',
        'default_flag', 'loan_date'
    ]
    simple_df = merged_df[simple_cols].copy()
    simple_df.to_csv(simple_file, index=False, encoding='utf-8-sig')
    print(f"✅ 简化数据保存到: {simple_file}")

    return {
        'customers': customers_file,
        'loans': loans_file,
        'merged': merged_file,
        'simple': simple_file
    }


def generate_sample_report(customers_df, loans_df):
    """
    生成数据样本报告

    参数:
    customers_df: 客户数据
    loans_df: 贷款数据
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False

    print("\n" + "=" * 60)
    print("生成数据样本报告...")
    print("=" * 60)

    # 创建图形
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))

    # 1. 违约率分布
    default_counts = loans_df['default_flag'].value_counts()
    axes[0, 0].pie(default_counts.values, labels=['正常', '违约'], autopct='%1.1f%%',
                   colors=['#4CAF50', '#F44336'])
    axes[0, 0].set_title('贷款违约分布')

    # 2. 年龄分布
    axes[0, 1].hist(customers_df['age'], bins=20, edgecolor='black', alpha=0.7, color='skyblue')
    axes[0, 1].set_xlabel('年龄')
    axes[0, 1].set_ylabel('客户数')
    axes[0, 1].set_title('客户年龄分布')
    axes[0, 1].axvline(customers_df['age'].mean(), color='red', linestyle='--',
                      label=f"均值: {customers_df['age'].mean():.1f}")
    axes[0, 1].legend()

    # 3. 收入分布
    axes[0, 2].hist(customers_df['monthly_income'], bins=30, edgecolor='black', alpha=0.7, color='lightgreen')
    axes[0, 2].set_xlabel('月收入')
    axes[0, 2].set_ylabel('客户数')
    axes[0, 2].set_title('客户收入分布')
    axes[0, 2].axvline(customers_df['monthly_income'].mean(), color='red', linestyle='--',
                      label=f"均值: {customers_df['monthly_income'].mean():,.0f}")
    axes[0, 2].legend()

    # 4. 贷款金额分布
    axes[1, 0].hist(loans_df['loan_amount'], bins=30, edgecolor='black', alpha=0.7, color='orange')
    axes[1, 0].set_xlabel('贷款金额')
    axes[1, 0].set_ylabel('贷款数')
    axes[1, 0].set_title('贷款金额分布')
    axes[1, 0].axvline(loans_df['loan_amount'].mean(), color='red', linestyle='--',
                      label=f"均值: {loans_df['loan_amount'].mean():,.0f}")
    axes[1, 0].legend()

    # 5. 信用评分分布
    axes[1, 1].hist(loans_df['credit_score'], bins=20, edgecolor='black', alpha=0.7, color='purple')
    axes[1, 1].set_xlabel('信用评分')
    axes[1, 1].set_ylabel('贷款数')
    axes[1, 1].set_title('信用评分分布')
    axes[1, 1].axvline(loans_df['credit_score'].mean(), color='red', linestyle='--',
                      label=f"均值: {loans_df['credit_score'].mean():.0f}")
    axes[1, 1].legend()

    # 6. 违约率按信用评分
    credit_score_bins = pd.cut(loans_df['credit_score'], bins=5)
    default_by_score = loans_df.groupby(credit_score_bins)['default_flag'].mean()
    axes[1, 2].bar(range(len(default_by_score)), default_by_score.values * 100,
                  color='lightcoral', edgecolor='black')
    axes[1, 2].set_xlabel('信用评分区间')
    axes[1, 2].set_ylabel('违约率 (%)')
    axes[1, 2].set_title('不同信用评分区间的违约率')
    axes[1, 2].set_xticks(range(len(default_by_score)))
    axes[1, 2].set_xticklabels([str(x) for x in default_by_score.index], rotation=45, ha='right')

    plt.tight_layout()
    plt.savefig('credit_data_sample_report.png', dpi=300, bbox_inches='tight')
    plt.show()

    print(f"✅ 样本报告图已保存到: credit_data_sample_report.png")


def main():
    """
    主函数：生成示例数据并保存
    """
    print("=" * 60)
    print("信贷示例数据生成器")
    print("=" * 60)

    # 生成数据
    customers_df, loans_df, merged_df = generate_credit_data(
        n_customers=1000,
        n_loans=5000,
        start_date='2020-01-01',
        end_date='2024-01-01'
    )

    # 保存数据
    files = save_data(customers_df, loans_df, merged_df, prefix='example_credit')

    # 生成报告
    generate_sample_report(customers_df, loans_df)

    print("\n" + "=" * 60)
    print("数据生成完成!")
    print("=" * 60)
    print("\n生成的文件:")
    for file_type, file_path in files.items():
        print(f"  - {file_type}: {file_path}")

    print("\n📋 下一步:")
    print("  1. 使用 credit_analysis.py 进行分析")
    print("  2. 查看 credit_sql_queries.sql 中的SQL查询")
    print("  3. 修改 generate_sample_data.py 生成自定义数据")

    return files


if __name__ == "__main__":
    # 检查依赖
    try:
        import pandas as pd
        import numpy as np
        import matplotlib.pyplot as plt
        print("✅ 依赖检查通过")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install pandas numpy matplotlib seaborn")
        exit(1)

    # 运行主函数
    try:
        files = main()
        print("\n🎉 示例数据生成成功!")
    except Exception as e:
        print(f"\n❌ 数据生成失败: {e}")
        import traceback
        traceback.print_exc()