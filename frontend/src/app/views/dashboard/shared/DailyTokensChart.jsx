import { Card, Typography, Box } from "@mui/material";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20AC" };

export default function DailyTokensChart({ data = [], currency = "USD" }) {
  const currencySymbol = CURRENCY_SYMBOLS[currency] || "$";

  if (!data || data.length === 0) {
    return null;
  }

  return (
    <Card elevation={3} sx={{ p: 2, mb: 3 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Daily Token Usage (Last 30 Days)</Typography>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} />
          <YAxis />
          <Tooltip formatter={(value) => value.toLocaleString()} />
          <Area type="monotone" dataKey="input_tokens" stackId="1" stroke="#cd6155" fill="#cd6155" fillOpacity={0.4} name="Input Tokens" />
          <Area type="monotone" dataKey="output_tokens" stackId="1" stroke="#52be80" fill="#52be80" fillOpacity={0.4} name="Output Tokens" />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}
