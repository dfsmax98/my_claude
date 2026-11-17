-- 贷前样本SQL模板
-- 必填: fpd_k30 >= 0 过滤
SELECT 
    s.cust_no,
    s.apply_no,
    s.apply_result,
    s.close_datetime,
    s.cust_group_dq,
    s.fpd_k30,
    s.if_out_30d,
    s.if_out_60d,
    s.if_in_30d,
    s.if_in_60d,
    s.f001_decision,
    f.*  -- 所有特征字段
FROM d_dq.dfs_dq_fqz_base_final s
LEFT JOIN \ f ON s.apply_no = f.apply_no
WHERE s.fpd_k30 >= 0  -- 🔒 强制过滤条件
  AND s.dt BETWEEN '' AND ''
