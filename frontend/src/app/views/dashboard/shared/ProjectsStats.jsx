import { Card, Grid, Box, Typography } from "@mui/material";
import {
  AccountTree, People, Groups, Token, AttachMoney, Speed
} from "@mui/icons-material";

const CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20AC" };

function formatNumber(num) {
  if (num == null) return "0";
  if (num >= 1000000000) return (num / 1000000000).toFixed(1) + "B";
  if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
  if (num >= 10000) return (num / 1000).toFixed(1) + "K";
  return num.toLocaleString();
}

const statCardSx = {
  p: 2.5,
  display: "flex",
  alignItems: "center",
  gap: 2,
  borderRadius: 3,
  border: "1px solid",
  borderColor: "divider",
  transition: "box-shadow 0.2s, transform 0.2s",
  "&:hover": {
    boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
    transform: "translateY(-2px)",
  },
};

function StatCard({ icon, iconBg, value, label }) {
  return (
    <Card elevation={0} sx={statCardSx}>
      <Box
        sx={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: iconBg,
          flexShrink: 0,
        }}
      >
        {icon}
      </Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h5" fontWeight={700} lineHeight={1.2} noWrap>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary" noWrap>
          {label}
        </Typography>
      </Box>
    </Card>
  );
}

export default function ProjectsStats({ projects = [], summary = null, dailyTokens = [], currency = "USD" }) {
  const currencySymbol = CURRENCY_SYMBOLS[currency] || "$";

  const avgLatency = dailyTokens.length > 0
    ? dailyTokens.reduce((sum, d) => sum + (d.avg_latency_ms || 0), 0) / dailyTokens.filter(d => d.avg_latency_ms).length
    : null;

  const cards = [
    {
      icon: <AccountTree sx={{ color: "#fff", fontSize: 24 }} />,
      iconBg: "linear-gradient(135deg, #42a5f5 0%, #1976d2 100%)",
      value: summary ? summary.total_projects : projects.length,
      label: "Projects",
    },
    {
      icon: <People sx={{ color: "#fff", fontSize: 24 }} />,
      iconBg: "linear-gradient(135deg, #66bb6a 0%, #2e7d32 100%)",
      value: summary ? summary.total_users : "—",
      label: "Users",
    },
    {
      icon: <Groups sx={{ color: "#fff", fontSize: 24 }} />,
      iconBg: "linear-gradient(135deg, #ab47bc 0%, #7b1fa2 100%)",
      value: summary ? summary.total_teams : "—",
      label: "Teams",
    },
  ];

  if (summary) {
    cards.push({
      icon: <Token sx={{ color: "#fff", fontSize: 24 }} />,
      iconBg: "linear-gradient(135deg, #ffa726 0%, #e65100 100%)",
      value: formatNumber(summary.total_tokens || 0),
      label: "Total Tokens",
    });
    cards.push({
      icon: <AttachMoney sx={{ color: "#fff", fontSize: 24 }} />,
      iconBg: "linear-gradient(135deg, #ef5350 0%, #c62828 100%)",
      value: `${currencySymbol}${(summary.total_cost || 0).toFixed(2)}`,
      label: "Total Cost",
    });
  }

  if (avgLatency && !isNaN(avgLatency)) {
    cards.push({
      icon: <Speed sx={{ color: "#fff", fontSize: 24 }} />,
      iconBg: "linear-gradient(135deg, #26c6da 0%, #00838f 100%)",
      value: avgLatency >= 1000 ? (avgLatency / 1000).toFixed(1) + "s" : Math.round(avgLatency) + "ms",
      label: "Avg Latency",
    });
  }

  const gridSize = cards.length <= 4 ? 3 : cards.length === 5 ? 2.4 : 2;

  return (
    <Grid container spacing={2} sx={{ mb: 3 }}>
      {cards.map((card, i) => (
        <Grid item xs={12} sm={6} md={gridSize} key={i}>
          <StatCard {...card} />
        </Grid>
      ))}
    </Grid>
  );
}
