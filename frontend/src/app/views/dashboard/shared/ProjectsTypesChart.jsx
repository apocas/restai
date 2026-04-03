import ReactEcharts from "echarts-for-react";

const COLORS = ["#42a5f5", "#66bb6a", "#ffa726", "#ef5350", "#ab47bc", "#26c6da"];

export default function ProjectsTypesChart({ projects = [], height = "280px" }) {
  const typeCounts = {};
  projects.forEach((p) => {
    typeCounts[p.type] = (typeCounts[p.type] || 0) + 1;
  });

  const data = Object.entries(typeCounts).map(([name, value]) => ({ name, value }));

  if (data.length === 0) return null;

  const option = {
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c} ({d}%)",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e0e0e0",
      borderWidth: 1,
      textStyle: { color: "#333", fontSize: 13 },
    },
    legend: {
      bottom: 0,
      itemGap: 16,
      icon: "circle",
      itemWidth: 10,
      textStyle: { fontSize: 12 },
    },
    color: COLORS,
    series: [
      {
        type: "pie",
        radius: ["48%", "72%"],
        center: ["50%", "45%"],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 600,
            formatter: "{b}\n{c} ({d}%)",
          },
          itemStyle: { shadowBlur: 12, shadowColor: "rgba(0,0,0,0.15)" },
        },
        data,
      },
    ],
  };

  return <ReactEcharts style={{ height }} option={option} />;
}
