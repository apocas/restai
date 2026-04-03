import { Card, Typography, Box } from "@mui/material";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";

const CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20AC" };

const CustomTooltip = ({ active, payload, label, currencySymbol }) => {
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
            {entry.name}: <strong>{currencySymbol}{entry.value.toFixed(4)}</strong>
          </Typography>
        </Box>
      ))}
    </Box>
  );
};

export default function DailyCostChart({ data = [], currency = "USD" }) {
  const currencySymbol = CURRENCY_SYMBOLS[currency] || "$";

  if (!data || data.length === 0) return null;

  const hasInputCost = data.some(d => d.input_cost > 0);
  const hasOutputCost = data.some(d => d.output_cost > 0);
  const hasTotalCost = data.some(d => d.total_cost > 0);

  if (!hasInputCost && !hasOutputCost && !hasTotalCost) return null;

  const chartData = data.map(d => ({
    ...d,
    input_cost: d.input_cost || 0,
    output_cost: d.output_cost || 0,
    total_cost: d.total_cost || 0,
  }));

  return (
    <Card elevation={0} sx={{
      p: 2.5,
      borderRadius: 3,
      border: "1px solid",
      borderColor: "divider",
    }}>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Daily Cost
      </Typography>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="gradInputCost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#42a5f5" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#42a5f5" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradOutputCost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ab47bc" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#ab47bc" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradTotalCost" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffa726" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#ffa726" stopOpacity={0.02} />
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
            tickFormatter={(v) => `${currencySymbol}${v.toFixed(2)}`}
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip currencySymbol={currencySymbol} />} />
          {hasInputCost && (
            <Area
              type="monotone"
              dataKey="input_cost"
              stackId="1"
              stroke="#42a5f5"
              strokeWidth={2}
              fill="url(#gradInputCost)"
              name="Input Cost"
            />
          )}
          {hasOutputCost && (
            <Area
              type="monotone"
              dataKey="output_cost"
              stackId="1"
              stroke="#ab47bc"
              strokeWidth={2}
              fill="url(#gradOutputCost)"
              name="Output Cost"
            />
          )}
          {!hasInputCost && !hasOutputCost && hasTotalCost && (
            <Area
              type="monotone"
              dataKey="total_cost"
              stroke="#ffa726"
              strokeWidth={2}
              fill="url(#gradTotalCost)"
              name="Total Cost"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}
