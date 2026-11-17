-- ============================================================================
-- APP特征衍生SQL - 按风险标签和应用分类
-- 数据源: t_bd_credit_cust_app_info (原始APPLIST) + d_dq.dfs_applist_tag_new (标签表)
-- 防穿越原则: 仅使用样本时间点之前的APPLIST数据
-- ============================================================================

-- ============================================================================
-- 贷前版本 (Pre-loan)
-- 样本表: d_dq.dfs_dq_fqz_base_final
-- 时间边界: close_datetime
-- ============================================================================

WITH app_with_tag AS (
    SELECT 
        a.cust_no,
        a.app_name,
        a.app_package,
        a.app_install_datetime,
        -- 应用分类
        COALESCE(t.app_markcategories_desc, '其他') AS app_category,
        COALESCE(t.app_marksubcategory_desc, '其他') AS app_subcategory,
        -- 风险标签 (处理多标签情况，如"负面|诈骗")
        t.risk_label,
        COALESCE(t.risk_label_desc, '') AS risk_desc
    FROM `default`.t_bd_credit_cust_app_info a
    LEFT JOIN d_dq.dfs_applist_tag_new t
        ON a.app_name = t.app_name 
        OR a.app_package = t.app_package_name
    WHERE a.app_install_datetime IS NOT NULL
),
sample_with_features AS (
    SELECT 
        s.cust_no,
        s.apply_no,
        s.close_datetime,
        -- ========== 基础统计 ==========
        COUNT(DISTINCT at.app_name) AS app_total_cnt,  -- 总APP数量
        
        -- ========== 按风险标签分类 ==========
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%诈骗%' THEN at.app_name END) AS app_risk_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%负面%' THEN at.app_name END) AS app_risk_negative_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%赌博%' THEN at.app_name END) AS app_risk_gambling_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%涉黄%' THEN at.app_name END) AS app_risk_porn_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%网搜诈骗%' THEN at.app_name END) AS app_risk_online_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%刷单%' THEN at.app_name END) AS app_risk_brush_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc != '' AND at.risk_desc != '优质' AND at.risk_desc NOT LIKE '%优质%' THEN at.app_name END) AS app_risk_any_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%|%' THEN at.app_name END) AS app_risk_multi_cnt,  -- 多标签风险APP
        
        -- ========== 按应用分类 ==========
        COUNT(DISTINCT CASE WHEN at.app_category = '贷款' THEN at.app_name END) AS app_cat_loan_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '伪冒' THEN at.app_name END) AS app_cat_counterfeit_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '博彩游戏' THEN at.app_name END) AS app_cat_gambling_game_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '高风险投资' THEN at.app_name END) AS app_cat_high_risk_invest_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '赌博' THEN at.app_name END) AS app_cat_gambling_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '改机工具' THEN at.app_name END) AS app_cat_clone_tool_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '诈骗' THEN at.app_name END) AS app_cat_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '涉黄' THEN at.app_name END) AS app_cat_porn_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '赚钱' THEN at.app_name END) AS app_cat_money_making_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '传销' THEN at.app_name END) AS app_cat_pyramid_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '反催收' THEN at.app_name END) AS app_cat_anti_collection_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '跑分' THEN at.app_name END) AS app_cat_money_launder_cnt,
        
        -- ========== 细分子类 ==========
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '贷款_714' THEN at.app_name END) AS app_sub_loan_714_cnt,  -- 714高炮
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '贷款_网络小贷' THEN at.app_name END) AS app_sub_loan_online_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '伪冒类APP' THEN at.app_name END) AS app_sub_counterfeit_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '分身' THEN at.app_name END) AS app_sub_clone_cnt,  -- 分身工具
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '区块链' THEN at.app_name END) AS app_sub_blockchain_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '境外赌场' THEN at.app_name END) AS app_sub_overseas_gambling_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '疑似诈骗' THEN at.app_name END) AS app_sub_suspect_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '疑似传销' THEN at.app_name END) AS app_sub_suspect_pyramid_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory IN ('扑克棋牌', '彩票', '捕鱼类') THEN at.app_name END) AS app_sub_gambling_game_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '异性社交' THEN at.app_name END) AS app_sub_dating_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '股票类' THEN at.app_name END) AS app_sub_stock_cnt,
        
        -- ========== 比率特征 ==========
        CASE WHEN COUNT(DISTINCT at.app_name) > 0 
             THEN CAST(COUNT(DISTINCT CASE WHEN at.risk_desc != '' AND at.risk_desc != '优质' AND at.risk_desc NOT LIKE '%优质%' THEN at.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT at.app_name)
             ELSE 0 END AS app_risk_ratio,
        CASE WHEN COUNT(DISTINCT at.app_name) > 0 
             THEN CAST(COUNT(DISTINCT CASE WHEN at.app_category = '改机工具' THEN at.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT at.app_name)
             ELSE 0 END AS app_clone_ratio,
        CASE WHEN COUNT(DISTINCT at.app_name) > 0 
             THEN CAST(COUNT(DISTINCT CASE WHEN at.app_category = '贷款' THEN at.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT at.app_name)
             ELSE 0 END AS app_loan_ratio
    FROM d_dq.dfs_dq_fqz_base_final s
    LEFT JOIN app_with_tag at
        ON s.cust_no = at.cust_no
        AND at.app_install_datetime < s.close_datetime  -- 防穿越：仅使用申请前的APP
    WHERE s.close_datetime IS NOT NULL
    GROUP BY s.cust_no, s.apply_no, s.close_datetime
)
SELECT * FROM sample_with_features
LIMIT 1000;


-- ============================================================================
-- 贷中版本 (In-loan)
-- 样本表: d_dq.dfs_dz_fqz_base_final
-- 时间边界: create_datetime
-- ============================================================================

WITH app_with_tag AS (
    SELECT 
        a.cust_no,
        a.app_name,
        a.app_package,
        a.app_install_datetime,
        COALESCE(t.app_markcategories_desc, '其他') AS app_category,
        COALESCE(t.app_marksubcategory_desc, '其他') AS app_subcategory,
        t.risk_label,
        COALESCE(t.risk_label_desc, '') AS risk_desc
    FROM `default`.t_bd_credit_cust_app_info a
    LEFT JOIN d_dq.dfs_applist_tag_new t
        ON a.app_name = t.app_name 
        OR a.app_package = t.app_package_name
    WHERE a.app_install_datetime IS NOT NULL
),
sample_with_features AS (
    SELECT 
        s.cust_no,
        s.trans_seqno,
        s.order_no,
        s.rsk_log_id,
        s.create_datetime,
        -- ========== 基础统计 ==========
        COUNT(DISTINCT at.app_name) AS app_total_cnt,
        
        -- ========== 按风险标签分类 ==========
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%诈骗%' THEN at.app_name END) AS app_risk_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%负面%' THEN at.app_name END) AS app_risk_negative_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%赌博%' THEN at.app_name END) AS app_risk_gambling_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%涉黄%' THEN at.app_name END) AS app_risk_porn_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%网搜诈骗%' THEN at.app_name END) AS app_risk_online_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%刷单%' THEN at.app_name END) AS app_risk_brush_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc != '' AND at.risk_desc != '优质' AND at.risk_desc NOT LIKE '%优质%' THEN at.app_name END) AS app_risk_any_cnt,
        COUNT(DISTINCT CASE WHEN at.risk_desc LIKE '%|%' THEN at.app_name END) AS app_risk_multi_cnt,
        
        -- ========== 按应用分类 ==========
        COUNT(DISTINCT CASE WHEN at.app_category = '贷款' THEN at.app_name END) AS app_cat_loan_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '伪冒' THEN at.app_name END) AS app_cat_counterfeit_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '博彩游戏' THEN at.app_name END) AS app_cat_gambling_game_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '高风险投资' THEN at.app_name END) AS app_cat_high_risk_invest_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '赌博' THEN at.app_name END) AS app_cat_gambling_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '改机工具' THEN at.app_name END) AS app_cat_clone_tool_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '诈骗' THEN at.app_name END) AS app_cat_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '涉黄' THEN at.app_name END) AS app_cat_porn_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '赚钱' THEN at.app_name END) AS app_cat_money_making_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '传销' THEN at.app_name END) AS app_cat_pyramid_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '反催收' THEN at.app_name END) AS app_cat_anti_collection_cnt,
        COUNT(DISTINCT CASE WHEN at.app_category = '跑分' THEN at.app_name END) AS app_cat_money_launder_cnt,
        
        -- ========== 细分子类 ==========
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '贷款_714' THEN at.app_name END) AS app_sub_loan_714_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '贷款_网络小贷' THEN at.app_name END) AS app_sub_loan_online_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '伪冒类APP' THEN at.app_name END) AS app_sub_counterfeit_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '分身' THEN at.app_name END) AS app_sub_clone_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '区块链' THEN at.app_name END) AS app_sub_blockchain_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '境外赌场' THEN at.app_name END) AS app_sub_overseas_gambling_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '疑似诈骗' THEN at.app_name END) AS app_sub_suspect_fraud_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '疑似传销' THEN at.app_name END) AS app_sub_suspect_pyramid_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory IN ('扑克棋牌', '彩票', '捕鱼类') THEN at.app_name END) AS app_sub_gambling_game_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '异性社交' THEN at.app_name END) AS app_sub_dating_cnt,
        COUNT(DISTINCT CASE WHEN at.app_subcategory = '股票类' THEN at.app_name END) AS app_sub_stock_cnt,
        
        -- ========== 比率特征 ==========
        CASE WHEN COUNT(DISTINCT at.app_name) > 0 
             THEN CAST(COUNT(DISTINCT CASE WHEN at.risk_desc != '' AND at.risk_desc != '优质' AND at.risk_desc NOT LIKE '%优质%' THEN at.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT at.app_name)
             ELSE 0 END AS app_risk_ratio,
        CASE WHEN COUNT(DISTINCT at.app_name) > 0 
             THEN CAST(COUNT(DISTINCT CASE WHEN at.app_category = '改机工具' THEN at.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT at.app_name)
             ELSE 0 END AS app_clone_ratio,
        CASE WHEN COUNT(DISTINCT at.app_name) > 0 
             THEN CAST(COUNT(DISTINCT CASE WHEN at.app_category = '贷款' THEN at.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT at.app_name)
             ELSE 0 END AS app_loan_ratio
    FROM d_dq.dfs_dz_fqz_base_final s
    LEFT JOIN app_with_tag at
        ON s.cust_no = at.cust_no
        AND at.app_install_datetime < s.create_datetime  -- 防穿越：仅使用交易前的APP
    WHERE s.create_datetime IS NOT NULL
    GROUP BY s.cust_no, s.trans_seqno, s.order_no, s.rsk_log_id, s.create_datetime
)
SELECT * FROM sample_with_features
LIMIT 1000;

