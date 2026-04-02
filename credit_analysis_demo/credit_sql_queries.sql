/*
信贷行业数据分析SQL查询集合
包含基础查询、高级分析、窗口函数、数据质量检查等
适用于MySQL/PostgreSQL/SQL Server等数据库
*/

-- ============================================================================
-- 1. 数据库与表结构查看
-- ============================================================================

-- 查看所有数据库
SHOW DATABASES;

-- 查看当前数据库中的所有表
SHOW TABLES;

-- 查看表结构
DESCRIBE credit_loans;
-- 或
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'credit_loans';

-- 查看表的基本统计信息
SELECT
    TABLE_NAME,
    TABLE_ROWS AS row_count,
    AVG_ROW_LENGTH AS avg_row_length,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS size_mb
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'credit_loans';

-- ============================================================================
-- 2. 基础查询与数据探索
-- ============================================================================

-- 查看前10行数据
SELECT * FROM credit_loans LIMIT 10;

-- 查看数据总量
SELECT COUNT(*) AS total_records FROM credit_loans;

-- 查看列的基本统计信息
SELECT
    'credit_loans' AS table_name,
    COUNT(*) AS total_rows,
    COUNT(DISTINCT customer_id) AS unique_customers,
    MIN(loan_date) AS earliest_loan,
    MAX(loan_date) AS latest_loan,
    COUNT(CASE WHEN default_flag = 1 THEN 1 END) AS default_count,
    ROUND(COUNT(CASE WHEN default_flag = 1 THEN 1 END) * 100.0 / COUNT(*), 2) AS default_rate_percent
FROM credit_loans;

-- ============================================================================
-- 3. 贷款业务关键指标计算
-- ============================================================================

-- 3.1 总体业务指标
SELECT
    -- 贷款总量指标
    COUNT(*) AS total_loans,
    SUM(loan_amount) AS total_loan_amount,
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,

    -- 违约指标
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    SUM(CASE WHEN default_flag = 1 THEN loan_amount ELSE 0 END) AS default_amount,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_by_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN loan_amount ELSE 0 END) * 100.0 / SUM(loan_amount), 2) AS default_rate_by_amount,

    -- 客户指标
    COUNT(DISTINCT customer_id) AS unique_customers,
    ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT customer_id), 2) AS avg_loans_per_customer,

    -- 时间指标
    DATEDIFF(MAX(loan_date), MIN(loan_date)) AS data_span_days
FROM credit_loans;

-- 3.2 按时间维度的业务指标
SELECT
    DATE_FORMAT(loan_date, '%Y-%m') AS year_month,
    COUNT(*) AS loan_count,
    SUM(loan_amount) AS total_loan_amount,
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 环比增长率
    LAG(COUNT(*)) OVER (ORDER BY DATE_FORMAT(loan_date, '%Y-%m')) AS prev_month_count,
    ROUND((COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY DATE_FORMAT(loan_date, '%Y-%m'))) * 100.0 /
          NULLIF(LAG(COUNT(*)) OVER (ORDER BY DATE_FORMAT(loan_date, '%Y-%m')), 0), 2) AS month_over_month_growth
FROM credit_loans
GROUP BY DATE_FORMAT(loan_date, '%Y-%m')
ORDER BY year_month;

-- ============================================================================
-- 4. 客户分析
-- ============================================================================

-- 4.1 客户基本特征分析
SELECT
    -- 年龄分组
    CASE
        WHEN age < 25 THEN '18-24'
        WHEN age BETWEEN 25 AND 34 THEN '25-34'
        WHEN age BETWEEN 35 AND 44 THEN '35-44'
        WHEN age BETWEEN 45 AND 54 THEN '45-44'
        WHEN age BETWEEN 55 AND 64 THEN '55-64'
        ELSE '65+'
    END AS age_group,

    COUNT(DISTINCT customer_id) AS customer_count,
    COUNT(*) AS loan_count,
    SUM(loan_amount) AS total_loan_amount,
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,
    ROUND(AVG(monthly_income), 2) AS avg_monthly_income,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent
