-- APP特征衍生SQL - 贷中版本
-- 样本表: d_dq.dfs_dz_fqz_base_final
-- 时间边界: create_datetime
-- 执行引擎: StarRocks/Trino (CTAS语法)

DROP TABLE IF EXISTS d_dq.dfs_applist_risk_features_inloan_20260708 FORCE;

CREATE TABLE d_dq.dfs_applist_risk_features_inloan_20260708 AS
SELECT 
    s.cust_no,
    s.trans_seqno,
    s.order_no,
    s.rsk_log_id,
    s.create_datetime,
    s.risk_decision_result,
    s.cust_group_dz,
    s.new_old,
    s.fpd_k30,
    s.if_out_30d,
    s.if_out_60d,
    s.if_in_30d,
    s.if_in_60d,
    COUNT(DISTINCT a.app_name) AS app_total_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%诈骗%' THEN a.app_name END) AS app_risk_fraud_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%负面%' THEN a.app_name END) AS app_risk_negative_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%赌博%' THEN a.app_name END) AS app_risk_gambling_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%涉黄%' THEN a.app_name END) AS app_risk_porn_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%网搜诈骗%' THEN a.app_name END) AS app_risk_online_fraud_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%刷单%' THEN a.app_name END) AS app_risk_brush_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS app_risk_any_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%|%' THEN a.app_name END) AS app_risk_multi_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS app_cat_loan_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '伪冒' THEN a.app_name END) AS app_cat_counterfeit_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '博彩游戏' THEN a.app_name END) AS app_cat_gambling_game_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '高风险投资' THEN a.app_name END) AS app_cat_high_risk_invest_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '赌博' THEN a.app_name END) AS app_cat_gambling_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '改机工具' THEN a.app_name END) AS app_cat_clone_tool_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '诈骗' THEN a.app_name END) AS app_cat_fraud_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '涉黄' THEN a.app_name END) AS app_cat_porn_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '赚钱' THEN a.app_name END) AS app_cat_money_making_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '传销' THEN a.app_name END) AS app_cat_pyramid_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '反催收' THEN a.app_name END) AS app_cat_anti_collection_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '跑分' THEN a.app_name END) AS app_cat_money_launder_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '贷款_714' THEN a.app_name END) AS app_sub_loan_714_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '贷款_网络小贷' THEN a.app_name END) AS app_sub_loan_online_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '伪冒类APP' THEN a.app_name END) AS app_sub_counterfeit_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '分身' THEN a.app_name END) AS app_sub_clone_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '区块链' THEN a.app_name END) AS app_sub_blockchain_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '境外赌场' THEN a.app_name END) AS app_sub_overseas_gambling_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '疑似诈骗' THEN a.app_name END) AS app_sub_suspect_fraud_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '疑似传销' THEN a.app_name END) AS app_sub_suspect_pyramid_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') IN ('扑克棋牌', '彩票', '捕鱼类') THEN a.app_name END) AS app_sub_gambling_game_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '异性社交' THEN a.app_name END) AS app_sub_dating_cnt,
    COUNT(DISTINCT CASE WHEN COALESCE(t1.app_marksubcategory_desc, t2.app_marksubcategory_desc, '其他') = '股票类' THEN a.app_name END) AS app_sub_stock_cnt,
    CASE WHEN COUNT(DISTINCT a.app_name) > 0 
         THEN CAST(COUNT(DISTINCT CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT a.app_name)
         ELSE 0 END AS app_risk_ratio,
    CASE WHEN COUNT(DISTINCT a.app_name) > 0 
         THEN CAST(COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '改机工具' THEN a.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT a.app_name)
         ELSE 0 END AS app_clone_ratio,
    CASE WHEN COUNT(DISTINCT a.app_name) > 0 
         THEN CAST(COUNT(DISTINCT CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS DECIMAL(10,4)) / COUNT(DISTINCT a.app_name)
         ELSE 0 END AS app_loan_ratio,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 7 DAY) AND a.app_install_datetime < s.create_datetime THEN a.app_name END) AS app_total_cnt_7d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 7 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS app_risk_any_cnt_7d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 7 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS app_cat_loan_cnt_7d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 7 DAY) AND a.app_install_datetime < s.create_datetime AND (COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%诈骗%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%负面%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%赌博%') THEN a.app_name END) AS app_risk_high_cnt_7d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) AND a.app_install_datetime < s.create_datetime THEN a.app_name END) AS app_total_cnt_30d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS app_risk_any_cnt_30d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS app_cat_loan_cnt_30d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) AND a.app_install_datetime < s.create_datetime AND (COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%诈骗%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%负面%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%赌博%') THEN a.app_name END) AS app_risk_high_cnt_30d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 90 DAY) AND a.app_install_datetime < s.create_datetime THEN a.app_name END) AS app_total_cnt_90d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 90 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS app_risk_any_cnt_90d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 90 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS app_cat_loan_cnt_90d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 90 DAY) AND a.app_install_datetime < s.create_datetime AND (COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%诈骗%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%负面%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%赌博%') THEN a.app_name END) AS app_risk_high_cnt_90d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 180 DAY) AND a.app_install_datetime < s.create_datetime THEN a.app_name END) AS app_total_cnt_180d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 180 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS app_risk_any_cnt_180d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 180 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS app_cat_loan_cnt_180d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 180 DAY) AND a.app_install_datetime < s.create_datetime AND (COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%诈骗%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%负面%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%赌博%') THEN a.app_name END) AS app_risk_high_cnt_180d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) AND a.app_install_datetime < s.create_datetime THEN a.app_name END) AS app_total_cnt_365d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS app_risk_any_cnt_365d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_name END) AS app_cat_loan_cnt_365d,
    COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) AND a.app_install_datetime < s.create_datetime AND (COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%诈骗%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%负面%' OR COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') LIKE '%赌博%') THEN a.app_name END) AS app_risk_high_cnt_365d,
    CASE WHEN COUNT(DISTINCT CASE WHEN a.app_install_datetime < DATE_SUB(s.create_datetime, INTERVAL 30 DAY) THEN a.app_name END) > 0
         THEN CAST(COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 7 DAY) AND a.app_install_datetime < s.create_datetime THEN a.app_name END) AS DECIMAL(10,4)) 
              / NULLIF(COUNT(DISTINCT CASE WHEN a.app_install_datetime < DATE_SUB(s.create_datetime, INTERVAL 30 DAY) THEN a.app_name END), 0)
         ELSE 0 END AS app_install_velocity_7d_30d,
    CASE WHEN COUNT(DISTINCT CASE WHEN a.app_install_datetime < DATE_SUB(s.create_datetime, INTERVAL 90 DAY) AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) > 0
         THEN CAST(COUNT(DISTINCT CASE WHEN a.app_install_datetime >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) AND a.app_install_datetime < s.create_datetime AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END) AS DECIMAL(10,4)) 
              / NULLIF(COUNT(DISTINCT CASE WHEN a.app_install_datetime < DATE_SUB(s.create_datetime, INTERVAL 90 DAY) AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_name END), 0)
         ELSE 0 END AS app_risk_velocity_30d_90d,
    DATEDIFF(s.create_datetime, MAX(CASE WHEN COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') != '优质' AND COALESCE(t1.risk_label_desc, t2.risk_label_desc, '') NOT LIKE '%优质%' THEN a.app_install_datetime END)) AS app_risk_latest_days,
    DATEDIFF(s.create_datetime, MAX(CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '贷款' THEN a.app_install_datetime END)) AS app_loan_latest_days,
    DATEDIFF(s.create_datetime, MAX(CASE WHEN COALESCE(t1.app_markcategories_desc, t2.app_markcategories_desc, '其他') = '改机工具' THEN a.app_install_datetime END)) AS app_clone_latest_days
FROM d_dq.dfs_dz_fqz_base_final s
LEFT JOIN `default`.t_bd_credit_cust_app_info a
    ON s.cust_no = a.cust_no
    AND a.app_install_datetime < s.create_datetime
LEFT JOIN d_dq.dfs_applist_tag_new t1
    ON a.app_name = t1.app_name
LEFT JOIN d_dq.dfs_applist_tag_new t2
    ON a.app_package = t2.app_package_name
WHERE s.create_datetime IS NOT NULL
GROUP BY s.cust_no, s.trans_seqno, s.order_no, s.rsk_log_id, s.create_datetime,
    s.risk_decision_result, s.cust_group_dz, s.new_old,
    s.fpd_k30, s.if_out_30d, s.if_out_60d, s.if_in_30d, s.if_in_60d
