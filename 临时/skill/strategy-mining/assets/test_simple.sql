DROP TABLE IF EXISTS d_dq.dfs_contact_test_simple FORCE;

CREATE TABLE d_dq.dfs_contact_test_simple AS
SELECT 
    s.cust_no,
    s.apply_no,
    s.close_datetime,
    COUNT(DISTINCT c.relation_mobile_no) as contact_cnt
FROM d_dq.dfs_dq_fqz_base_final s
LEFT JOIN default.t_bd_cust_relation_info c
    ON s.cust_no = c.cust_no
    AND c.create_datetime < s.close_datetime
WHERE s.close_datetime IS NOT NULL
GROUP BY s.cust_no, s.apply_no, s.close_datetime
LIMIT 100;