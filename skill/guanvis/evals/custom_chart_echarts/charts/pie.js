var cols = data[0] || [];
var names = (cols[0] || {}).data || [];
var values = (cols[1] || {}).data || [];

option = {
  tooltip: { trigger: "item" },
  legend: { bottom: 10 },
  series: [{
    type: "pie",
    radius: ["30%", "60%"],
    data: names.map(function(name, i) { return { name: name, value: values[i] }; }),
    label: { formatter: "{b}: {d}%" }
  }],
  color: config.colors
};
