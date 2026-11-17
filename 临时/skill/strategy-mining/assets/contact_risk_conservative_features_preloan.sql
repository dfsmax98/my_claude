DROP TABLE IF EXISTS d_dq.dfs_contact_risk_conservative_preloan FORCE;

CREATE TABLE d_dq.dfs_contact_risk_conservative_preloan AS
(
    WITH contacts_filtered AS (
    SELECT cust_no, contact_phone, create_time, dt
    FROM default.t_bd_cust_relation_info
    WHERE dt >= DATE_FORMAT(DATE_TRUNC('month', ADD_MONTHS(CURRENT_DATE, -12)), 'yyyy-MM-dd')
    AND contact_phone IS NOT NULL
    AND contact_phone != ''
),
immediate_filtered AS (
    SELECT cust_no, contact_phone, create_time, dt
    FROM default.t_cif_cst_cust_immediate_relation_info
    WHERE dt >= DATE_FORMAT(DATE_TRUNC('month', ADD_MONTHS(CURRENT_DATE, -12)), 'yyyy-MM-dd')
    AND contact_phone IS NOT NULL
)
    SELECT 
        
        s.cust_no, 
        s.apply_no, 
        s.close_datetime, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_total_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 7 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_recent_7d_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 30 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_recent_30d_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND immediate.create_time >= DATE_SUB(s.close_datetime, INTERVAL 365 DAY) AND immediate.create_time < s.close_datetime THEN contact_phone END) AS immediate_contact_cnt, 
        COUNT(DISTINCT CASE WHEN 1=1 AND contacts.create_time >= DATE_SUB(s.close_datetime, INTERVAL 7 DAY) AND contacts.create_time < s.close_datetime THEN contact_phone END) AS contact_add_ratio_7d_30d, 
        CASE WHEN contact_recent_7d_cnt > 2 * (contact_recent_30d_cnt / 4) AND contact_recent_7d_cnt > 5 THEN 1 ELSE 0 END AS contact_sudden_add_flag, 
        CASE WHEN contact_recent_30d_cnt > 0 THEN 1 ELSE 0 END AS contact_active_flag
    FROM d_dq.dfs_dq_fqz_base_final s
    
LEFT JOIN contacts_filtered contacts
    ON s.cust_no = contacts.cust_no
    AND contacts.create_time < s.close_datetime    
LEFT JOIN immediate_filtered immediate
    ON s.cust_no = immediate.cust_no
    AND immediate.create_time < s.close_datetime
    WHERE s.close_datetime IS NOT NULL AND s.dt >= '20260101'
    GROUP BY s.cust_no, s.apply_no, s.close_datetime
);