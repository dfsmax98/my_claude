DROP TABLE IF EXISTS d_dq.dfs_contact_risk_schema_based_preloan FORCE;

CREATE TABLE d_dq.dfs_contact_risk_schema_based_preloan AS
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
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_total_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN contacts.relation_type END) AS contact_unique_type_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_named_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_total_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_urgent_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_type END) AS immediate_relation_type_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_valid_phone_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_checked_real_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN immediate.relation_mobile_no END) AS immediate_checked_invalid_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_suspicious_phone_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 7 DAY) THEN contacts.relation_mobile_no END) AS contact_recent_7d_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 30 DAY) THEN contacts.relation_mobile_no END) AS contact_recent_30d_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 90 DAY) THEN contacts.relation_mobile_no END) AS contact_recent_90d_cnt, 
    COUNT(DISTINCT CASE WHEN immediate.create_datetime >= DATE_SUB(s.close_datetime, INTERVAL 30 DAY) THEN immediate.relation_mobile_no END) AS immediate_recent_30d_cnt
FROM d_dq.dfs_dq_fqz_base_final s

LEFT JOIN default.t_bd_cust_relation_info contacts
    ON s.cust_no = contacts.cust_no
    AND contacts.create_datetime < s.close_datetime
    AND contacts.dt >= '20250101'
    AND contacts.relation_mobile_no IS NOT NULL
    AND contacts.relation_mobile_no != ''    
LEFT JOIN default.t_cif_cst_cust_immediate_relation_info immediate
    ON s.cust_no = immediate.cust_no
    AND immediate.create_datetime < s.close_datetime
    AND immediate.dt >= '20250101'
    AND immediate.relation_mobile_no IS NOT NULL
WHERE s.close_datetime IS NOT NULL
GROUP BY s.cust_no, s.apply_no, s.close_datetime, s.apply_result, s.cust_group_dq, s.fpd_k30, s.if_out_30d, s.if_out_60d, s.if_in_30d, s.if_in_60d, s.f001_decision;