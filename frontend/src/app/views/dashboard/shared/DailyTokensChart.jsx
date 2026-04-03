import { Card, Typography, Box } from "@mui/material";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K";
  return num.toLocaleString();
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <Box sx={{
      bgcolor: "background.paper",
      border: "1px solid",
      borderColor: "divider",
      borderRadius: 2,
      p: 1.5,
      boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
    }}>
      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
        {label}
      </Typography>
      {payload.map((entry, i) => (
        <Box key={i} sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
          <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: entry.color }} />
          <Typography variant="body2">
            {entry.name}: <strong>{entry.value.toLocaleString()}</strong>
          </Typography>
        </Box>
      ))}
    </Box>
  );
};

export default function DailyTokensChart({ data = [] }) {
  if (!data || data.length === 0) return null;

  return (
    <Card elevation={0} sx={{
      p: 2.5,
      borderRadius: 3,
      border: "1px solid",
      borderColor: "divider",
    }}>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Daily Token Usage
      </Typography>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="gradInput" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef5350" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#ef5350" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradOutput" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#66bb6a" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#66bb6a" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => v.slice(5)}
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={formatNumber}
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="input_tokens"
            stackId="1"
            stroke="#ef5350"
            strokeWidth={2}
            fill="url(#gradInput)"
            name="Input Tokens"
          />
          <Area
            type="monotone"
            dataKey="output_tokens"
            stackId="1"
            stroke="#66bb6a"
            strokeWidth={2}
            fill="url(#gradOutput)"
            name="Output Tokens"
          />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}
