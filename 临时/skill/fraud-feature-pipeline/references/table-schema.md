# 核心表结构

## 样本表
d_dq.dfs_dq_fqz_base_final: cust_no,apply_no,close_datetime,cust_group_dq,fpd_k30
d_dq.dfs_dz_fqz_base_final: cust_no,trans_seqno,order_no,rsk_log_id,create_datetime,cust_group_dz

## 特征宽表
dwh.gdm_risk_vars_dipa_task_wide_pcr_df: apply_no=req_flow_no
dwh.gdm_risk_vars_dipa_task_wide_rms_df: rsk_log_id=req_flow_no

## 数据源
t_bd_credit_cust_app_info: cust_no,app_name,app_category,install_time
t_bd_cust_relation_info: cust_no,relation_mobile_no,create_datetime
设备三源: smy/td/bs via cust_no+event_time

## APP标签表 (已验证)
### d_dq.fqz_applist_tag_new
表结构 (2026-07-15探查确认, 总行数: 236483):
  app_package    varchar(64)  -- 包名(主键)
  app_name       varchar(64)  -- APP显示名称
  app_l1         varchar(64)  -- 一级分类: 社交通讯/办公软件/金融理财
  app_l2         varchar(64)  -- 二级分类: 即时通讯/邮箱/支付
  risk_type      varchar(64)  -- 风险类型: 无/高危/中危
  quality_tag    varchar(64)  -- 质量标签: 无/企业员工/黑产工具
  confidence     varchar(64)  -- 置信度: 0.99/0.85
  reason         varchar(64)  -- 标注原因
  source_1       varchar(64)  -- 数据来源: mainstream/third_party

关联方式:
  - JOIN: applist.package_name = tag.app_package
  - 过滤: tag.confidence >= 0.9 AND tag.source_1 = mainstream
  - 时间: applist.install_time < sample.close_datetime

衍生特征示例:
  - 风险计数: COUNT(*) WHERE risk_type != 无
  - 黑产标志: MAX(CASE WHEN quality_tag LIKE %黑产% THEN 1 ELSE 0 END)
  - 企业占比: COUNT(app_l1=办公软件)/COUNT(*)
  - 置信度加权: SUM(CASE WHEN confidence>=0.95 THEN 1.0 WHEN confidence>=0.90 THEN 0.5 ELSE 0 END)
