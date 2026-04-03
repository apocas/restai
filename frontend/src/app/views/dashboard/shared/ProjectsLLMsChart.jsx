import ReactEcharts from "echarts-for-react";

const COLORS = ["#5c6bc0", "#26a69a", "#ec407a", "#ffa726", "#42a5f5", "#ab47bc", "#66bb6a", "#ef5350"];

export default function ProjectsLLMsChart({ projects = [], height = "280px" }) {
  const llmCounts = {};
  projects.forEach((p) => {
    if (p.llm) {
      llmCounts[p.llm] = (llmCounts[p.llm] || 0) + 1;
    }
  });

  const data = Object.entries(llmCounts).map(([name, value]) => ({ name, value }));

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
