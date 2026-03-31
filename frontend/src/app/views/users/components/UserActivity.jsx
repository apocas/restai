import { useState, useEffect } from "react";
import {
  Box, Card, Divider, Grid, Typography, styled,
  Table, TableBody, TableCell, TableHead, TableRow,
} from "@mui/material";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { Timeline } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

const StatCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2),
  textAlign: "center",
}));

const CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20AC" };

export default function UserActivity({ user }) {
  const auth = useAuth();
  const { platformCapabilities } = usePlatformCapabilities();
  const currencySymbol = CURRENCY_SYMBOLS[platformCapabilities.currency] || "$";
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!user.id) return;
    api.get(`/statistics/users/${user.id}?days=30`, auth.user.token, { silent: true })
      .then(setData)
      .catch(() => setData(null));
  }, [user.id]);

  if (!data) return null;

  const s = data.summary || {};

  return (
    <Card elevation={3}>
      <FlexBox>
        <Timeline sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>Activity (Last 30 Days)</H4>
      </FlexBox>
      <Divider />

      <Box sx={{ p: 2 }}>
        {/* Summary cards */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={6} sm={2.4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.total_requests?.toLocaleString() || 0}</Typography>
              <Typography variant="caption" color="text.secondary">Requests</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={2.4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.total_tokens?.toLocaleString() || 0}</Typography>
              <Typography variant="caption" color="text.secondary">Tokens</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={2.4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{currencySymbol}{(s.total_cost || 0).toFixed(3)}</Typography>
              <Typography variant="caption" color="text.secondary">Cost</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={2.4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.avg_latency_ms > 1000 ? `${(s.avg_latency_ms / 1000).toFixed(1)}s` : `${s.avg_latency_ms || 0}ms`}</Typography>
              <Typography variant="caption" color="text.secondary">Avg Latency</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={2.4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.total_conversations || 0}</Typography>
              <Typography variant="caption" color="text.secondary">Conversations</Typography>
            </StatCard>
          </Grid>
        </Grid>

        {/* Daily activity chart */}
        {data.daily && data.daily.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Daily Activity</Typography>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={data.daily} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={(v) => typeof v === "string" ? v.slice(5) : v} />
                <YAxis />
                <Tooltip />
                <Area type="monotone" dataKey="requests" stroke="#3498db" fill="#3498db" fillOpacity={0.4} name="Requests" />
              </AreaChart>
            </ResponsiveContainer>
          </>
        )}

        {/* Hourly distribution */}
        {data.hourly && (
          <>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Peak Hours</Typography>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={data.hourly} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="hour" tickFormatter={(v) => `${v}h`} />
                <YAxis />
                <Tooltip labelFormatter={(v) => `${v}:00 - ${v}:59`} />
                <Bar dataKey="requests" fill="#9b59b6" name="Requests" />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}

        {/* Top projects */}
        {data.top_projects && data.top_projects.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Top Projects</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>Project</TableCell>
                  <TableCell align="right">Requests</TableCell>
                  <TableCell align="right" sx={{ pr: 2 }}>Tokens</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.top_projects.map((p) => (
                  <TableRow key={p.project_id}>
                    <TableCell sx={{ pl: 2 }}>{p.project_name}</TableCell>
                    <TableCell align="right">{p.requests}</TableCell>
                    <TableCell align="right" sx={{ pr: 2 }}>{p.tokens?.toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </Box>
    </Card>
  );
}
