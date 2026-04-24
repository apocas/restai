import { useEffect, useState, useRef } from "react";
import { Box, Typography, styled, keyframes } from "@mui/material";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";

const pulse = keyframes`
  0%   { box-shadow: 0 0 0 0 rgba(16,185,129,0.55); }
  70%  { box-shadow: 0 0 0 10px rgba(16,185,129,0); }
  100% { box-shadow: 0 0 0 0 rgba(16,185,129,0); }
`;

const shimmer = keyframes`
  0%   { background-position:   0% 50%; }
  50%  { background-position: 100% 50%; }
  100% { background-position:   0% 50%; }
`;

// Mesh gradient done with layered radial gradients — no image asset needed.
// Three blobs drift slightly via the animated `background-position` so it
// feels alive without being noisy.
// Navy / MUI-blue gradient mesh — matches the app's active "blue"
// theme (primary #1976d2). Kept punchy with cyan and sky highlights
// so it still reads as "AI platform" and not a stock-photo banner.
const HeroRoot = styled(Box)(({ theme }) => ({
  position: "relative",
  borderRadius: 20,
  overflow: "hidden",
  padding: theme.spacing(4, 4.5),
  color: "#fff",
  background: `
    radial-gradient(at 20% 20%, rgba(25,118,210,0.95) 0px, transparent 55%),
    radial-gradient(at 85% 15%, rgba(14,165,233,0.90) 0px, transparent 55%),
    radial-gradient(at 75% 85%, rgba(6,182,212,0.80) 0px, transparent 55%),
    radial-gradient(at 10% 90%, rgba(56,189,248,0.70) 0px, transparent 55%),
    linear-gradient(135deg, #0b1d3a 0%, #0f2c5a 100%)
  `,
  backgroundSize: "200% 200%, 200% 200%, 200% 200%, 200% 200%, 100% 100%",
  animation: `${shimmer} 20s ease-in-out infinite`,
  [theme.breakpoints.down("md")]: { padding: theme.spacing(3) },
  // Subtle grain on top so the gradient doesn't look like a default
  // Stripe/Linear login page — it picks up a little texture.
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
    backgroundImage:
      "radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px)",
    backgroundSize: "4px 4px",
    mixBlendMode: "overlay",
    opacity: 0.5,
  },
}));

const StatusDot = styled(Box)(() => ({
  width: 10,
  height: 10,
  borderRadius: "50%",
  background: "#10b981",
  animation: `${pulse} 2s ease-out infinite`,
  flexShrink: 0,
}));

const StatChip = styled(Box)(() => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 12px",
  borderRadius: 999,
  background: "rgba(255,255,255,0.08)",
  backdropFilter: "blur(12px)",
  border: "1px solid rgba(255,255,255,0.12)",
  fontSize: "0.78rem",
  fontWeight: 500,
  fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
  letterSpacing: "0.3px",
  whiteSpace: "nowrap",
}));

function formatCompact(num) {
  if (num == null || isNaN(num)) return "—";
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
  if (num >= 1_000) return (num / 1_000).toFixed(1) + "K";
  return Math.round(num).toLocaleString();
}

function formatLatency(ms) {
  if (ms == null || isNaN(ms) || ms === 0) return "—";
  return ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : Math.round(ms) + "ms";
}

// Greeting is time-of-day aware so admins opening the dashboard at
// 9am and at 11pm get a subtly different cue that the thing is alive.
function greeting(t) {
  const h = new Date().getHours();
  if (h < 5)  return t("dashboard.hero.greetLate");
  if (h < 12) return t("dashboard.hero.greetMorning");
  if (h < 18) return t("dashboard.hero.greetAfternoon");
  return t("dashboard.hero.greetEvening");
}

