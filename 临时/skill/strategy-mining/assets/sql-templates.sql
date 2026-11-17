-- ============================================================================
-- SQL Templates for Strategy Mining
-- ============================================================================

-- ============================================================================
-- 1. 样本表基础查询
-- ============================================================================

-- 1.1 贷前样本基础查询
SELECT 
    apply_no,
    cust_no,
    apply_time,
    close_datetime,
    fpd_k30,
    if_out_30d,
    if_out_60d,
    if_in_30d,
    if_in_60d
FROM d_dq.dfs_dq_fqz_base_final
WHERE dt BETWEEN '20260101' AND '20260630'
  AND fpd_k30 >= 0;  -- 排除未观察期样本

-- 1.2 贷中样本基础查询
SELECT 
    order_no,
    cust_no,
    trans_seqno,
    create_date,
    fpd_k30,
    if_out_30d,
    if_out_60d,
    if_in_30d,
    if_in_60d
FROM d_dq.dfs_dz_fqz_base_final
WHERE dt BETWEEN '20260101' AND '20260630'
  AND fpd_k30 >= 0;

-- ============================================================================
-- 2. 宽表特征拼接
-- ============================================================================

-- 2.1 贷前样本 + 宽表特征
SELECT 
    base.apply_no,
    base.cust_no,
    base.apply_time,
    base.fpd_k30,
    base.if_out_30d,
    base.if_in_30d,
    -- 通讯录特征
    wide.txl_relation_apply_n_cust_num,
    wide.txl_relation_cust_cnt,
    wide.txl_black_mobile_cnt,
    wide.txl_history_overdue_days_pct,
    -- 通话记录特征
    wide.call_record_total_cnt,
    wide.call_record_relation_cust_cnt,
    wide.call_record_black_mobile_cnt,
    -- APPLIST特征
    wide.f_dq_app_total_cnt,
    wide.f_dq_app_loan_cnt,
    wide.fqz_q_black_app_cnt,
    -- 设备特征
    wide.t_bs_device_cust_cnt,
    wide.t_bs_device_root_flag
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
    ON base.apply_no = wide.apply_no
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0;

-- 2.2 贷中样本 + 宽表特征
SELECT 
    base.order_no,
    base.cust_no,
    base.trans_seqno,
    base.create_date,
    base.fpd_k30,
    base.if_out_30d,
    base.if_in_30d,
    -- 通讯录特征
    wide.txl_relation_apply_n_cust_num,
    wide.txl_relation_cust_cnt,
    wide.txl_black_mobile_cnt,
    -- 通话记录特征
    wide.call_record_total_cnt,
    wide.call_record_relation_cust_cnt,
    -- APPLIST特征
    wide.f_dq_app_total_cnt,
    wide.f_dq_app_loan_cnt,
    -- 设备特征
    wide.t_bs_device_cust_cnt,
    wide.rt_rt_device_2degree_cust_cnt
FROM d_dq.dfs_dz_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_rms_df wide 
    ON base.order_no = wide.order_no
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0;

-- ============================================================================
-- 3. 客群筛选
-- ============================================================================

-- 3.1 APP渠道客群筛选
WHERE base.apply_channel = 'APP'  -- 或 base.channel_type = 'APP'

-- 3.2 API渠道客群筛选
WHERE base.apply_channel = 'API'  -- 或 base.channel_type = 'API'

-- 3.3 新客筛选
WHERE base.is_new_cust = 1  -- 或 base.cust_type = 'NEW'

-- 3.4 老客筛选
WHERE base.is_new_cust = 0  -- 或 base.cust_type = 'OLD'

-- 3.5 组合筛选示例
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0
  AND base.apply_channel = 'APP'
  AND base.is_new_cust = 1;

-- ============================================================================
-- 4. 从原始表衍生特征
-- ============================================================================

-- 4.1 通讯录特征衍生
-- 4.1.1 联系人数量统计
SELECT 
    apply_no,
    COUNT(DISTINCT contact_phone) as contact_total_cnt,
    COUNT(DISTINCT CASE WHEN relation_type = 'family' THEN contact_phone END) as family_cnt,
    COUNT(DISTINCT CASE WHEN relation_type = 'friend' THEN contact_phone END) as friend_cnt,
    COUNT(DISTINCT CASE WHEN relation_type = 'colleague' THEN contact_phone END) as colleague_cnt
