import { useState, useEffect, useMemo } from "react";
import {
  Box, Card, Grid, Typography, styled,
  Table, TableBody, TableCell, TableHead, TableRow,
  IconButton, Tooltip,
} from "@mui/material";
import {
  Security, ChevronLeft, ChevronRight, Block, CheckCircle,
  Warning, Percent,
} from "@mui/icons-material";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer,
} from "recharts";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Guards = security/protection. Rose reads as "shield/guard" without
// being as alarming as pure red. Distinct from cron-amber, audit-indigo,
// logs-violet, routines-emerald, proxy-cyan, classifier-purple.
const ACCENT = "#f43f5e";
const ACCENT_SOFT = "rgba(244,63,94,0.10)";

// Chart palette — distinct hues for the three series.
const CHART_COLORS = {
  checks: "#0891b2",  // cyan  — total volume
  blocks: "#ef4444",  // red   — denied
  warns:  "#f59e0b",  // amber — flagged
};

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

function TileHeader({ icon, title, subtitle, accent = ACCENT, action }) {
  return (
    <Box
      sx={{
        px: 3, pt: 2.75, pb: 2,
        display: "flex",
        alignItems: "center",
        gap: 1.75,
        borderBottom: "1px solid rgba(15,23,42,0.06)",
        flexWrap: "wrap",
      }}
    >
      <Box
        sx={{
          width: 40, height: 40,
          flexShrink: 0,
          borderRadius: 1.5,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 22 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {action}
    </Box>
  );
}

// ── Stat tile — coloured number on the left, icon on the right.
// Used for Total checks / Blocked / Block rate / Warnings.
function StatTile({ icon: Icon, value, label, color, accent }) {
  return (
    <Box
      sx={{
        position: "relative",
        p: 2,
        borderRadius: 2,
        border: `1px solid ${accent}22`,
        background: `linear-gradient(135deg, ${accent}0a, rgba(15,23,42,0.015))`,
        display: "flex",
        alignItems: "center",
        gap: 2,
        transition: "transform 0.2s ease, box-shadow 0.2s ease",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: `0 6px 16px ${accent}22`,
        },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontWeight: 700,
            fontSize: "1.6rem",
            color: color || "text.primary",
            lineHeight: 1.1,
          }}
        >
          {value}
        </Box>
        <Box
          component="span"
          sx={{
            display: "block",
            mt: 0.5,
            fontSize: "0.7rem",
            color: "text.secondary",
            letterSpacing: 0.3,
            textTransform: "uppercase",
            fontWeight: 600,
          }}
        >
          {label}
        </Box>
      </Box>
      <Box
        sx={{
          width: 38, height: 38,
          flexShrink: 0,
          borderRadius: "50%",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: color || accent,
          "& svg": { fontSize: 20 },
        }}
      >
        <Icon />
      </Box>
    </Box>
  );
}

const formatRelative = (iso) => {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

// Tooltip for the area chart — clean dark slate panel with mono labels.
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <Box
      sx={{
        backgroundColor: "#0b1220",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 1.5,
        p: 1.25,
        boxShadow: "0 8px 22px rgba(15,23,42,0.18)",
        minWidth: 140,
      }}
    >
      <Box
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.65rem",
          color: "rgba(255,255,255,0.55)",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          fontWeight: 700,
          mb: 0.75,
        }}
      >
        {label}
      </Box>
      {payload.map((entry) => (
        <Box
          key={entry.dataKey}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 0.75,
            fontFamily: FONT_MONO,
            fontSize: "0.75rem",
            color: "#cbd5e1",
            mt: 0.25,
          }}
        >
          <Box
            sx={{
              width: 8, height: 8,
              borderRadius: "50%",
              background: entry.color,
              flexShrink: 0,
            }}
          />
          <Box component="span" sx={{ flex: 1, color: "rgba(255,255,255,0.7)" }}>
            {entry.name}
          </Box>
          <Box component="span" sx={{ color: entry.color, fontWeight: 700 }}>
            {entry.value}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

export default function ProjectGuards({ project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState([]);
  const [events, setEvents] = useState([]);
  const [eventsTotal, setEventsTotal] = useState(0);

  const now = new Date();
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);

  const monthLabel = new Date(selectedYear, selectedMonth - 1)
    .toLocaleString("default", { month: "long", year: "numeric" });

  const isCurrentMonth =
    selectedYear === now.getFullYear() && selectedMonth === now.getMonth() + 1;

  const handlePrev = () => {
    if (selectedMonth === 1) { setSelectedMonth(12); setSelectedYear(selectedYear - 1); }
    else setSelectedMonth(selectedMonth - 1);
  };
  const handleNext = () => {
    if (isCurrentMonth) return;
    if (selectedMonth === 12) { setSelectedMonth(1); setSelectedYear(selectedYear + 1); }
    else setSelectedMonth(selectedMonth + 1);
  };

  useEffect(() => {
    api.get(`/projects/${project.id}/guards/summary`, auth.user.token, { silent: true })
      .then(setSummary)
      .catch(() => {});
    api.get(`/projects/${project.id}/guards/events?start=0&end=20&action=block`, auth.user.token, { silent: true })
      .then((d) => { setEvents(d.events || []); setEventsTotal(d.total || 0); })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  useEffect(() => {
    const params = new URLSearchParams({ year: selectedYear, month: selectedMonth });
    api.get(`/projects/${project.id}/guards/daily?${params}`, auth.user.token, { silent: true })
      .then((d) => setDaily(d.events || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, selectedYear, selectedMonth]);

  const filledDaily = useMemo(() => {
    const daysInMonth = new Date(selectedYear, selectedMonth, 0).getDate();
    const map = {};
    daily.forEach((d) => { map[d.date] = d; });
    const result = [];
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(selectedYear, selectedMonth - 1, day);
      const dateStr = date.toISOString().split("T")[0];
      result.push(map[dateStr] || { date: dateStr, checks: 0, blocks: 0, warns: 0 });
    }
    return result;
  }, [daily, selectedYear, selectedMonth]);

  // ── Loading / no-data
  if (!summary) {
    return (
      <TileCard elevation={0} accent={ACCENT}>
        <Box
          sx={{
            py: 8,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 1.5,
          }}
        >
          <Box
            sx={{
              width: 64, height: 64,
              borderRadius: "50%",
              background: ACCENT_SOFT,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              animation: `${pulse} 3s ease-out infinite`,
            }}
          >
            <Security sx={{ fontSize: 32, color: ACCENT }} />
          </Box>
          <Typography variant="body2" color="text.secondary">
            {t("projects.edit.knowledge.guardAnalytics.noData")}
          </Typography>
        </Box>
      </TileCard>
    );
  }

  return (
    <Grid container spacing={3}>
      {/* ── Summary + chart ─────────────────────────────────── */}
      <Grid item xs={12}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<Security />}
            title={t("projects.edit.knowledge.guardAnalytics.title")}
            subtitle="Per-month guard activity, blocks, and warning trend"
            accent={ACCENT}
            action={
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0.5,
                  px: 0.5,
                  py: 0.25,
                  borderRadius: 1.5,
                  border: "1px solid rgba(15,23,42,0.08)",
                  backgroundColor: "rgba(15,23,42,0.02)",
                }}
              >
                <Tooltip title="Previous month">
                  <IconButton
                    onClick={handlePrev}
                    size="small"
                    sx={{ color: "text.secondary", "&:hover": { color: ACCENT } }}
                  >
                    <ChevronLeft fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Typography
                  sx={{
                    mx: 1,
                    minWidth: 140,
                    textAlign: "center",
                    fontFamily: FONT_MONO,
                    fontSize: "0.78rem",
                    fontWeight: 700,
                    letterSpacing: "0.05em",
                    textTransform: "uppercase",
                    color: "text.primary",
                  }}
                >
                  {monthLabel}
                </Typography>
                <Tooltip title={isCurrentMonth ? "Already at the current month" : "Next month"}>
                  <span>
                    <IconButton
                      onClick={handleNext}
                      size="small"
                      disabled={isCurrentMonth}
                      sx={{ color: "text.secondary", "&:hover": { color: ACCENT } }}
                    >
                      <ChevronRight fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </Box>
            }
          />

          <Box sx={{ p: 3 }}>
            {/* Stat tiles */}
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={6} sm={3}>
                <StatTile
                  icon={CheckCircle}
                  value={summary.total_checks.toLocaleString()}
                  label={t("projects.edit.knowledge.guardAnalytics.totalChecks")}
                  accent={CHART_COLORS.checks}
                  color={CHART_COLORS.checks}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatTile
                  icon={Block}
                  value={summary.total_blocks.toLocaleString()}
                  label={t("projects.edit.knowledge.guardAnalytics.blocked")}
                  accent={CHART_COLORS.blocks}
                  color={CHART_COLORS.blocks}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatTile
                  icon={Percent}
                  value={`${(summary.block_rate * 100).toFixed(1)}%`}
                  label={t("projects.edit.knowledge.guardAnalytics.blockRate")}
                  accent={ACCENT}
                  color={ACCENT}
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatTile
                  icon={Warning}
                  value={summary.warn_count.toLocaleString()}
                  label={t("projects.edit.knowledge.guardAnalytics.warnings")}
                  accent={CHART_COLORS.warns}
                  color={CHART_COLORS.warns}
                />
              </Grid>
            </Grid>

            {/* Chart */}
            <Box>
              <Typography
                variant="overline"
                sx={{
                  color: "text.secondary",
                  fontWeight: 600,
                  letterSpacing: 1.5,
                  fontSize: "0.65rem",
                  mb: 1,
                  display: "block",
                }}
              >
                {t("projects.edit.knowledge.guardAnalytics.events")} · {monthLabel}
              </Typography>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={filledDaily} margin={{ top: 10, right: 16, left: -8, bottom: 0 }}>
                  <defs>
                    <linearGradient id="g-checks" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor={CHART_COLORS.checks} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={CHART_COLORS.checks} stopOpacity={0.04} />
                    </linearGradient>
                    <linearGradient id="g-blocks" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor={CHART_COLORS.blocks} stopOpacity={0.45} />
                      <stop offset="100%" stopColor={CHART_COLORS.blocks} stopOpacity={0.06} />
                    </linearGradient>
                    <linearGradient id="g-warns" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%"   stopColor={CHART_COLORS.warns} stopOpacity={0.40} />
                      <stop offset="100%" stopColor={CHART_COLORS.warns} stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="rgba(15,23,42,0.06)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v) => v.slice(8)}
                    tick={{ fontFamily: FONT_MONO, fontSize: 11, fill: "#94a3b8" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontFamily: FONT_MONO, fontSize: 11, fill: "#94a3b8" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RTooltip content={<ChartTooltip />} cursor={{ stroke: ACCENT, strokeWidth: 1, strokeDasharray: "3 3" }} />
                  <Area
                    type="monotone"
                    dataKey="checks"
                    stroke={CHART_COLORS.checks}
                    strokeWidth={2}
                    fill="url(#g-checks)"
                    name="Checks"
                  />
                  <Area
                    type="monotone"
                    dataKey="warns"
                    stroke={CHART_COLORS.warns}
                    strokeWidth={2}
                    fill="url(#g-warns)"
                    name="Warned"
                  />
                  <Area
                    type="monotone"
                    dataKey="blocks"
                    stroke={CHART_COLORS.blocks}
                    strokeWidth={2}
                    fill="url(#g-blocks)"
                    name="Blocked"
                  />
                </AreaChart>
              </ResponsiveContainer>

              {/* Legend strip */}
              <Box
                sx={{
                  display: "flex",
                  gap: 2,
                  mt: 1,
                  justifyContent: "center",
                  flexWrap: "wrap",
                }}
              >
                {[
                  { name: "Checks",  color: CHART_COLORS.checks },
                  { name: "Warned",  color: CHART_COLORS.warns },
                  { name: "Blocked", color: CHART_COLORS.blocks },
                ].map((s) => (
                  <Box
                    key={s.name}
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 0.75,
                      fontFamily: FONT_MONO,
                      fontSize: "0.7rem",
                      color: "text.secondary",
                    }}
                  >
                    <Box
                      sx={{
                        width: 10, height: 10,
                        borderRadius: 0.5,
                        background: s.color,
                      }}
                    />
                    {s.name}
                  </Box>
                ))}
              </Box>
            </Box>
          </Box>
        </TileCard>
      </Grid>

      {/* ── Recent blocked events ───────────────────────────── */}
      <Grid item xs={12}>
        <TileCard elevation={0} accent={CHART_COLORS.blocks}>
          <TileHeader
            icon={<Block />}
            title={t("projects.edit.knowledge.guardAnalytics.recentBlocked", { count: eventsTotal })}
            subtitle={`Most recent ${events.length} blocked attempts (of ${eventsTotal} total)`}
            accent={CHART_COLORS.blocks}
          />
          {events.length === 0 ? (
            <Box
              sx={{
                py: 6,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 1.25,
              }}
            >
              <Box
                sx={{
                  width: 56, height: 56,
                  borderRadius: "50%",
                  background: "rgba(16,185,129,0.10)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <CheckCircle sx={{ fontSize: 28, color: "#10b981" }} />
              </Box>
              <Typography variant="body2" color="text.secondary">
                {t("projects.edit.knowledge.guardAnalytics.noBlocked")}
              </Typography>
            </Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
                  <TableCell sx={{ pl: 3 }}>{t("projects.edit.knowledge.guardAnalytics.date")}</TableCell>
                  <TableCell>{t("projects.edit.knowledge.guardAnalytics.phase")}</TableCell>
                  <TableCell>{t("projects.edit.knowledge.guardAnalytics.guard")}</TableCell>
                  <TableCell>{t("projects.edit.knowledge.guardAnalytics.text")}</TableCell>
                  <TableCell sx={{ pr: 3 }}>{t("projects.edit.knowledge.guardAnalytics.guardResponse")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {events.map((e) => {
                  const phaseColor = e.phase === "input" ? "#0891b2" : "#a855f7";
                  return (
                    <TableRow
                      key={e.id}
                      sx={{
                        "&:hover": { backgroundColor: "rgba(239,68,68,0.04)" },
                        transition: "background-color 0.15s ease",
                      }}
                    >
                      <TableCell sx={{ pl: 3, py: 1.25, whiteSpace: "nowrap" }}>
                        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.1 }}>
                          <Box
                            component="span"
                            sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", color: "text.primary" }}
                          >
                            {e.date ? new Date(e.date).toLocaleString() : "—"}
                          </Box>
                          <Box
                            component="span"
                            sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled" }}
                          >
                            {formatRelative(e.date)}
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Box
                          sx={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 0.5,
                            px: 0.85,
                            py: 0.3,
                            borderRadius: 0.75,
                            backgroundColor: `${phaseColor}10`,
                            border: `1px solid ${phaseColor}33`,
                          }}
                        >
                          <Box
                            sx={{
                              width: 6, height: 6,
                              borderRadius: "50%",
                              background: phaseColor,
                            }}
                          />
                          <Box
                            component="span"
                            sx={{
                              fontFamily: FONT_MONO,
                              fontSize: "0.68rem",
                              fontWeight: 700,
                              color: phaseColor,
                              textTransform: "uppercase",
                              letterSpacing: "0.06em",
                            }}
                          >
                            {e.phase}
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Box
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.78rem",
                            color: "text.primary",
                            fontWeight: 600,
                          }}
                        >
                          {e.guard_project}
                        </Box>
                      </TableCell>
                      <TableCell sx={{ maxWidth: 280 }}>
                        <Tooltip title={e.text_checked || ""} placement="top-start" arrow>
                          <Box
                            component="code"
                            sx={{
                              display: "inline-block",
                              maxWidth: "100%",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              fontFamily: FONT_MONO,
                              fontSize: "0.72rem",
                              color: "text.secondary",
                              backgroundColor: "rgba(15,23,42,0.04)",
                              px: 0.75, py: 0.25,
                              borderRadius: 0.75,
                            }}
                          >
                            {e.text_checked || t("projects.edit.knowledge.guardAnalytics.loggingDisabled")}
                          </Box>
                        </Tooltip>
                      </TableCell>
                      <TableCell sx={{ pr: 3, maxWidth: 320 }}>
                        <Tooltip title={e.guard_response || ""} placement="top-start" arrow>
                          <Box
                            component="span"
                            sx={{
                              display: "inline-block",
                              maxWidth: "100%",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              fontSize: "0.78rem",
                              color: "text.secondary",
                              fontStyle: e.guard_response ? "normal" : "italic",
                            }}
                          >
                            {e.guard_response || "—"}
                          </Box>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </TileCard>
      </Grid>
    </Grid>
  );
}
