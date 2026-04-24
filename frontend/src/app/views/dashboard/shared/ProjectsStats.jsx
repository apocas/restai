import { Card, Grid, Box, Typography, styled } from "@mui/material";
import {
  AccountTree, People, Groups, Token, AttachMoney, Speed,
} from "@mui/icons-material";
import { useTranslation } from "react-i18next";

const CURRENCY_SYMBOLS = { USD: "$", EUR: "€" };

function formatNumber(num) {
  if (num == null) return "0";
  if (num >= 1_000_000_000) return (num / 1_000_000_000).toFixed(1) + "B";
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
  if (num >= 10_000) return (num / 1_000).toFixed(1) + "K";
  return num.toLocaleString();
}

// Inline SVG sparkline — no chart lib, so it stays cheap to render even
// when six cards render at once. Values normalize to [0, 1] against the
// local max so every card fills the box regardless of scale.
function Sparkline({ values, accent }) {
  if (!values || values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const w = 120;
  const h = 32;
  const stepX = w / (values.length - 1);
  const points = values
    .map((v, i) => {
      const x = i * stepX;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const areaPoints = `0,${h} ${points} ${w},${h}`;
  const gradId = "spark-" + accent.replace(/[^a-z0-9]/gi, "");
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ display: "block", overflow: "visible" }}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.35" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#${gradId})`} />
      <polyline
        points={points}
        fill="none"
        stroke={accent}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const StatRoot = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ theme, accent }) => ({
  position: "relative",
  padding: theme.spacing(2.25, 2.5),
  borderRadius: 16,
  border: "1px solid",
  borderColor: theme.palette.divider,
  overflow: "hidden",
  transition: "transform 0.2s, box-shadow 0.2s, border-color 0.2s",
  // Left accent bar as a pseudo-element so it paints under everything
  // and can grow on hover without shifting layout.
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
    background: accent,
    opacity: 0.8,
    transition: "width 0.2s",
  },
  "&:hover": {
    transform: "translateY(-2px)",
    boxShadow: `0 8px 28px -10px ${accent}55`,
    borderColor: accent + "66",
    "&::before": { width: 5 },
  },
}));

function StatCard({ icon: Icon, value, label, accent, sparkline }) {
  return (
    <StatRoot elevation={0} accent={accent}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              color: "text.secondary",
              textTransform: "uppercase",
              letterSpacing: 1.2,
              fontWeight: 600,
              fontSize: "0.68rem",
              display: "block",
              mb: 0.5,
            }}
          >
            {label}
          </Typography>
          <Typography
            sx={{
              fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
              fontSize: "1.9rem",
              fontWeight: 700,
              lineHeight: 1,
              fontVariantNumeric: "tabular-nums",
              letterSpacing: "-0.5px",
              color: "text.primary",
            }}
          >
            {value}
          </Typography>
        </Box>
        <Box
          sx={{
            width: 30,
            height: 30,
            borderRadius: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: `${accent}18`,
            color: accent,
            flexShrink: 0,
          }}
        >
          <Icon sx={{ fontSize: 16 }} />
        </Box>
      </Box>

      {sparkline && sparkline.length >= 2 && (
        <Box sx={{ mt: 1.5, mx: -0.5, opacity: 0.85 }}>
          <Sparkline values={sparkline} accent={accent} />
        </Box>
      )}
    </StatRoot>
  );
}

export default function ProjectsStats({
  projects = [],
  summary = null,
  dailyTokens = [],
  currency = "USD",
}) {
  const { t } = useTranslation();
  const currencySymbol = CURRENCY_SYMBOLS[currency] || "$";

  // Build per-metric sparkline sources from dailyTokens
  const tokenSeries = dailyTokens.map((d) => (d.input_tokens || 0) + (d.output_tokens || 0));
  const costSeries = dailyTokens.map((d) => d.cost || 0);
  const latencySeries = dailyTokens
    .map((d) => d.avg_latency_ms || 0)
    .filter((v) => v > 0);

  const avgLatency =
    latencySeries.length > 0
      ? latencySeries.reduce((s, v) => s + v, 0) / latencySeries.length
      : null;

  // Blue-family palette anchored on the theme's primary #1976d2.
  // Cost keeps a red/rose accent — semantically money-coded — so it
  // still pops against the blues and is immediately readable.
  const accentPrimary  = "#1976d2"; // theme primary
  const accentBlue600  = "#2563eb";
  const accentSky      = "#0ea5e9";
  const accentIndigo   = "#1e40af";
  const accentCyan     = "#06b6d4";
  const accentRose     = "#ef4444"; // cost — money = red

  const cards = [
    {
      icon: AccountTree,
      value: summary ? summary.total_projects : projects.length,
      label: t("dashboard.stats.projects"),
      accent: accentPrimary,
    },
    {
      icon: People,
      value: summary ? summary.total_users : "—",
      label: t("dashboard.stats.users"),
      accent: accentBlue600,
    },
    {
      icon: Groups,
      value: summary ? summary.total_teams : "—",
      label: t("dashboard.stats.teams"),
      accent: accentSky,
    },
  ];

  if (summary) {
    cards.push({
      icon: Token,
      value: formatNumber(summary.total_tokens || 0),
      label: t("dashboard.stats.tokens"),
      accent: accentIndigo,
      sparkline: tokenSeries.length >= 2 ? tokenSeries : undefined,
    });
    cards.push({
      icon: AttachMoney,
      value: `${currencySymbol}${(summary.total_cost || 0).toFixed(2)}`,
      label: t("dashboard.stats.cost"),
      accent: accentRose,
      sparkline: costSeries.length >= 2 ? costSeries : undefined,
    });
  }

  if (avgLatency && !isNaN(avgLatency)) {
    cards.push({
      icon: Speed,
      value: avgLatency >= 1000 ? (avgLatency / 1000).toFixed(1) + "s" : Math.round(avgLatency) + "ms",
      label: t("dashboard.stats.avgLatency"),
      accent: accentCyan,
      sparkline: latencySeries.length >= 2 ? latencySeries : undefined,
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