FROM t_bd_cust_relation_info
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY apply_no;

-- 4.1.2 近N天新增联系人统计
SELECT 
    apply_no,
    COUNT(DISTINCT CASE 
        WHEN DATEDIFF(apply_time, add_time) <= 7 THEN contact_phone 
    END) as recent_7d_cnt,
    COUNT(DISTINCT CASE 
        WHEN DATEDIFF(apply_time, add_time) <= 30 THEN contact_phone 
    END) as recent_30d_cnt,
    COUNT(DISTINCT CASE 
        WHEN DATEDIFF(apply_time, add_time) <= 90 THEN contact_phone 
    END) as recent_90d_cnt
FROM t_bd_cust_relation_info
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY apply_no;

-- 4.2 通话记录特征衍生
-- 4.2.1 通话统计
SELECT 
    apply_no,
    COUNT(*) as call_total_cnt,
    SUM(call_duration) as call_total_duration,
    AVG(call_duration) as call_avg_duration,
    COUNT(DISTINCT call_number) as call_unique_contact_cnt,
    SUM(CASE WHEN HOUR(call_time) BETWEEN 22 AND 23 OR HOUR(call_time) < 6 THEN 1 ELSE 0 END) as night_call_cnt,
    SUM(CASE WHEN DAYOFWEEK(call_time) IN (1, 7) THEN 1 ELSE 0 END) as weekend_call_cnt
FROM t_bd_local_calls_records
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY apply_no;

-- 4.2.2 近期通话统计
SELECT 
    apply_no,
    COUNT(CASE WHEN DATEDIFF(apply_time, call_time) <= 7 THEN 1 END) as recent_7d_call_cnt,
    COUNT(CASE WHEN DATEDIFF(apply_time, call_time) <= 30 THEN 1 END) as recent_30d_call_cnt,
    COUNT(CASE WHEN DATEDIFF(apply_time, call_time) <= 90 THEN 1 END) as recent_90d_call_cnt
FROM t_bd_local_calls_records
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY apply_no;

-- 4.3 APPLIST特征衍生
-- 4.3.1 应用统计
SELECT 
    apply_no,
    COUNT(DISTINCT app_package) as app_total_cnt,
    COUNT(DISTINCT CASE WHEN app_category = 'finance' THEN app_package END) as finance_app_cnt,
    COUNT(DISTINCT CASE WHEN app_category = 'loan' THEN app_package END) as loan_app_cnt,
    COUNT(DISTINCT CASE WHEN app_category = 'gambling' THEN app_package END) as gambling_app_cnt,
    COUNT(DISTINCT CASE WHEN app_category = 'game' THEN app_package END) as game_app_cnt,
    COUNT(DISTINCT CASE WHEN is_system_app = 0 THEN app_package END) as non_system_app_cnt
FROM t_bd_credit_cust_app_info
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY apply_no;

-- 4.3.2 近期安装应用统计
SELECT 
    apply_no,
    COUNT(DISTINCT CASE 
        WHEN DATEDIFF(apply_time, install_time) <= 7 THEN app_package 
    END) as recent_7d_app_cnt,
    COUNT(DISTINCT CASE 
        WHEN DATEDIFF(apply_time, install_time) <= 30 THEN app_package 
    END) as recent_30d_app_cnt,
    COUNT(DISTINCT CASE 
        WHEN DATEDIFF(apply_time, install_time) <= 90 THEN app_package 
    END) as recent_90d_app_cnt
FROM t_bd_credit_cust_app_info
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY apply_no;

-- 4.4 设备特征衍生
-- 4.4.1 SMY设备关联统计
SELECT 
    device_id,
    COUNT(DISTINCT cust_no) as device_cust_cnt,
    COUNT(DISTINCT apply_no) as device_apply_cnt
FROM smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY device_id;

-- 4.4.2 TD设备关联统计
SELECT 
    device_id,
    COUNT(DISTINCT cust_no) as device_cust_cnt,
    COUNT(DISTINCT apply_no) as device_apply_cnt
FROM smy_pc_tmp.uld_dwd.dwd_risk_rms_rt_device_log_di
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY device_id;

-- 4.4.3 BS设备关联统计（含跨端）
SELECT 
    cross_device_id,
    COUNT(DISTINCT device_id) as unique_device_cnt,
    COUNT(DISTINCT cust_no) as cross_device_cust_cnt,
    COUNT(DISTINCT apply_no) as cross_device_apply_cnt