FROM credit_loans
GROUP BY age_group
ORDER BY MIN(age);

-- 4.2 收入水平分析（十分位分析）
SELECT
    NTILE(10) OVER (ORDER BY monthly_income) AS income_decile,
    ROUND(MIN(monthly_income), 2) AS min_income,
    ROUND(MAX(monthly_income), 2) AS max_income,
    ROUND(AVG(monthly_income), 2) AS avg_income,
    COUNT(*) AS loan_count,
    COUNT(DISTINCT customer_id) AS customer_count,
    SUM(loan_amount) AS total_loan_amount,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 平均贷款收入比
    ROUND(AVG(loan_amount / NULLIF(monthly_income, 0)), 2) AS avg_loan_to_income_ratio
FROM credit_loans
WHERE monthly_income > 0
GROUP BY income_decile
ORDER BY income_decile;

-- 4.3 信用评分分析
SELECT
    CASE
        WHEN credit_score < 500 THEN '<500'
        WHEN credit_score BETWEEN 500 AND 599 THEN '500-599'
        WHEN credit_score BETWEEN 600 AND 699 THEN '600-699'
        WHEN credit_score BETWEEN 700 AND 799 THEN '700-799'
        ELSE '800+'
    END AS credit_score_range,

    COUNT(*) AS loan_count,
    COUNT(DISTINCT customer_id) AS customer_count,
    ROUND(AVG(credit_score), 0) AS avg_credit_score,
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 不同信用评分段的利率
    ROUND(AVG(interest_rate) * 100, 2) AS avg_interest_rate_percent
FROM credit_loans
GROUP BY credit_score_range
ORDER BY MIN(credit_score);

-- ============================================================================
-- 5. 贷款产品分析
-- ============================================================================

-- 5.1 贷款金额分布分析
SELECT
    CASE
        WHEN loan_amount < 10000 THEN '<10k'
        WHEN loan_amount BETWEEN 10000 AND 49999 THEN '10k-49k'
        WHEN loan_amount BETWEEN 50000 AND 99999 THEN '50k-99k'
        WHEN loan_amount BETWEEN 100000 AND 199999 THEN '100k-199k'
        WHEN loan_amount BETWEEN 200000 AND 499999 THEN '200k-499k'
        ELSE '500k+'
    END AS loan_amount_range,

    COUNT(*) AS loan_count,
    ROUND(MIN(loan_amount), 2) AS min_amount,
    ROUND(MAX(loan_amount), 2) AS max_amount,
    ROUND(AVG(loan_amount), 2) AS avg_amount,
    SUM(loan_amount) AS total_amount,
    ROUND(SUM(loan_amount) * 100.0 / (SELECT SUM(loan_amount) FROM credit_loans), 2) AS amount_percentage,

    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 平均利率
    ROUND(AVG(interest_rate) * 100, 2) AS avg_interest_rate_percent
FROM credit_loans
GROUP BY loan_amount_range
ORDER BY MIN(loan_amount);

-- 5.2 贷款期限分析
SELECT
    loan_term,
    COUNT(*) AS loan_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM credit_loans), 2) AS percentage,
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,
    ROUND(AVG(interest_rate) * 100, 2) AS avg_interest_rate_percent,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 月供计算（假设等额本息）
    ROUND(AVG(loan_amount * interest_rate / 12 * POWER(1 + interest_rate / 12, loan_term) /
          (POWER(1 + interest_rate / 12, loan_term) - 1)), 2) AS estimated_monthly_payment
FROM credit_loans
GROUP BY loan_term
ORDER BY loan_term;

-- 5.3 贷款利率分析
SELECT
    ROUND(interest_rate * 100, 1) AS interest_rate_percent,
    COUNT(*) AS loan_count,
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,
    ROUND(AVG(credit_score), 0) AS avg_credit_score,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 平均贷款期限
    ROUND(AVG(loan_term), 1) AS avg_loan_term
