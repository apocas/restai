import { useTheme } from "@mui/material/styles";
import ReactEcharts from "echarts-for-react";

export default function ProjectsLLMsChart({ projects = [], height, color = [] }) {
  const theme = useTheme();

  var projectsLLMs = {};

  for (let i = 0; i < projects.length; i++) {
    projectsLLMs[projects[i].llm] = (projectsLLMs[projects[i].llm] || 0) + 1;
  }

  var data = [];
  for (let key in projectsLLMs) {
    data.push({ value: projectsLLMs[key], name: key });
  }


  const option = {
    legend: {
      show: false,
      itemGap: 20,
      icon: "circle",
      bottom: 0,
      textStyle: { color: theme.palette.text.secondary, fontSize: 11, fontFamily: "roboto" }
    },
    tooltip: { show: false, trigger: "item", formatter: "{a} <br/>{b}: {c} ({d}%)" },
    xAxis: [{ axisLine: { show: false }, splitLine: { show: false } }],
    yAxis: [{ axisLine: { show: false }, splitLine: { show: false } }],

    series: [
      {
        name: "Traffic Rate",
        type: "pie",
        radius: ["45%", "72.55%"],
        center: ["50%", "50%"],
        avoidLabelOverlap: false,
        hoverOffset: 5,
        stillShowZeroSum: false,
        bottom: 20,
        emphasis: {
          label: {
            show: true,
            fontSize: "14",
            fontWeight: "normal",
            formatter: "{b} \n{c} ({d}%)"
          },
          itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: "rgba(0, 0, 0, 0.5)" }
        },
        label: {
          show: false,
          position: "center",
          color: theme.palette.text.secondary,
          fontSize: 13,
          fontFamily: "roboto",
          formatter: "{a}"
        },
        labelLine: { show: false },
        data: data,
      }
    ]
  };

  return <ReactEcharts style={{ height: height }} option={{ ...option, color: [...color] }} />;
}
