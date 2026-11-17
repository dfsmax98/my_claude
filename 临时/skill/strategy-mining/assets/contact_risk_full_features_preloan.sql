DROP TABLE IF EXISTS d_dq.dfs_contact_risk_full_20260708 FORCE;

CREATE TABLE d_dq.dfs_contact_risk_full_20260708 AS
(
    WITH contacts_filtered AS (
    SELECT cust_no, create_time
    FROM default.t_bd_cust_relation_info
    WHERE dt >= DATE_FORMAT(DATE_TRUNC('month', ADD_MONTHS(CURRENT_DATE, -12)), 'yyyy-MM-dd')
        AND contact_phone IS NOT NULL    AND contact_phone != ''
),
immediate_contacts_filtered AS (
    SELECT cust_no, create_time
    FROM default.t_cif_cst_cust_immediate_relation_info
    WHERE dt >= DATE_FORMAT(DATE_TRUNC('month', ADD_MONTHS(CURRENT_DATE, -12)), 'yyyy-MM-dd')
        AND contact_phone IS NOT NULL
)
    SELECT 
        
        s.cust_no, 
        s.apply_no, 
        s.close_datetime, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_total_cnt, 
        COUNT(DISTINCT CASE WHEN relation_type = 'family' AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_family_cnt, 
        COUNT(DISTINCT CASE WHEN relation_type = 'friend' AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_friend_cnt, 
        COUNT(DISTINCT CASE WHEN relation_type = 'colleague' AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_colleague_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND immediate_contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND immediate_contacts.create_time < s.close_datetime THEN contact_phone END) AS immediate_contact_cnt, 
        COUNT(DISTINCT CASE WHEN is_blacklist = 1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS black_contact_cnt, 
        COUNT(DISTINCT CASE WHEN is_overdue = 1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS overdue_contact_cnt, 
        COUNT(DISTINCT CASE WHEN is_complaint = 1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS complaint_contact_cnt, 
        COUNT(DISTINCT CASE WHEN is_collection = 1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS collection_contact_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 7 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_recent_7d_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 30 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_recent_30d_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 90 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_recent_90d_cnt, 
        COUNT(DISTINCT CASE WHEN LENGTH(contact_phone) = 11 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_valid_ratio, 
        CASE WHEN black_contact_cnt > 0 OR overdue_contact_cnt > 5 OR complaint_contact_cnt > 0 THEN 1 ELSE 0 END AS contact_high_risk_flag, 
        CAST(COALESCE(black_contact_cnt,0)*3 + COALESCE(overdue_contact_cnt,0)*2 + COALESCE(complaint_contact_cnt,0)*2 AS INT) AS contact_risk_score_simple
    FROM d_dq.dfs_dq_fqz_base_final s
    
LEFT JOIN contacts_filtered contacts
    ON s.cust_no = contacts.cust_no
    AND contacts.create_time < s.close_datetime    
LEFT JOIN immediate_contacts_filtered immediate_contacts
    ON s.cust_no = immediate_contacts.cust_no
    AND immediate_contacts.create_time < s.close_datetime
    WHERE s.close_datetime IS NOT NULL AND s.dt >= '20260101'
    GROUP BY s.cust_no, s.apply_no, s.close_datetime
);