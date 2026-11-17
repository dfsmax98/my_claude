var cols = data[0] || [];
var categories = (cols[0] || {}).data || [];
var values = (cols[1] || {}).data || [];

option = {
  tooltip: { trigger: "axis" },
  xAxis: { type: "category", data: categories },
  yAxis: { type: "value" },
  series: [{ type: "bar", data: values }],
  color: config.colors
};