FROM smy_pc_tmp.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY cross_device_id;

-- 4.5 紧急联系人特征衍生
SELECT 
    cust_no,
    COUNT(DISTINCT relation_phone) as emergency_contact_cnt,
    COUNT(DISTINCT CASE WHEN relation_type = 'parent' THEN relation_phone END) as parent_cnt,
    COUNT(DISTINCT CASE WHEN relation_type = 'spouse' THEN relation_phone END) as spouse_cnt,
    COUNT(DISTINCT CASE WHEN relation_type = 'friend' THEN relation_phone END) as friend_cnt
FROM t_cif_cst_cust_immediate_relation_info
WHERE dt BETWEEN '20260101' AND '20260630'
GROUP BY cust_no;

-- ============================================================================
-- 5. 完整分析SQL模板
-- ============================================================================

-- 5.1 通讯录特征分析（贷前+线上特征）
SELECT 
    base.apply_no,
    base.cust_no,
    base.fpd_k30,
    base.if_out_30d,
    base.if_in_30d,
    -- 线上特征
    wide.txl_relation_cust_cnt,
    wide.txl_black_mobile_cnt,
    wide.txl_history_overdue_days_pct
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
    ON base.apply_no = wide.apply_no
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0;

-- 5.2 通讯录特征分析（贷前+衍生特征）
WITH contact_features AS (
    SELECT 
        apply_no,
        COUNT(DISTINCT contact_phone) as contact_total_cnt,
        COUNT(DISTINCT CASE WHEN DATEDIFF(apply_time, add_time) <= 30 THEN contact_phone END) as recent_30d_cnt
    FROM t_bd_cust_relation_info
    WHERE dt BETWEEN '20260101' AND '20260630'
    GROUP BY apply_no
)
SELECT 
    base.apply_no,
    base.cust_no,
    base.fpd_k30,
    base.if_out_30d,
    base.if_in_30d,
    feat.contact_total_cnt,
    feat.recent_30d_cnt
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN contact_features feat 
    ON base.apply_no = feat.apply_no
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0;

-- 5.3 设备特征分析（贷中+跨端）
WITH device_features AS (
    SELECT 
        device_id,
        cross_device_id,
        COUNT(DISTINCT cust_no) as cross_device_cust_cnt
    FROM smy_pc_tmp.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di
    WHERE dt BETWEEN '20260101' AND '20260630'
    GROUP BY device_id, cross_device_id
)
SELECT 
    base.order_no,
    base.cust_no,
    base.fpd_k30,
    base.if_out_30d,
    base.if_in_30d,
    wide.t_bs_device_cust_cnt,
    dev.cross_device_cust_cnt
FROM d_dq.dfs_dz_fqz_base_final base
LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_rms_df wide 
    ON base.order_no = wide.order_no
LEFT JOIN smy_pc_tmp.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di device
    ON base.apply_no = device.apply_no
LEFT JOIN device_features dev
    ON device.device_id = dev.device_id
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0;

-- 5.4 多数据源组合分析
WITH applist_features AS (
    SELECT 
        apply_no,
        COUNT(DISTINCT app_package) as app_total_cnt,
        COUNT(DISTINCT CASE WHEN app_category = 'loan' THEN app_package END) as loan_app_cnt
    FROM t_bd_credit_cust_app_info
    WHERE dt BETWEEN '20260101' AND '20260630'
    GROUP BY apply_no
),
contact_features AS (
    SELECT 
        apply_no,
        COUNT(DISTINCT contact_phone) as contact_total_cnt
    FROM t_bd_cust_relation_info
    WHERE dt BETWEEN '20260101' AND '20260630'
    GROUP BY apply_no
),
call_features AS (
    SELECT 
        apply_no,
        COUNT(*) as call_total_cnt,
        COUNT(DISTINCT call_number) as call_unique_contact_cnt
    FROM t_bd_local_calls_records
    WHERE dt BETWEEN '20260101' AND '20260630'
    GROUP BY apply_no
)
SELECT 
    base.apply_no,
    base.cust_no,
    base.fpd_k30,
    base.if_out_30d,
    base.if_in_30d,
    app.app_total_cnt,
    app.loan_app_cnt,
    contact.contact_total_cnt,
    call.call_total_cnt,
    call.call_unique_contact_cnt
