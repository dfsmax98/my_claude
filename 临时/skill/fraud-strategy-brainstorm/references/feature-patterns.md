# 特征设计模式

## 计数类
name: f_{source}_{metric}_{window}
agg_func: count/sum/max
time_window: 1h/3h/24h/7d/30d/2y

## 比例类
name: f_{source}_{ratio}
formula: numerator / nullif(denominator, 0)

## 标志类
name: f_{source}_{flag}
agg_func: max/any
output_type: binary

## 时间类
name: f_{source}_{time_metric}
agg_func: min/max/datediff
unit: days/hours