export default function AIHero({ summary, dailyTokens, modelsCount }) {
  const { t } = useTranslation();
  const auth = useAuth();

  // Derived live-ish stats
  const today = dailyTokens?.[dailyTokens.length - 1];
  const yesterday = dailyTokens?.[dailyTokens.length - 2];
  const todayTokens = today ? (today.input_tokens || 0) + (today.output_tokens || 0) : 0;
  const yesterdayTokens = yesterday
    ? (yesterday.input_tokens || 0) + (yesterday.output_tokens || 0)
    : 0;
  const avgLatency = dailyTokens?.length
    ? (dailyTokens
        .filter((d) => d.avg_latency_ms)
        .reduce((s, d) => s + (d.avg_latency_ms || 0), 0) /
        (dailyTokens.filter((d) => d.avg_latency_ms).length || 1))
    : null;

  // The tiny rolling counter is just ergonomic sugar — gives the hero
  // the feel of a live system without polling anything. It increments
  // a pretend "tokens since page load" number based on today's average.
  const [liveTicker, setLiveTicker] = useState(0);
  const startRef = useRef(Date.now());
  useEffect(() => {
    if (!todayTokens) return;
    // tokens per second = today's total / seconds elapsed so far today
    const now = new Date();
    const secondsIntoDay =
      now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
    const tps = secondsIntoDay > 0 ? todayTokens / secondsIntoDay : 0;
    if (tps <= 0) return;
    const id = setInterval(() => {
      const elapsed = (Date.now() - startRef.current) / 1000;
      setLiveTicker(Math.round(elapsed * tps));
    }, 1000);
    return () => clearInterval(id);
  }, [todayTokens]);

  const username = auth?.user?.username;

  return (
    <HeroRoot sx={{ mb: 3 }}>
      <Box sx={{ position: "relative", zIndex: 1 }}>
        <Typography
          variant="overline"
          sx={{
            color: "rgba(255,255,255,0.75)",
            letterSpacing: 3,
            fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
          }}
        >
          {t("dashboard.hero.tagline")}
        </Typography>
        <Typography
          variant="h4"
          sx={{
            mt: 0.5,
            fontWeight: 700,
            letterSpacing: "-0.5px",
            color: "#fff",
            textShadow: "0 2px 20px rgba(0,0,0,0.2)",
          }}
        >
          {greeting(t)}{username ? `, ${username}` : ""}
          <Box
            component="span"
            sx={{
              display: "inline-block",
              width: 10,
              ml: 0.5,
              animation: "blink 1.1s steps(2, start) infinite",
              "@keyframes blink": {
                "50%": { opacity: 0 },
              },
            }}
          >
            _
          </Box>
        </Typography>
        <Typography variant="body2" sx={{ mt: 1, color: "rgba(255,255,255,0.82)", maxWidth: 600 }}>
          {t("dashboard.hero.subtitle")}
        </Typography>

        {/* Live status row */}
        <Box sx={{ mt: 3, display: "flex", flexWrap: "wrap", gap: 1.25 }}>
          <StatChip>
            <StatusDot />
            <span>{t("dashboard.hero.operational")}</span>
          </StatChip>

          {modelsCount != null && (
            <StatChip>
              <Box component="span" sx={{ color: "#93c5fd" }}>◆</Box>
              <span>{t("dashboard.hero.modelsOnline", { count: modelsCount })}</span>
            </StatChip>
          )}

          {todayTokens > 0 && (
            <StatChip>
              <Box component="span" sx={{ color: "#7dd3fc" }}>⚡</Box>
              <span>
                {t("dashboard.hero.tokensToday", {
                  value: formatCompact(todayTokens + liveTicker * 0), // keep display stable; liveTicker below
                })}
              </span>
            </StatChip>
          )}

          {liveTicker > 0 && (
            <StatChip>
              <Box component="span" sx={{ color: "#6ee7b7" }}>▲</Box>
              <span>
                {t("dashboard.hero.sinceOpen", {
                  value: formatCompact(liveTicker),
                })}
              </span>
            </StatChip>
          )}

          {avgLatency > 0 && (
            <StatChip>
              <Box component="span" sx={{ color: "#67e8f9" }}>↯</Box>
              <span>{t("dashboard.hero.latency", { value: formatLatency(avgLatency) })}</span>
            </StatChip>
          )}

          {summary && (
            <StatChip>
              <Box component="span" sx={{ color: "#a5f3fc" }}>∑</Box>
              <span>
                {t("dashboard.hero.totalTokens", {
                  value: formatCompact(summary.total_tokens || 0),
                })}
              </span>
            </StatChip>
          )}

          {yesterdayTokens > 0 && (
            <StatChip>
              <Box
                component="span"
                sx={{
                  color:
                    todayTokens >= yesterdayTokens ? "#6ee7b7" : "#fca5a5",
                }}
              >
                {todayTokens >= yesterdayTokens ? "↗" : "↘"}
              </Box>
              <span>
                {t("dashboard.hero.vsYesterday", {
                  pct:
                    yesterdayTokens > 0
                      ? Math.round(
                          ((todayTokens - yesterdayTokens) / yesterdayTokens) *
                            100
                        )
                      : 0,
                })}
              </span>
            </StatChip>
          )}
        </Box>
      </Box>
    </HeroRoot>
  );
}
