DROP TABLE IF EXISTS d_dq.dfs_contact_risk_schema_based_inloan_contacts FORCE;

CREATE TABLE d_dq.dfs_contact_risk_schema_based_inloan_contacts AS
SELECT 
    s.cust_no, 
    s.order_no, 
    s.trans_seqno, 
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
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_total_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) THEN contacts.relation_type END) AS contact_unique_type_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_named_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_valid_phone_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 365 DAY) THEN contacts.relation_mobile_no END) AS contact_suspicious_phone_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 7 DAY) THEN contacts.relation_mobile_no END) AS contact_recent_7d_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 30 DAY) THEN contacts.relation_mobile_no END) AS contact_recent_30d_cnt, 
    COUNT(DISTINCT CASE WHEN contacts.create_datetime >= DATE_SUB(s.create_datetime, INTERVAL 90 DAY) THEN contacts.relation_mobile_no END) AS contact_recent_90d_cnt
FROM d_dq.dfs_dz_fqz_base_final s
LEFT JOIN default.t_bd_cust_relation_info contacts
    ON s.cust_no = contacts.cust_no
    AND contacts.create_datetime < s.create_datetime
    AND contacts.dt >= '20250101'
    AND contacts.relation_mobile_no IS NOT NULL
    AND contacts.relation_mobile_no != ''
WHERE s.create_datetime IS NOT NULL
GROUP BY s.cust_no, s.order_no, s.trans_seqno, s.rsk_log_id, s.create_datetime, s.risk_decision_result, s.cust_group_dz, s.new_old, s.fpd_k30, s.if_out_30d, s.if_out_60d, s.if_in_30d, s.if_in_60d;