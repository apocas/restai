import { Card, Typography, Box, Tooltip } from "@mui/material";
import ReactEcharts from "echarts-for-react";
import { TrendingUp, TrendingDown, TrendingFlat, LocalFireDepartment, BoltOutlined } from "@mui/icons-material";

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const PETAL_COLORS = [
  "#42a5f5", "#26c6da", "#66bb6a", "#ffa726", "#ef5350", "#ab47bc", "#5c6bc0",
];

function getHeatColor(value, max) {
  if (!max || value === 0) return "rgba(66, 165, 245, 0.08)";
  const ratio = value / max;
  if (ratio < 0.25) return "rgba(66, 165, 245, 0.2)";
  if (ratio < 0.5) return "rgba(66, 165, 245, 0.4)";
  if (ratio < 0.75) return "rgba(66, 165, 245, 0.65)";
  return "rgba(66, 165, 245, 0.9)";
}

function formatCompact(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K";
  return num.toLocaleString();
}

export default function ActivityPulse({ data = [] }) {
  if (!data || data.length === 0) return null;

  // Last 7 days for the rose chart
  const last7 = data.slice(-7);
  const roseData = last7.map((d) => {
    const date = new Date(d.date + "T00:00:00");
    const dayName = DAY_NAMES[date.getDay()];
    const total = (d.input_tokens || 0) + (d.output_tokens || 0);
    return { name: dayName, value: total, date: d.date };
  });

  // 30-day heatmap data
  const heatTotals = data.map((d) => (d.input_tokens || 0) + (d.output_tokens || 0));
  const heatMax = Math.max(...heatTotals, 1);

  // Insights
  const last7Total = last7.reduce((s, d) => s + (d.input_tokens || 0) + (d.output_tokens || 0), 0);
  const prev7 = data.slice(-14, -7);
  const prev7Total = prev7.reduce((s, d) => s + (d.input_tokens || 0) + (d.output_tokens || 0), 0);
  const trendPct = prev7Total > 0 ? ((last7Total - prev7Total) / prev7Total * 100) : 0;

  const peakDay = roseData.reduce((best, d) => d.value > best.value ? d : best, roseData[0]);

  let streak = 0;
  for (let i = data.length - 1; i >= 0; i--) {
    if ((data[i].input_tokens || 0) + (data[i].output_tokens || 0) > 0) streak++;
    else break;
  }

  const roseOption = {
    tooltip: {
      trigger: "item",
      formatter: (p) => `<strong>${p.name}</strong><br/>${p.value.toLocaleString()} tokens`,
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e0e0e0",
      borderWidth: 1,
      textStyle: { color: "#333", fontSize: 12 },
    },
    series: [
      {
        type: "pie",
        roseType: "radius",
        radius: ["20%", "70%"],
        center: ["50%", "50%"],
        data: roseData.map((d, i) => ({
          ...d,
          itemStyle: {
            color: PETAL_COLORS[i % PETAL_COLORS.length],
            borderRadius: 6,
            borderColor: "#fff",
            borderWidth: 2,
          },
        })),
        label: {
          show: true,
          position: "outside",
          formatter: "{b}",
          fontSize: 10,
          color: "#999",
        },
        labelLine: {
          length: 8,
          length2: 6,
          lineStyle: { color: "#ddd" },
        },
        emphasis: {
          itemStyle: { shadowBlur: 14, shadowColor: "rgba(0,0,0,0.15)" },
          label: { fontSize: 12, fontWeight: 600 },
        },
        animationType: "scale",
        animationEasing: "elasticOut",
        animationDelay: (idx) => idx * 80,
      },
    ],
  };

  return (
    <Card elevation={0} sx={{
      p: 2.5,
      borderRadius: 3,
      border: "1px solid",
      borderColor: "divider",
      display: "flex",
      flexDirection: "column",
      height: "100%",
    }}>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 0.5 }}>
        Activity Pulse
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>
        Last 7 days
      </Typography>

      {/* Rose Chart */}
      <Box sx={{ flex: 1, minHeight: 0 }}>
        <ReactEcharts option={roseOption} style={{ height: "180px" }} />
      </Box>

      {/* 30-Day Heatmap Strip */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: "block" }}>
          30-day activity
        </Typography>
        <Box sx={{ display: "flex", gap: "3px", flexWrap: "nowrap" }}>
          {data.map((d, i) => {
            const total = heatTotals[i];
            return (
              <Tooltip key={i} title={`${d.date}: ${formatCompact(total)} tokens`} placement="top" arrow>
                <Box sx={{
                  flex: 1,
                  height: 14,
                  borderRadius: "3px",
                  bgcolor: getHeatColor(total, heatMax),
                  transition: "transform 0.15s",
                  cursor: "default",
                  "&:hover": { transform: "scaleY(1.6)" },
                }} />
              </Tooltip>
            );
          })}
        </Box>
      </Box>

      {/* Insights Row */}
      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
        <InsightPill
          icon={<BoltOutlined sx={{ fontSize: 14 }} />}
          label="Peak"
          value={peakDay.name}
          color="#ffa726"
        />
        <InsightPill
          icon={trendPct > 0 ? <TrendingUp sx={{ fontSize: 14 }} /> : trendPct < 0 ? <TrendingDown sx={{ fontSize: 14 }} /> : <TrendingFlat sx={{ fontSize: 14 }} />}
          label="Trend"
          value={`${trendPct > 0 ? "+" : ""}${trendPct.toFixed(0)}%`}
          color={trendPct > 0 ? "#66bb6a" : trendPct < 0 ? "#ef5350" : "#90a4ae"}
        />
        {streak > 1 && (
          <InsightPill
            icon={<LocalFireDepartment sx={{ fontSize: 14 }} />}
            label="Streak"
            value={`${streak}d`}
            color="#ef5350"
          />
        )}
      </Box>
    </Card>
  );
}

function InsightPill({ icon, label, value, color }) {
  return (
    <Box sx={{
      display: "flex",
      alignItems: "center",
      gap: 0.5,
      bgcolor: `${color}14`,
      border: "1px solid",
      borderColor: `${color}30`,
      borderRadius: 2,
      px: 1,
      py: 0.5,
    }}>
      <Box sx={{ color, display: "flex", alignItems: "center" }}>{icon}</Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="caption" fontWeight={700} sx={{ color }}>{value}</Typography>
    </Box>
  );
}
