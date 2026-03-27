import {
  Card,
  styled,
  Divider,
  Box,
  Typography,
  Grid,
  IconButton,
} from "@mui/material";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { H4 } from "app/components/Typography";
import { useMemo } from "react";
import DataUsageIcon from '@mui/icons-material/DataUsage';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

const CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20AC" };

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

const StatCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2),
  textAlign: "center",
}));

export default function ProjectTokens({ project, tokens, selectedYear, selectedMonth, setSelectedYear, setSelectedMonth }) {
  const { platformCapabilities } = usePlatformCapabilities();
  const currencySymbol = CURRENCY_SYMBOLS[platformCapabilities.currency] || "$";

  const monthLabel = new Date(selectedYear, selectedMonth - 1).toLocaleString('default', { month: 'long', year: 'numeric' });

  const handlePrev = () => {
    if (selectedMonth === 1) {
      setSelectedMonth(12);
      setSelectedYear(selectedYear - 1);
    } else {
      setSelectedMonth(selectedMonth - 1);
    }
  };

  const handleNext = () => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1;
    if (selectedYear === currentYear && selectedMonth === currentMonth) return;
    if (selectedMonth === 12) {
      setSelectedMonth(1);
      setSelectedYear(selectedYear + 1);
    } else {
      setSelectedMonth(selectedMonth + 1);
    }
  };

  const filledTokens = useMemo(() => {
    const daysInMonth = new Date(selectedYear, selectedMonth, 0).getDate();
    const tokenMap = {};
    if (tokens && tokens.length > 0) {
      tokens.forEach((item) => {
        tokenMap[item.date] = item;
      });
    }
    const result = [];
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(selectedYear, selectedMonth - 1, day);
      const dateStr = date.toISOString().split("T")[0];
      result.push(tokenMap[dateStr] || { date: dateStr, input_tokens: 0, output_tokens: 0, input_cost: 0, output_cost: 0, avg_latency_ms: 0 });
    }
    return result;
  }, [tokens, selectedYear, selectedMonth]);

  const sums = useMemo(() => {
    return filledTokens.reduce(
      (acc, item) => {
        acc.input_tokens += item.input_tokens || 0;
        acc.output_tokens += item.output_tokens || 0;
        acc.input_cost += item.input_cost || 0;
        acc.output_cost += item.output_cost || 0;
        acc.total_latency += item.avg_latency_ms || 0;
        if (item.avg_latency_ms > 0) acc.latency_days += 1;
        return acc;
      },
      { input_tokens: 0, output_tokens: 0, input_cost: 0, output_cost: 0, total_latency: 0, latency_days: 0 }
    );
  }, [filledTokens]);

  const daysWithData = filledTokens.filter(d => d.input_tokens > 0 || d.output_tokens > 0).length;
  const avgDailyTokens = daysWithData > 0 ? Math.round((sums.input_tokens + sums.output_tokens) / daysWithData) : 0;
  const avgDailyCost = daysWithData > 0 ? (sums.input_cost + sums.output_cost) / daysWithData : 0;
  const avgLatency = sums.latency_days > 0 ? Math.round(sums.total_latency / sums.latency_days) : 0;

  return (
    <Card elevation={3}>
      <FlexBox justifyContent="space-between">
        <FlexBox>
          <DataUsageIcon sx={{ ml: 2 }} />
          <H4 sx={{ p: 2 }}>Usage</H4>
        </FlexBox>
        <FlexBox sx={{ mr: 2 }}>
          <IconButton onClick={handlePrev} size="small"><ChevronLeftIcon /></IconButton>
          <Typography variant="subtitle1" sx={{ mx: 1, minWidth: 140, textAlign: 'center' }}>{monthLabel}</Typography>
          <IconButton onClick={handleNext} size="small"><ChevronRightIcon /></IconButton>
        </FlexBox>
      </FlexBox>
      <Divider />

      <Box sx={{ p: 2 }}>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{(sums.input_tokens + sums.output_tokens).toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary">Total Tokens</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{currencySymbol}{(sums.input_cost + sums.output_cost).toFixed(3)}</Typography>
              <Typography variant="caption" color="text.secondary">Total Cost</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{avgDailyTokens.toLocaleString()}</Typography>
              <Typography variant="caption" color="text.secondary">Avg Daily Tokens</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{currencySymbol}{avgDailyCost.toFixed(3)}</Typography>
              <Typography variant="caption" color="text.secondary">Avg Daily Cost</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={6} sm={3}>
            <StatCard elevation={1}>
              <Typography variant="h6">{avgLatency > 1000 ? `${(avgLatency / 1000).toFixed(1)}s` : `${avgLatency}ms`}</Typography>
              <Typography variant="caption" color="text.secondary">Avg Latency</Typography>
            </StatCard>
          </Grid>
        </Grid>

        <Typography variant="subtitle2" sx={{ mb: 1 }}>Tokens</Typography>
        <ResponsiveContainer width='100%' height={250}>
          <AreaChart data={filledTokens} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(v) => v.slice(8)} />
            <YAxis />
            <Tooltip formatter={(value) => value.toLocaleString()} />
            <Area type="monotone" dataKey="input_tokens" stackId="1" stroke="#cd6155" fill="#cd6155" fillOpacity={0.4} name="Input Tokens" />
            <Area type="monotone" dataKey="output_tokens" stackId="1" stroke="#52be80" fill="#52be80" fillOpacity={0.4} name="Output Tokens" />
          </AreaChart>
        </ResponsiveContainer>

        <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Cost</Typography>
        <ResponsiveContainer width='100%' height={250}>
          <AreaChart data={filledTokens} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(v) => v.slice(8)} />
            <YAxis tickFormatter={(v) => `${currencySymbol}${v}`} />
            <Tooltip formatter={(value) => `${currencySymbol}${value.toFixed(4)}`} />
            <Area type="monotone" dataKey="input_cost" stackId="1" stroke="#922b21" fill="#922b21" fillOpacity={0.4} name="Input Cost" />
            <Area type="monotone" dataKey="output_cost" stackId="1" stroke="#1e8449" fill="#1e8449" fillOpacity={0.4} name="Output Cost" />
          </AreaChart>
        </ResponsiveContainer>

        <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>Latency</Typography>
        <ResponsiveContainer width='100%' height={250}>
          <AreaChart data={filledTokens} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={(v) => v.slice(8)} />
            <YAxis tickFormatter={(v) => v > 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`} />
            <Tooltip formatter={(value) => value > 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`} />
            <Area type="monotone" dataKey="avg_latency_ms" stroke="#3498db" fill="#3498db" fillOpacity={0.4} name="Avg Latency" />
          </AreaChart>
        </ResponsiveContainer>
      </Box>
    </Card>
  );
}
