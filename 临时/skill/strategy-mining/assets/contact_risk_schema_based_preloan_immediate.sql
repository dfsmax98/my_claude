DROP TABLE IF EXISTS d_dq.dfs_contact_risk_schema_based_preloan_immediate FORCE;

CREATE TABLE d_dq.dfs_contact_risk_schema_based_preloan_immediate AS
SELECT 
    s.cust_no, 
    s.apply_no, 
    s.close_datetime, 
    s.apply_result, 
    s.cust_group_dq, 
    s.fpd_k30, 
    s.if_out_30d, 
    s.if_out_60d, 
    s.if_in_30d, 
    s.if_in_60d, 
    s.f001_decision, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_total_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_urgent_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_type END) AS immediate_relation_type_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_checked_real_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_checked_invalid_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 30 DAY) THEN immediate.relation_mobile_no END) AS immediate_recent_30d_cnt
FROM d_dq.dfs_dq_fqz_base_final s
LEFT JOIN default.t_cif_cst_cust_immediate_relation_info immediate
    ON s.cust_no = immediate.cust_no
    AND immediate.create_datetime < s.close_datetime
    AND immediate.dt >= '20250101'
    AND immediate.relation_mobile_no IS NOT NULL
WHERE s.close_datetime IS NOT NULL
GROUP BY s.cust_no, s.apply_no, s.close_datetime, s.apply_result, s.cust_group_dq, s.fpd_k30, s.if_out_30d, s.if_out_60d, s.if_in_30d, s.if_in_60d, s.f001_decision;