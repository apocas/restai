import { Card, Typography } from "@mui/material";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function TopLLMsChart({ data = [] }) {
  if (!data || data.length === 0) {
    return null;
  }

  return (
    <Card elevation={3} sx={{ p: 2, mb: 3 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Top LLMs by Usage</Typography>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 30, left: 60, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" tickFormatter={(v) => v.toLocaleString()} />
          <YAxis type="category" dataKey="name" width={80} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(value) => value.toLocaleString()} />
          <Bar dataKey="total_tokens" fill="#5c6bc0" name="Total Tokens" />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
