-- 贷中样本SQL模板
-- 必填: fpd_k30 >= 0 过滤
SELECT 
    s.cust_no,
    s.trans_seqno,
    s.order_no,
    s.rsk_log_id,
    s.risk_decision_result,
    s.create_datetime,
    s.cust_group_dz,
    s.new_old,
    s.fpd_k30,
    s.if_out_30d,
    s.if_out_60d,
    s.if_in_30d,
    s.if_in_60d,
    f.*  -- 所有特征字段
FROM d_dq.dfs_dz_fqz_base_final s
LEFT JOIN \ f ON s.trans_seqno = f.trans_seqno
WHERE s.fpd_k30 >= 0  -- 🔒 强制过滤条件
  AND s.dt BETWEEN '' AND ''