FROM credit_loans
GROUP BY ROUND(interest_rate * 100, 1)
ORDER BY interest_rate_percent;

-- ============================================================================
-- 6. 风险分析
-- ============================================================================

-- 6.1 负债收入比 (DTI) 分析
WITH dti_calculated AS (
    SELECT
        *,
        -- 计算DTI（假设有月负债字段）
        monthly_debt / NULLIF(monthly_income, 0) AS dti_ratio
    FROM credit_loans
    WHERE monthly_income > 0
)
SELECT
    CASE
        WHEN dti_ratio < 0.3 THEN '<30%'
        WHEN dti_ratio BETWEEN 0.3 AND 0.4 THEN '30%-40%'
        WHEN dti_ratio BETWEEN 0.4 AND 0.5 THEN '40%-50%'
        WHEN dti_ratio BETWEEN 0.5 AND 0.6 THEN '50%-60%'
        ELSE '>60%'
    END AS dti_range,

    COUNT(*) AS loan_count,
    ROUND(MIN(dti_ratio) * 100, 1) AS min_dti_percent,
    ROUND(MAX(dti_ratio) * 100, 1) AS max_dti_percent,
    ROUND(AVG(dti_ratio) * 100, 1) AS avg_dti_percent,
    ROUND(AVG(credit_score), 0) AS avg_credit_score,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent
FROM dti_calculated
GROUP BY dti_range
ORDER BY MIN(dti_ratio);

-- 6.2 风险评分模型特征分析
SELECT
    -- 年龄风险因子
    CASE
        WHEN age < 25 THEN '高风险'
        WHEN age BETWEEN 25 AND 35 THEN '中高风险'
        WHEN age BETWEEN 36 AND 50 THEN '中等风险'
        WHEN age BETWEEN 51 AND 65 THEN '中低风险'
        ELSE '低风险'
    END AS age_risk_category,

    -- 信用评分风险因子
    CASE
        WHEN credit_score < 500 THEN '极高风险'
        WHEN credit_score BETWEEN 500 AND 600 THEN '高风险'
        WHEN credit_score BETWEEN 601 AND 700 THEN '中等风险'
        WHEN credit_score BETWEEN 701 AND 800 THEN '低风险'
        ELSE '极低风险'
    END AS credit_risk_category,

    -- 贷款收入比风险因子
    CASE
        WHEN loan_amount / NULLIF(monthly_income, 0) < 2 THEN '低风险'
        WHEN loan_amount / NULLIF(monthly_income, 0) BETWEEN 2 AND 4 THEN '中等风险'
        WHEN loan_amount / NULLIF(monthly_income, 0) BETWEEN 4 AND 6 THEN '高风险'
        ELSE '极高风险'
    END AS lti_risk_category,

    COUNT(*) AS loan_count,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent
FROM credit_loans
WHERE monthly_income > 0
GROUP BY age_risk_category, credit_risk_category, lti_risk_category
ORDER BY default_rate_percent DESC;

-- 6.3 风险集中度分析
-- 按客户的风险敞口排序
SELECT
    customer_id,
    COUNT(*) AS loan_count,
    SUM(loan_amount) AS total_exposure,
    SUM(CASE WHEN default_flag = 1 THEN loan_amount ELSE 0 END) AS default_exposure,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN loan_amount ELSE 0 END) * 100.0 / SUM(loan_amount), 2) AS default_rate_by_amount,

    -- 客户平均特征
    ROUND(AVG(credit_score), 0) AS avg_credit_score,
    ROUND(AVG(monthly_income), 2) AS avg_monthly_income,
    ROUND(AVG(age), 1) AS avg_age
FROM credit_loans
GROUP BY customer_id
HAVING SUM(loan_amount) > 100000  -- 仅看大额风险敞口
ORDER BY total_exposure DESC
LIMIT 20;

