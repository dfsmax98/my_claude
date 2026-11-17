-- 设备特征衍生 - 贷中
-- 执行引擎: StarRocks/Trino (兼容CTAS语法)
-- 生成时间: 2026-07-08

DROP TABLE IF EXISTS d_dq.dfs_device_risk_features_inloan_20260708 FORCE;

CREATE TABLE d_dq.dfs_device_risk_features_inloan_20260708 AS
(
    WITH smy_device_log_filtered AS (
        SELECT rsk_log_id, device_id, device_type, risk_level, operation_type, device_time
        FROM smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di
        WHERE device_id IS NOT NULL
          AND device_id NOT IN ('', '[]')
          AND dt >= DATE_FORMAT(DATE_TRUNC('month', ADD_MONTHS(CURRENT_DATE, -12)), 'yyyy-MM-dd')
    ),
    bangsheng_fingerprint_filtered AS (
        SELECT bang_sheng_dfp, cust_no, device_type, create_time
        FROM smy_pc.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di
        WHERE bang_sheng_dfp IS NOT NULL
          AND dt >= DATE_FORMAT(DATE_TRUNC('month', ADD_MONTHS(CURRENT_DATE, -12)), 'yyyy-MM-dd')
    ),
    smy_agg AS (
        SELECT 
            d.rsk_log_id,
            COUNT(DISTINCT d.device_id) AS smy_device_unique_cnt,
            COUNT(DISTINCT CASE WHEN d.device_type = 'mobile' THEN d.device_id END) AS smy_mobile_cnt,
            COUNT(DISTINCT CASE WHEN d.risk_level = 'high' THEN d.device_id END) AS smy_high_risk_cnt,
            COUNT(DISTINCT CASE WHEN d.operation_type = 'login' THEN d.device_id END) AS smy_login_cnt,
            DATEDIFF(s.create_datetime, MAX(d.device_time)) AS smy_latest_device_days
        FROM d_dq.dfs_dz_fqz_base_final s
        LEFT JOIN smy_device_log_filtered d
            ON s.rsk_log_id = d.rsk_log_id
            AND d.device_time < s.create_datetime
        WHERE s.dt >= '20260101' AND s.create_datetime IS NOT NULL
        GROUP BY d.rsk_log_id, s.create_datetime
    ),
    bs_agg AS (
        SELECT 
            s.rsk_log_id,
            COUNT(DISTINCT f.bang_sheng_dfp) AS bs_device_unique_cnt,
            COUNT(DISTINCT CASE WHEN f.device_type IN ('rooted', 'emulator', 'proxy') THEN f.bang_sheng_dfp END) AS bs_abnormal_cnt,
            COUNT(DISTINCT f.cust_no) AS bs_cross_cust_cnt,
            COUNT(DISTINCT CASE WHEN f.create_time >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) THEN f.bang_sheng_dfp END) AS bs_recent_30d_cnt
        FROM d_dq.dfs_dz_fqz_base_final s
        LEFT JOIN bangsheng_fingerprint_filtered f
            ON s.cust_no = f.cust_no
            AND f.create_time < s.create_datetime
        WHERE s.dt >= '20260101' AND s.create_datetime IS NOT NULL
        GROUP BY s.rsk_log_id
    )
    SELECT 
        s.cust_no, s.order_no, s.trans_seqno, s.rsk_log_id, s.create_datetime,
        s.risk_decision_result, s.fpd_k30, s.if_out_30d, s.if_out_60d,
        s.if_in_30d, s.if_in_60d, s.new_old,
        COALESCE(smy.smy_device_unique_cnt, 0) AS smy_device_unique_cnt,
        COALESCE(smy.smy_mobile_cnt, 0) AS smy_mobile_cnt,
        COALESCE(smy.smy_high_risk_cnt, 0) AS smy_high_risk_cnt,
        COALESCE(smy.smy_login_cnt, 0) AS smy_login_cnt,
        COALESCE(smy.smy_latest_device_days, 999) AS smy_latest_device_days,
        COALESCE(bs.bs_device_unique_cnt, 0) AS bs_device_unique_cnt,
        COALESCE(bs.bs_abnormal_cnt, 0) AS bs_abnormal_cnt,
        COALESCE(bs.bs_cross_cust_cnt, 0) AS bs_cross_cust_cnt,
        COALESCE(bs.bs_recent_30d_cnt, 0) AS bs_recent_30d_cnt,
        CASE WHEN COALESCE(smy.smy_high_risk_cnt, 0) > 0 OR COALESCE(bs.bs_abnormal_cnt, 0) > 0 THEN 1 ELSE 0 END AS device_risk_flag,
        CASE WHEN COALESCE(smy.smy_device_unique_cnt, 0) > 5 AND COALESCE(bs.bs_recent_30d_cnt, 0) > 3 THEN 1 ELSE 0 END AS device_unstable_flag
    FROM d_dq.dfs_dz_fqz_base_final s
    LEFT JOIN smy_agg smy ON s.rsk_log_id = smy.rsk_log_id
    LEFT JOIN bs_agg bs ON s.rsk_log_id = bs.rsk_log_id
    WHERE s.dt >= '20260101' AND s.create_datetime IS NOT NULL
    GROUP BY 
        s.cust_no, s.order_no, s.trans_seqno, s.rsk_log_id, s.create_datetime,
        s.risk_decision_result, s.fpd_k30, s.if_out_30d, s.if_out_60d,
        s.if_in_30d, s.if_in_60d, s.new_old,
        smy.smy_device_unique_cnt, smy.smy_mobile_cnt, smy.smy_high_risk_cnt, 
        smy.smy_login_cnt, smy.smy_latest_device_days,
        bs.bs_device_unique_cnt, bs.bs_abnormal_cnt, bs.bs_cross_cust_cnt, bs.bs_recent_30d_cnt
);
