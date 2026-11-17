DROP TABLE IF EXISTS d_dq.dfs_contact_test_one_agg FORCE;

CREATE TABLE d_dq.dfs_contact_test_one_agg AS
SELECT 
    s.cust_no,
    s.apply_no,
    s.close_datetime,
    COUNT(DISTINCT c.relation_mobile_no) as contact_cnt
FROM d_dq.dfs_dq_fqz_base_final s
LEFT JOIN default.t_bd_cust_relation_info c
    ON s.cust_no = c.cust_no
WHERE s.close_datetime IS NOT NULL
GROUP BY s.cust_no, s.apply_no, s.close_datetime
LIMIT 10;