-- 设备特征衍生 - 贷前 (MINIMAL SAFE VERSION)
-- 执行引擎: StarRocks/Trino
-- 仅使用基础字段确保兼容性

DROP TABLE IF EXISTS d_dq.dfs_device_risk_features_preloan_20260708 FORCE;

CREATE TABLE d_dq.dfs_device_risk_features_preloan_20260708 AS
(
    WITH smy_device_agg AS (
        SELECT 
            s.apply_no,
            COUNT(DISTINCT d.device_id) AS smy_device_cnt,
            MAX(d.device_time) AS smy_latest_time
        FROM d_dq.dfs_dq_fqz_base_final s
        LEFT JOIN smy_pc.uld_dwd.dwd_risk_rms_rsk_device_log_di d
            ON s.cust_no = d.cust_no
            AND d.device_time < s.close_datetime
            AND d.dt >= DATE_FORMAT(DATE_SUB(s.close_datetime, INTERVAL 365 DAY), 'yyyy-MM-dd')
        WHERE s.dt >= '20260101' AND s.close_datetime IS NOT NULL
        GROUP BY s.apply_no
    ),
    bs_device_agg AS (
        SELECT 
            s.apply_no,
            COUNT(DISTINCT f.bang_sheng_dfp) AS bs_device_cnt,
            COUNT(DISTINCT f.cust_no) AS bs_cross_cust_cnt
        FROM d_dq.dfs_dq_fqz_base_final s
        LEFT JOIN smy_pc.uld_dwd.dwd_risk_afp_bang_sheng_fingerprint_di f
            ON s.cust_no = f.cust_no
            AND f.create_time < s.close_datetime
            AND f.dt >= DATE_FORMAT(DATE_SUB(s.close_datetime, INTERVAL 365 DAY), 'yyyy-MM-dd')
        WHERE s.dt >= '20260101' AND s.close_datetime IS NOT NULL
        GROUP BY s.apply_no
    )
    SELECT 
        s.cust_no, s.apply_no, s.apply_result, s.close_datetime,
        s.cust_group_dq, s.fpd_k30, s.if_out_30d, s.if_out_60d,
        s.if_in_30d, s.if_in_60d, s.f001_decision,
        COALESCE(smy.smy_device_cnt, 0) AS smy_device_cnt,
        COALESCE(bs.bs_device_cnt, 0) AS bs_device_cnt,
        COALESCE(bs.bs_cross_cust_cnt, 0) AS bs_cross_cust_cnt,
        CASE WHEN COALESCE(bs.bs_cross_cust_cnt, 0) > 10 THEN 1 ELSE 0 END AS device_multi_cust_flag
    FROM d_dq.dfs_dq_fqz_base_final s
    LEFT JOIN smy_device_agg smy ON s.apply_no = smy.apply_no
    LEFT JOIN bs_device_agg bs ON s.apply_no = bs.apply_no
    WHERE s.dt >= '20260101' AND s.close_datetime IS NOT NULL
    GROUP BY 
        s.cust_no, s.apply_no, s.apply_result, s.close_datetime,
        s.cust_group_dq, s.fpd_k30, s.if_out_30d, s.if_out_60d,
        s.if_in_30d, s.if_in_60d, s.f001_decision,
        smy.smy_device_cnt, smy.smy_latest_time,
        bs.bs_device_cnt, bs.bs_cross_cust_cnt
);