-- ============================================================================
-- 7. 窗口函数与高级分析
-- ============================================================================

-- 7.1 客户行为时间序列分析
SELECT
    customer_id,
    loan_date,
    loan_amount,
    default_flag,

    -- 累计指标
    SUM(loan_amount) OVER (PARTITION BY customer_id ORDER BY loan_date) AS cumulative_loan_amount,
    COUNT(*) OVER (PARTITION BY customer_id ORDER BY loan_date) AS loan_sequence,

    -- 时间间隔
    DATEDIFF(loan_date, LAG(loan_date) OVER (PARTITION BY customer_id ORDER BY loan_date)) AS days_since_last_loan,

    -- 滚动违约率（过去3笔贷款）
    AVG(default_flag) OVER (
        PARTITION BY customer_id
        ORDER BY loan_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_default_rate_3loans,

    -- 客户总体指标
    SUM(default_flag) OVER (PARTITION BY customer_id) AS total_defaults,
    COUNT(*) OVER (PARTITION BY customer_id) AS total_loans,
    SUM(loan_amount) OVER (PARTITION BY customer_id) AS total_borrowed
FROM credit_loans
ORDER BY customer_id, loan_date;

-- 7.2 贷款金额排名分析
SELECT
    loan_id,
    customer_id,
    loan_date,
    loan_amount,
    default_flag,

    -- 绝对排名
    ROW_NUMBER() OVER (ORDER BY loan_amount DESC) AS amount_rank_all,
    RANK() OVER (ORDER BY loan_amount DESC) AS amount_rank_with_ties,
    DENSE_RANK() OVER (ORDER BY loan_amount DESC) AS amount_dense_rank,

    -- 分组排名（按年份）
    ROW_NUMBER() OVER (PARTITION BY YEAR(loan_date) ORDER BY loan_amount DESC) AS amount_rank_by_year,

    -- 百分比排名
    PERCENT_RANK() OVER (ORDER BY loan_amount) AS amount_percent_rank,

    -- 贷款金额分位数
    NTILE(4) OVER (ORDER BY loan_amount) AS amount_quartile,
    NTILE(10) OVER (ORDER BY loan_amount) AS amount_decile,

    -- 相对于平均值的偏差
    loan_amount - AVG(loan_amount) OVER () AS amount_deviation_from_mean,
    loan_amount / AVG(loan_amount) OVER () AS amount_relative_to_mean
FROM credit_loans
ORDER BY loan_amount DESC
LIMIT 20;

-- 7.3 移动窗口分析（按月）
WITH monthly_stats AS (
    SELECT
        DATE_FORMAT(loan_date, '%Y-%m') AS year_month,
        COUNT(*) AS loan_count,
        SUM(loan_amount) AS total_amount,
        SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count
    FROM credit_loans
    GROUP BY DATE_FORMAT(loan_date, '%Y-%m')
)
SELECT
    year_month,
    loan_count,
    total_amount,
    default_count,
    ROUND(default_count * 100.0 / loan_count, 2) AS default_rate_percent,

    -- 移动平均（3个月）
    ROUND(AVG(loan_count) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 1) AS moving_avg_loan_count_3m,
    ROUND(AVG(total_amount) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_amount_3m,
    ROUND(AVG(default_count * 100.0 / loan_count) OVER (ORDER BY year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_default_rate_3m,

    -- 累计指标
    SUM(loan_count) OVER (ORDER BY year_month) AS cumulative_loan_count,
    SUM(total_amount) OVER (ORDER BY year_month) AS cumulative_total_amount
FROM monthly_stats
ORDER BY year_month;

-- ============================================================================
-- 8. 多表关联分析
-- ============================================================================

-- 8.1 客户信息与贷款信息关联
SELECT
    c.customer_id,
    c.customer_name,
    c.join_date,
    c.city,
    c.education_level,

    -- 贷款汇总信息
    COUNT(l.loan_id) AS total_loans,
    SUM(l.loan_amount) AS total_borrowed,
    MAX(l.loan_date) AS latest_loan_date,
    MIN(l.loan_date) AS first_loan_date,

    -- 违约信息
    SUM(CASE WHEN l.default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    SUM(CASE WHEN l.default_flag = 1 THEN l.loan_amount ELSE 0 END) AS default_amount,

    -- 客户当前状态
    CASE
        WHEN SUM(CASE WHEN l.default_flag = 1 THEN 1 ELSE 0 END) > 0 THEN '有违约记录'
        WHEN COUNT(l.loan_id) = 0 THEN '无贷款记录'
        ELSE '正常客户'
    END AS customer_status,

    -- 平均特征
    ROUND(AVG(l.credit_score), 0) AS avg_credit_score,
    ROUND(AVG(l.loan_amount), 2) AS avg_loan_amount,
    ROUND(AVG(l.interest_rate) * 100, 2) AS avg_interest_rate_percent
FROM customers c
LEFT JOIN credit_loans l ON c.customer_id = l.customer_id
GROUP BY c.customer_id, c.customer_name, c.join_date, c.city, c.education_level
ORDER BY total_borrowed DESC
LIMIT 20;

-- 8.2 还款记录分析
SELECT
    l.loan_id,
    l.customer_id,
    l.loan_amount,
    l.loan_date,
    l.default_flag,

    -- 还款汇总
    COUNT(r.payment_id) AS total_payments,
    SUM(r.payment_amount) AS total_paid,
    MAX(r.payment_date) AS latest_payment_date,
    MIN(r.payment_date) AS first_payment_date,

    -- 还款状态
    CASE
        WHEN l.default_flag = 1 THEN '已违约'
        WHEN COUNT(r.payment_id) = 0 THEN '未开始还款'
        WHEN SUM(r.payment_amount) >= l.loan_amount THEN '已还清'
        ELSE '还款中'
    END AS repayment_status,

    -- 还款进度
    ROUND(SUM(r.payment_amount) * 100.0 / l.loan_amount, 2) AS repayment_percentage,

    -- 逾期情况
    SUM(CASE WHEN r.is_delayed = 1 THEN 1 ELSE 0 END) AS delayed_payments_count,
    MAX(r.delay_days) AS max_delay_days
FROM credit_loans l
LEFT JOIN repayments r ON l.loan_id = r.loan_id
GROUP BY l.loan_id, l.customer_id, l.loan_amount, l.loan_date, l.default_flag
ORDER BY l.loan_date DESC
LIMIT 20;

-- ============================================================================
-- 9. 数据质量检查
-- ============================================================================

-- 9.1 缺失值检查
SELECT
    'credit_loans' AS table_name,
    'credit_score' AS column_name,
    COUNT(*) AS total_rows,
    SUM(CASE WHEN credit_score IS NULL THEN 1 ELSE 0 END) AS missing_count,
    ROUND(SUM(CASE WHEN credit_score IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS missing_percentage
FROM credit_loans
UNION ALL
SELECT
    'credit_loans',
    'monthly_income',
    COUNT(*),
    SUM(CASE WHEN monthly_income IS NULL THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN monthly_income IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
FROM credit_loans
UNION ALL
SELECT
    'credit_loans',
    'loan_amount',
    COUNT(*),
    SUM(CASE WHEN loan_amount IS NULL THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN loan_amount IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2)
FROM credit_loans
ORDER BY missing_percentage DESC;

-- 9.2 异常值检测
SELECT
    'monthly_income' AS column_name,
    ROUND(MIN(monthly_income), 2) AS min_value,
    ROUND(MAX(monthly_income), 2) AS max_value,
    ROUND(AVG(monthly_income), 2) AS avg_value,
    ROUND(STDDEV(monthly_income), 2) AS std_value,
    COUNT(CASE WHEN monthly_income < 1000 OR monthly_income > 100000 THEN 1 END) AS outlier_count,
    ROUND(COUNT(CASE WHEN monthly_income < 1000 OR monthly_income > 100000 THEN 1 END) * 100.0 / COUNT(*), 2) AS outlier_percentage
FROM credit_loans
UNION ALL
SELECT
    'loan_amount',
    ROUND(MIN(loan_amount), 2),
    ROUND(MAX(loan_amount), 2),
    ROUND(AVG(loan_amount), 2),
    ROUND(STDDEV(loan_amount), 2),
    COUNT(CASE WHEN loan_amount < 100 OR loan_amount > 1000000 THEN 1 END),
    ROUND(COUNT(CASE WHEN loan_amount < 100 OR loan_amount > 1000000 THEN 1 END) * 100.0 / COUNT(*), 2)
FROM credit_loans
UNION ALL
SELECT
    'age',
    MIN(age),
    MAX(age),
    ROUND(AVG(age), 1),
    ROUND(STDDEV(age), 1),
    COUNT(CASE WHEN age < 18 OR age > 100 THEN 1 END),
    ROUND(COUNT(CASE WHEN age < 18 OR age > 100 THEN 1 END) * 100.0 / COUNT(*), 2)
FROM credit_loans;

-- 9.3 数据一致性检查
-- 检查贷款日期是否合理
SELECT
    COUNT(*) AS invalid_dates,
    MIN(loan_date) AS earliest_date,
    MAX(loan_date) AS latest_date,
    SUM(CASE WHEN loan_date < '2000-01-01' OR loan_date > CURDATE() THEN 1 ELSE 0 END) AS out_of_range_dates
FROM credit_loans;

-- 检查利率范围
SELECT
    COUNT(*) AS invalid_interest_rates,
    MIN(interest_rate) AS min_rate,
    MAX(interest_rate) AS max_rate,
    SUM(CASE WHEN interest_rate < 0 OR interest_rate > 0.5 THEN 1 ELSE 0 END) AS out_of_range_rates
FROM credit_loans;

-- 检查贷款期限
SELECT
    COUNT(*) AS invalid_loan_terms,
    MIN(loan_term) AS min_term,
    MAX(loan_term) AS max_term,
    SUM(CASE WHEN loan_term < 1 OR loan_term > 360 THEN 1 ELSE 0 END) AS out_of_range_terms
FROM credit_loans;

-- 9.4 重复数据检查
SELECT
    customer_id,
    loan_date,
    loan_amount,
    COUNT(*) AS duplicate_count
FROM credit_loans
GROUP BY customer_id, loan_date, loan_amount
HAVING COUNT(*) > 1;

-- 检查同一客户同一天多笔贷款
SELECT
    customer_id,
    loan_date,
    COUNT(*) AS loans_on_same_day
FROM credit_loans
GROUP BY customer_id, loan_date
HAVING COUNT(*) > 1
ORDER BY loans_on_same_day DESC;

-- ============================================================================
-- 10. 业务KPI与仪表板查询
-- ============================================================================

-- 10.1 每日业务仪表板
SELECT
    DATE(loan_date) AS report_date,

    -- 业务量指标
    COUNT(DISTINCT customer_id) AS unique_customers,
    COUNT(*) AS total_loans,
    SUM(loan_amount) AS total_loan_amount,
    ROUND(AVG(loan_amount), 2) AS avg_loan_size,

    -- 新增客户（当天首次贷款）
    COUNT(DISTINCT CASE WHEN loan_date = customer_first_loan THEN customer_id END) AS new_customers,

    -- 违约指标
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    SUM(CASE WHEN default_flag = 1 THEN loan_amount ELSE 0 END) AS default_amount,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_by_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN loan_amount ELSE 0 END) * 100.0 / SUM(loan_amount), 2) AS default_rate_by_amount,

    -- 平均客户质量
    ROUND(AVG(credit_score), 0) AS avg_credit_score,
    ROUND(AVG(monthly_income), 2) AS avg_monthly_income,
    ROUND(AVG(age), 1) AS avg_age
FROM (
    SELECT
        *,
        MIN(loan_date) OVER (PARTITION BY customer_id) AS customer_first_loan
    FROM credit_loans
) subquery
GROUP BY DATE(loan_date)
ORDER BY report_date DESC
LIMIT 30;

-- 10.2 月度KPI汇总
SELECT
    DATE_FORMAT(loan_date, '%Y-%m') AS year_month,

    -- 业务规模
    COUNT(*) AS loan_count,
    SUM(loan_amount) AS total_loan_amount,
    COUNT(DISTINCT customer_id) AS unique_customers,

    -- 新增客户
    COUNT(DISTINCT CASE WHEN DATE_FORMAT(loan_date, '%Y-%m') = customer_first_month THEN customer_id END) AS new_customers,

    -- 违约情况
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent,

    -- 平均贷款特征
    ROUND(AVG(loan_amount), 2) AS avg_loan_amount,
    ROUND(AVG(interest_rate) * 100, 2) AS avg_interest_rate_percent,
    ROUND(AVG(credit_score), 0) AS avg_credit_score,

    -- 贷款产品结构
    ROUND(SUM(CASE WHEN loan_amount < 50000 THEN loan_amount ELSE 0 END) * 100.0 / SUM(loan_amount), 2) AS small_loans_percentage,
    ROUND(SUM(CASE WHEN loan_amount >= 50000 AND loan_amount < 200000 THEN loan_amount ELSE 0 END) * 100.0 / SUM(loan_amount), 2) AS medium_loans_percentage,
    ROUND(SUM(CASE WHEN loan_amount >= 200000 THEN loan_amount ELSE 0 END) * 100.0 / SUM(loan_amount), 2) AS large_loans_percentage
FROM (
    SELECT
        *,
        DATE_FORMAT(MIN(loan_date) OVER (PARTITION BY customer_id), '%Y-%m') AS customer_first_month
    FROM credit_loans
) subquery
GROUP BY DATE_FORMAT(loan_date, '%Y-%m')
ORDER BY year_month DESC
LIMIT 12;

-- 10.3 风险KPI监控
SELECT
    '整体' AS segment,

    -- 风险指标
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4) * 100 AS PD_percent,

    -- 假设LGD为40%
    40.0 AS LGD_percent,

    -- 计算EL
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 4) * 40.0 AS EL_percent,

    -- 风险集中度
    ROUND(MAX(top10_exposure) * 100.0 / SUM(loan_amount), 2) AS top10_concentration_percent,

    -- 平均风险评分
    ROUND(AVG(
        CASE
            WHEN credit_score < 500 THEN 100
            WHEN credit_score BETWEEN 500 AND 600 THEN 80
            WHEN credit_score BETWEEN 601 AND 700 THEN 60
            WHEN credit_score BETWEEN 701 AND 800 THEN 40
            ELSE 20
        END
    ), 1) AS avg_risk_score
FROM credit_loans
CROSS JOIN (
    SELECT SUM(loan_amount) AS top10_exposure
    FROM (
        SELECT
            customer_id,
            SUM(loan_amount) AS total_exposure
        FROM credit_loans
        GROUP BY customer_id
        ORDER BY total_exposure DESC
        LIMIT 10
    ) top_customers
) concentration;

-- ============================================================================
-- 11. 优化与性能查询
-- ============================================================================

-- 11.1 创建索引建议
/*
-- 常用查询字段建议创建索引
CREATE INDEX idx_loan_date ON credit_loans(loan_date);
CREATE INDEX idx_customer_id ON credit_loans(customer_id);
CREATE INDEX idx_default_flag ON credit_loans(default_flag);
CREATE INDEX idx_credit_score ON credit_loans(credit_score);
CREATE INDEX idx_loan_amount ON credit_loans(loan_amount);

-- 复合索引（用于多条件查询）
CREATE INDEX idx_customer_loan ON credit_loans(customer_id, loan_date);
CREATE INDEX idx_risk_indicators ON credit_loans(credit_score, monthly_income, default_flag);
*/

-- 11.2 查询性能分析
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS loan_count,
    SUM(loan_amount) AS total_borrowed
FROM credit_loans
WHERE loan_date >= '2023-01-01'
GROUP BY customer_id
HAVING SUM(loan_amount) > 100000;

-- 11.3 分区表建议（大数据量时）
/*
-- 按时间分区（适用于时间序列数据）
CREATE TABLE credit_loans_partitioned (
    -- 表结构相同
    ...
)
PARTITION BY RANGE (YEAR(loan_date)) (
    PARTITION p2020 VALUES LESS THAN (2021),
    PARTITION p2021 VALUES LESS THAN (2022),
    PARTITION p2022 VALUES LESS THAN (2023),
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
*/

-- ============================================================================
-- 12. 实用查询模板
-- ============================================================================

-- 12.1 客户画像查询模板
/*
SELECT
    [选择客户特征字段],
    COUNT(*) AS customer_count,
    [添加聚合指标]
FROM customers c
JOIN credit_loans l ON c.customer_id = l.customer_id
GROUP BY [客户特征字段]
ORDER BY [排序字段];
*/

-- 12.2 风险分析查询模板
/*
SELECT
    [风险维度字段],
    COUNT(*) AS loan_count,
    SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) AS default_count,
    ROUND(SUM(CASE WHEN default_flag = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS default_rate_percent
FROM credit_loans
WHERE [筛选条件]
GROUP BY [风险维度字段]
HAVING [结果筛选条件]
ORDER BY default_rate_percent DESC;
*/

-- 12.3 时间序列分析模板
/*
WITH time_series AS (
    SELECT
        DATE_FORMAT(loan_date, '[时间粒度]') AS time_period,
        [聚合指标]
    FROM credit_loans
    WHERE loan_date BETWEEN [开始时间] AND [结束时间]
    GROUP BY DATE_FORMAT(loan_date, '[时间粒度]')
)
SELECT
    time_period,
    [聚合指标],
    -- 移动平均
    AVG([指标]) OVER (ORDER BY time_period ROWS BETWEEN [N] PRECEDING AND CURRENT ROW) AS moving_avg,
    -- 环比增长
    ([指标] - LAG([指标]) OVER (ORDER BY time_period)) / NULLIF(LAG([指标]) OVER (ORDER BY time_period), 0) * 100 AS growth_rate
FROM time_series
ORDER BY time_period;
*/

-- ============================================================================
-- 使用说明
-- ============================================================================

/*
1. 查询分类说明:
   - 第1-2节: 基础查询和数据探索
   - 第3-5节: 业务指标和客户分析
   - 第6节: 风险分析
   - 第7节: 高级分析（窗口函数）
   - 第8节: 多表关联分析
   - 第9节: 数据质量检查
   - 第10节: KPI和仪表板查询
   - 第11节: 性能优化
   - 第12节: 查询模板

2. 使用建议:
   - 根据实际表结构调整字段名
   - 大数据量时使用LIMIT限制结果
   - 定期运行数据质量检查查询
   - 根据业务需求修改风险阈值

3. 性能优化:
   - 为常用查询字段创建索引
   - 大数据表考虑分区
   - 复杂查询使用WITH子句提高可读性
   - 定期分析查询执行计划
*/

-- 查询版本信息
SELECT
    '信贷数据分析SQL查询集合' AS title,
    '版本: 1.0' AS version,
    '最后更新: 2024-01-15' AS last_updated,
    '适用数据库: MySQL/PostgreSQL/SQL Server' AS compatible_databases;