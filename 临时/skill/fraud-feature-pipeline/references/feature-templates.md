# 特征设计模式库

## 计数类
name: f_{source}_{metric}_{window}
agg_func: count/sum/max
time_window: 1h/3h/24h/7d/30d/2y

## 比例类
name: f_{source}_{ratio}
formula: numerator / nullif(denominator, 0)

## 序列类
name: f_{source}_{pattern}_score
logic: 提取时间序列->计算模式指标->标准化

## 网络类
name: f_{source}_{graph}_centrality
logic: 构建图->计算中心性->风险加权

## 融合类
name: f_{source}_consensus_risk
logic: 多源标准化->共识度计算->加权融合

## 标签关联类 (APP tag - VERIFIED)
name: f_app_tag_{metric}
source: applist + d_dq.fqz_applist_tag_new
join: package_name = app_package
filters: confidence >= 0.9, source_1 = mainstream
logic:
  - risk_cnt: COUNT(*) WHERE risk_type != 无
  - blacktool: MAX(CASE WHEN quality_tag LIKE %黑产% THEN 1 ELSE 0 END)
  - enterprise_ratio: COUNT(app_l1=办公软件)/COUNT(*)
  - confidence_weighted: SUM(CASE WHEN confidence>=0.95 THEN 1.0 ELSE 0.5 END)
output: numeric/binary
