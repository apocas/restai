import { useState, useEffect, useMemo } from "react";
import {
  Box, Card, Divider, Grid, Typography, styled, IconButton,
  Table, TableBody, TableCell, TableHead, TableRow,
} from "@mui/material";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import { Analytics, ChevronLeft, ChevronRight } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

const StatCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2),
  textAlign: "center",
}));

export default function ProjectAnalytics({ project }) {
  const auth = useAuth();
  const [data, setData] = useState(null);

  const now = new Date();
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);

  const monthLabel = new Date(selectedYear, selectedMonth - 1).toLocaleString("default", { month: "long", year: "numeric" });

  const handlePrev = () => {
    if (selectedMonth === 1) { setSelectedMonth(12); setSelectedYear(selectedYear - 1); }
    else setSelectedMonth(selectedMonth - 1);
  };
  const handleNext = () => {
    const cy = now.getFullYear(), cm = now.getMonth() + 1;
    if (selectedYear === cy && selectedMonth === cm) return;
    if (selectedMonth === 12) { setSelectedMonth(1); setSelectedYear(selectedYear + 1); }
    else setSelectedMonth(selectedMonth + 1);
  };

  useEffect(() => {
    if (!project.id) return;
    const params = new URLSearchParams({ year: selectedYear, month: selectedMonth });
    api.get(`/projects/${project.id}/analytics/conversations?${params}`, auth.user.token, { silent: true })
      .then(setData)
      .catch(() => setData(null));
  }, [project.id, selectedYear, selectedMonth]);

  const filledDaily = useMemo(() => {
    if (!data) return [];
    const daysInMonth = new Date(selectedYear, selectedMonth, 0).getDate();
    const map = {};
    (data.daily || []).forEach((d) => { map[d.date] = d; });
    const result = [];
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(selectedYear, selectedMonth - 1, day);
      const dateStr = date.toISOString().split("T")[0];
      result.push(map[dateStr] || { date: dateStr, conversations: 0, messages: 0 });
    }
    return result;
  }, [data, selectedYear, selectedMonth]);

  if (!data) return null;

  const s = data.summary || {};

  return (
    <Card elevation={3}>
      <FlexBox justifyContent="space-between">
        <FlexBox>
          <Analytics sx={{ ml: 2 }} />
          <H4 sx={{ p: 2 }}>Conversation Analytics</H4>
        </FlexBox>
        <FlexBox sx={{ mr: 2 }}>
          <IconButton onClick={handlePrev} size="small"><ChevronLeft /></IconButton>
          <Typography variant="subtitle1" sx={{ mx: 1, minWidth: 140, textAlign: "center" }}>{monthLabel}</Typography>
          <IconButton onClick={handleNext} size="small"><ChevronRight /></IconButton>
        </FlexBox>
      </FlexBox>
      <Divider />

      <Box sx={{ p: 2 }}>
        {/* Summary cards */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.total_conversations?.toLocaleString() || 0}</Typography>
              <Typography variant="caption" color="text.secondary">Conversations</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.total_messages?.toLocaleString() || 0}</Typography>
              <Typography variant="caption" color="text.secondary">Messages</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.avg_messages_per_conversation || 0}</Typography>
              <Typography variant="caption" color="text.secondary">Avg Msgs/Conv</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{s.avg_latency_ms > 1000 ? `${(s.avg_latency_ms / 1000).toFixed(1)}s` : `${s.avg_latency_ms || 0}ms`}</Typography>
              <Typography variant="caption" color="text.secondary">Avg Latency</Typography>
            </StatCard>
          </Grid>
        </Grid>

        {/* Daily conversations chart */}
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Daily Activity</Typography>
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={filledDaily} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(v) => v.slice(8)} />
            <YAxis />
            <Tooltip />
            <Area type="monotone" dataKey="messages" stroke="#3498db" fill="#3498db" fillOpacity={0.4} name="Messages" />
            <Area type="monotone" dataKey="conversations" stroke="#2ecc71" fill="#2ecc71" fillOpacity={0.4} name="Conversations" />
          </AreaChart>
        </ResponsiveContainer>

        {/* Hourly distribution */}
        <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Peak Hours</Typography>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data.hourly || []} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="hour" tickFormatter={(v) => `${v}h`} />
            <YAxis />
            <Tooltip labelFormatter={(v) => `${v}:00 - ${v}:59`} />
            <Bar dataKey="messages" fill="#9b59b6" name="Messages" />
          </BarChart>
        </ResponsiveContainer>

        {/* Top users */}
        {data.top_users && data.top_users.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Top Users</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>User</TableCell>
                  <TableCell align="right" sx={{ pr: 2 }}>Messages</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.top_users.map((u) => (
                  <TableRow key={u.user_id}>
                    <TableCell sx={{ pl: 2 }}>{u.username}</TableCell>
                    <TableCell align="right" sx={{ pr: 2 }}>{u.messages}</TableCell>
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