FROM d_dq.dfs_dq_fqz_base_final base
LEFT JOIN applist_features app ON base.apply_no = app.apply_no
LEFT JOIN contact_features contact ON base.apply_no = contact.apply_no
LEFT JOIN call_features call ON base.apply_no = call.apply_no
WHERE base.dt BETWEEN '20260101' AND '20260630'
  AND base.fpd_k30 >= 0;

-- ============================================================================
-- 6. 策略效果分析模板
-- ============================================================================

-- 6.1 单特征分箱分析
SELECT 
    CASE 
        WHEN txl_relation_cust_cnt < 10 THEN 'A: <10'
        WHEN txl_relation_cust_cnt < 50 THEN 'B: 10-50'
        WHEN txl_relation_cust_cnt < 100 THEN 'C: 50-100'
        ELSE 'D: >=100'
    END as contact_cnt_bin,
    COUNT(*) as sample_cnt,
    SUM(fpd_k30) as bad_cnt,
    AVG(fpd_k30) as bad_rate,
    SUM(if_out_30d) as complaint_cnt,
    AVG(if_out_30d) as complaint_rate
FROM (
    SELECT 
        base.apply_no,
        base.fpd_k30,
        base.if_out_30d,
        wide.txl_relation_cust_cnt
    FROM d_dq.dfs_dq_fqz_base_final base
    LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
        ON base.apply_no = wide.apply_no
    WHERE base.dt BETWEEN '20260101' AND '20260630'
      AND base.fpd_k30 >= 0
) t
GROUP BY 1
ORDER BY 1;

-- 6.2 多特征组合策略评估
SELECT 
    '策略A: 通讯录<10 AND 贷款APP>5' as strategy_name,
    COUNT(*) as hit_cnt,
    SUM(fpd_k30) as bad_cnt,
    AVG(fpd_k30) as bad_rate,
    SUM(if_out_30d) as complaint_cnt,
    AVG(if_out_30d) as complaint_rate
FROM (
    SELECT 
        base.apply_no,
        base.fpd_k30,
        base.if_out_30d,
        wide.txl_relation_cust_cnt,
        wide.f_dq_app_loan_cnt
    FROM d_dq.dfs_dq_fqz_base_final base
    LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
        ON base.apply_no = wide.apply_no
    WHERE base.dt BETWEEN '20260101' AND '20260630'
      AND base.fpd_k30 >= 0
) t
WHERE txl_relation_cust_cnt < 10 AND f_dq_app_loan_cnt > 5;

-- 6.3 规则效果对比分析
WITH base_data AS (
    SELECT 
        base.apply_no,
        base.fpd_k30,
        base.if_out_30d,
        base.if_in_30d,
        wide.txl_relation_cust_cnt,
        wide.f_dq_app_loan_cnt,
        wide.t_bs_device_cust_cnt
    FROM d_dq.dfs_dq_fqz_base_final base
    LEFT JOIN dwh.gdm_risk_vars_dipa_task_wide_pcr_df wide 
        ON base.apply_no = wide.apply_no
    WHERE base.dt BETWEEN '20260101' AND '20260630'
      AND base.fpd_k30 >= 0
)
SELECT 
    'Rule1: 通讯录<10' as rule_name,
    COUNT(*) as hit_cnt,
    SUM(fpd_k30) as bad_cnt,
    AVG(fpd_k30) as bad_rate
FROM base_data
WHERE txl_relation_cust_cnt < 10

UNION ALL

SELECT 
    'Rule2: 贷款APP>5' as rule_name,
    COUNT(*) as hit_cnt,
    SUM(fpd_k30) as bad_cnt,
    AVG(fpd_k30) as bad_rate
FROM base_data
WHERE f_dq_app_loan_cnt > 5

UNION ALL

SELECT 
    'Rule3: 设备关联>100' as rule_name,
    COUNT(*) as hit_cnt,
    SUM(fpd_k30) as bad_cnt,
    AVG(fpd_k30) as bad_rate
FROM base_data
WHERE t_bs_device_cust_cnt > 100

UNION ALL

SELECT 
    'Rule4: Rule1 AND Rule2' as rule_name,
    COUNT(*) as hit_cnt,
    SUM(fpd_k30) as bad_cnt,
    AVG(fpd_k30) as bad_rate
FROM base_data
WHERE txl_relation_cust_cnt < 10 AND f_dq_app_loan_cnt > 5;
