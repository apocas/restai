import { useState, useEffect, useMemo } from "react";
import {
  Box, Card, Grid, Typography, IconButton, Tooltip, LinearProgress,
  CircularProgress, Table, TableBody, TableCell, TableHead, TableRow, styled,
} from "@mui/material";
import { keyframes } from "@mui/system";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, ResponsiveContainer,
} from "recharts";
import {
  ChevronLeft, ChevronRight, ArrowBack, AccountBalanceWallet, AllInclusive,
  Insights, Group, Workspaces, Bolt, Forum, Speed, Api, Paid, Hub, Edit as EditIcon,
} from "@mui/icons-material";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO, sweep, shimmer, blink } from "app/components/page/pageStyles";
import MemberBudgetDialog from "./MemberBudgetDialog";

const ACCENT = "#0891b2";
// Categorical palette — cyan-leaning, distinct hues for project/user/llm shares.
const PALETTE = [
  "#0891b2", "#0ea5e9", "#6366f1", "#8b5cf6", "#14b8a6",
  "#f59e0b", "#ef4444", "#10b981", "#ec4899", "#64748b",
];

const fadeUp = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
`;

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

const HeroCard = styled(Card)(({ theme }) => ({
  position: "relative",
  padding: theme.spacing(3.5),
  marginBottom: theme.spacing(3),
  borderRadius: 20,
  overflow: "hidden",
  color: "#fff",
  background: `
    radial-gradient(at 18% 20%, rgba(14,165,233,0.92) 0px, transparent 55%),
    radial-gradient(at 82% 12%, rgba(6,182,212,0.85) 0px, transparent 55%),
    radial-gradient(at 75% 90%, rgba(56,189,248,0.65) 0px, transparent 55%),
    linear-gradient(135deg, #06182f 0%, #0c2748 100%)
  `,
  backgroundSize: "200% 200%, 200% 200%, 200% 200%, 100% 100%",
  animation: `${shimmer} 22s ease-in-out infinite`,
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background: "linear-gradient(90deg, transparent, rgba(125,211,252,0.6), rgba(56,189,248,0.6), transparent)",
    animation: `${sweep} 6s ease-in-out infinite`,
    zIndex: 2,
  },
  "& > *": { position: "relative", zIndex: 1 },
}));

const sectionCardSx = {
  position: "relative",
  borderRadius: 2,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#fff",
  overflow: "hidden",
  boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background: `linear-gradient(90deg, transparent, ${ACCENT}, transparent)`,
    transform: "translateX(-100%)",
    animation: `${sweep} 7s linear infinite`,
    opacity: 0.5,
    zIndex: 2,
  },
};

const heroIconBtnSx = {
  color: "rgba(255,255,255,0.85)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 1.5,
  background: "rgba(255,255,255,0.06)",
  backdropFilter: "blur(12px)",
  "&:hover": { color: "#fff", background: "rgba(255,255,255,0.14)" },
};

// ---- formatters -----------------------------------------------------------
const fmtNum = (n) => {
  n = Number(n || 0);
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(Math.round(n));
};
const fmtCost = (n) => {
  n = Number(n || 0);
  if (n === 0) return "$0.00";
  if (n < 0.01) return "$" + n.toFixed(4);
  return "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};
const fmtLatency = (ms) => (ms > 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms || 0)}ms`);

// ---- small components ------------------------------------------------------
function SectionCard({ icon: Icon, title, subtitle, children, action }) {
  return (
    <Card variant="outlined" sx={sectionCardSx}>
      <Box sx={{ px: 2.5, pt: 2, pb: 1.5, display: "flex", alignItems: "center", gap: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
        {Icon && <Icon sx={{ fontSize: 16, color: ACCENT, flexShrink: 0 }} />}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.74rem", letterSpacing: "0.16em", textTransform: "uppercase", fontWeight: 800, color: "#0f172a" }}>
            {title}
          </Typography>
          {subtitle && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.3 }}>{subtitle}</Typography>}
        </Box>
        {action}
      </Box>
      <Box sx={{ p: 2.5 }}>{children}</Box>
    </Card>
  );
}

function StatCard({ icon: Icon, label, value, sub, accent = ACCENT, index = 0 }) {
  return (
    <Card
      variant="outlined"
      sx={{
        p: 2, height: "100%", borderRadius: 2,
        border: "1px solid rgba(15,23,42,0.08)",
        position: "relative", overflow: "hidden",
        animation: `${fadeUp} 0.4s ease both`,
        animationDelay: `${index * 45}ms`,
        "&::before": {
          content: '""', position: "absolute", left: 0, top: 0, bottom: 0, width: 3,
          background: accent, opacity: 0.85,
        },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.75 }}>
        {Icon && <Icon sx={{ fontSize: 15, color: accent }} />}
        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "text.secondary", fontWeight: 700 }}>
          {label}
        </Typography>
      </Box>
      <Typography sx={{ fontFamily: FONT_MONO, fontWeight: 800, fontSize: "1.5rem", color: "#0f172a", lineHeight: 1.1 }}>
        {value}
      </Typography>
      {sub && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.4 }}>{sub}</Typography>}
    </Card>
  );
}

// Breakdown table with an inline cost-share bar per row.
function BreakdownTable({ t, rows, labelKey, labelHeader, total, renderLabel, capHeader, renderCap }) {
  if (!rows || rows.length === 0) {
    return <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>{t("teams.analytics.noData")}</Typography>;
  }
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell sx={{ pl: 0 }}>{labelHeader}</TableCell>
          <TableCell align="right">{t("teams.analytics.messages")}</TableCell>
          <TableCell align="right">{t("teams.analytics.tokens")}</TableCell>
          <TableCell align="right" sx={{ pr: capHeader ? undefined : 0 }}>{t("teams.analytics.cost")}</TableCell>
          {capHeader && <TableCell align="right" sx={{ pr: 0 }}>{capHeader}</TableCell>}
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((r, i) => {
          const share = total > 0 ? (r.cost / total) * 100 : 0;
          return (
            <TableRow key={(r[labelKey] ?? "direct") + "_" + i}>
              <TableCell sx={{ pl: 0, maxWidth: 220 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <Box sx={{ width: 8, height: 8, borderRadius: "2px", flexShrink: 0, background: PALETTE[i % PALETTE.length] }} />
                  <Box sx={{ minWidth: 0, flex: 1 }}>
                    <Typography noWrap sx={{ fontSize: "0.82rem", fontWeight: 600 }}>{renderLabel(r)}</Typography>
                    <LinearProgress
                      variant="determinate" value={Math.min(share, 100)}
                      sx={{ mt: 0.5, height: 4, borderRadius: 2, backgroundColor: "rgba(15,23,42,0.06)",
                        "& .MuiLinearProgress-bar": { backgroundColor: PALETTE[i % PALETTE.length] } }}
                    />
                  </Box>
                </Box>
              </TableCell>
              <TableCell align="right" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>{fmtNum(r.messages)}</TableCell>
              <TableCell align="right" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>{fmtNum(r.tokens)}</TableCell>
              <TableCell align="right" sx={{ pr: capHeader ? undefined : 0, fontFamily: FONT_MONO, fontSize: "0.78rem", fontWeight: 700 }}>
                {fmtCost(r.cost)}
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>{share.toFixed(0)}%</Typography>
              </TableCell>
              {capHeader && <TableCell align="right" sx={{ pr: 0 }}>{renderCap(r)}</TableCell>}
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export default function TeamAnalytics() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const auth = useAuth();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [capTarget, setCapTarget] = useState(null);

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const monthLabel = new Date(year, month - 1).toLocaleString("default", { month: "long", year: "numeric" });
  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;

  const prevMonth = () => { if (month === 1) { setMonth(12); setYear(year - 1); } else setMonth(month - 1); };
  const nextMonth = () => { if (isCurrentMonth) return; if (month === 12) { setMonth(1); setYear(year + 1); } else setMonth(month + 1); };

  const fetchAnalytics = () => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ year, month });
    api.get(`/teams/${id}/analytics?${params}`, auth.user.token, { silent: true })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(e?.status === 403 ? "forbidden" : "error"); setLoading(false); });
  };

  useEffect(() => {
    fetchAnalytics();
    // eslint-disable-next-line
  }, [id, year, month]);

  useEffect(() => {
    if (data?.team) document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - ${data.team.name} · Analytics`;
  }, [data]);

  const filledDaily = useMemo(() => {
    if (!data) return [];
    const days = new Date(year, month, 0).getDate();
    const map = {};
    (data.daily || []).forEach((d) => { map[d.date] = d; });
    const out = [];
    for (let d = 1; d <= days; d++) {
      const ds = new Date(Date.UTC(year, month - 1, d)).toISOString().split("T")[0];
      out.push(map[ds] || { date: ds, input_tokens: 0, output_tokens: 0, tokens: 0, cost: 0, messages: 0 });
    }
    return out;
  }, [data, year, month]);

  if (loading) {
    return <Container><Box sx={{ display: "flex", justifyContent: "center", py: 10 }}><CircularProgress /></Box></Container>;
  }
  if (error || !data) {
    return (
      <Container>
        <Card variant="outlined" sx={{ ...sectionCardSx, p: 4, textAlign: "center" }}>
          <Typography color="text.secondary">
            {error === "forbidden" ? t("teams.analytics.forbidden") : t("teams.analytics.loadError")}
          </Typography>
          <Box component="span" role="link" tabIndex={0}
            onClick={() => navigate(`/team/${id}`)}
            sx={{ display: "inline-block", mt: 2, color: ACCENT, cursor: "pointer", fontWeight: 600 }}>
            {t("teams.analytics.backToTeam")}
          </Box>
        </Card>
      </Container>
    );
  }

  const s = data.summary || {};
  const b = data.budget || {};
  const totalCost = s.total_cost || 0;
  const pct = !b.unlimited && b.budget > 0 ? Math.min((b.spending_month / b.budget) * 100, 100) : 0;
  const barColor = pct > 90 ? "#ef4444" : pct > 70 ? "#f59e0b" : "#10b981";

  const monthDays = filledDaily.length;
  const xTick = (v) => v.slice(8);

  const llmPie = (data.per_llm || []).filter((l) => l.cost > 0).map((l) => ({ name: l.llm, value: l.cost }));
  const projLabel = (r) => (r.project ? r.project : t("teams.view.tx.directAccess"));

  return (
    <Container>
      {/* HERO */}
      <HeroCard elevation={0}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, flexWrap: "wrap" }}>
          <Box sx={{ minWidth: 220 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, fontFamily: FONT_MONO, fontSize: "0.62rem", letterSpacing: 3, textTransform: "uppercase" }}>
              <Box component="span" role="link" tabIndex={0} onClick={() => navigate(`/team/${id}`)}
                sx={{ color: "rgba(255,255,255,0.75)", cursor: "pointer", "&:hover": { color: "#fff", textDecoration: "underline", textUnderlineOffset: 3 } }}>
                {data.team?.name || "Team"}
              </Box>
              <Box component="span" sx={{ color: "rgba(255,255,255,0.4)" }}>/</Box>
              <Box component="span" sx={{ color: "rgba(125,211,252,0.95)" }}>{t("teams.analytics.eyebrow")}</Box>
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 700, mt: 0.5, letterSpacing: "-0.5px", display: "flex", alignItems: "center", gap: 1 }}>
              <Insights sx={{ fontSize: 28, color: "rgba(125,211,252,0.95)" }} />
              {t("teams.analytics.title")}
              <Box component="span" sx={{ width: 9, animation: `${blink} 1.1s steps(2,start) infinite`, color: "rgba(125,211,252,0.9)" }}>_</Box>
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.5, color: "rgba(255,255,255,0.78)" }}>{t("teams.analytics.subtitle")}</Typography>
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Tooltip title={t("teams.analytics.backToTeam")}>
              <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate(`/team/${id}`)}><ArrowBack fontSize="small" /></IconButton>
            </Tooltip>
            <Box sx={{ width: 8 }} />
            <IconButton size="small" sx={heroIconBtnSx} onClick={prevMonth}><ChevronLeft fontSize="small" /></IconButton>
            <Typography sx={{ mx: 1, minWidth: 150, textAlign: "center", fontFamily: FONT_MONO, fontSize: "0.82rem", fontWeight: 600 }}>{monthLabel}</Typography>
            <IconButton size="small" sx={{ ...heroIconBtnSx, opacity: isCurrentMonth ? 0.4 : 1 }} onClick={nextMonth} disabled={isCurrentMonth}><ChevronRight fontSize="small" /></IconButton>
          </Box>
        </Box>

        {/* budget gauge */}
        <Box sx={{ mt: 3, pt: 2, borderTop: "1px solid rgba(255,255,255,0.12)" }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.75, flexWrap: "wrap", gap: 1 }}>
            <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
              <AccountBalanceWallet sx={{ fontSize: 16, color: "rgba(255,255,255,0.85)" }} />
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.85)" }}>
                {t("teams.analytics.budgetUsed")} · {monthLabel}
              </Typography>
            </Box>
            {b.unlimited ? (
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, color: "rgba(255,255,255,0.9)" }}>
                <AllInclusive sx={{ fontSize: 16 }} />
                <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.82rem" }}>{fmtCost(b.spending_month)} · {t("teams.analytics.unlimited")}</Typography>
              </Box>
            ) : (
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.85rem", fontWeight: 700, color: "#fff" }}>
                {fmtCost(b.spending_month)} <Box component="span" sx={{ color: "rgba(255,255,255,0.6)" }}>/ {fmtCost(b.budget)} ({pct.toFixed(0)}%)</Box>
              </Typography>
            )}
          </Box>
          {!b.unlimited && (
            <LinearProgress variant="determinate" value={pct}
              sx={{ height: 8, borderRadius: 4, backgroundColor: "rgba(255,255,255,0.15)",
                "& .MuiLinearProgress-bar": { backgroundColor: barColor, borderRadius: 4 } }} />
          )}
        </Box>
      </HeroCard>

      {/* STAT CARDS */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { icon: Paid, label: t("teams.analytics.totalCost"), value: fmtCost(totalCost), accent: ACCENT },
          { icon: Bolt, label: t("teams.analytics.totalTokens"), value: fmtNum(s.total_tokens), sub: `${fmtNum(s.total_input_tokens)} ${t("teams.analytics.in")} · ${fmtNum(s.total_output_tokens)} ${t("teams.analytics.out")}`, accent: "#6366f1" },
          { icon: Forum, label: t("teams.analytics.messages"), value: fmtNum(s.total_messages), sub: `${fmtNum(s.total_conversations)} ${t("teams.analytics.conversations")}`, accent: "#0ea5e9" },
          { icon: Group, label: t("teams.analytics.activeUsers"), value: fmtNum(s.active_users), accent: "#14b8a6" },
          { icon: Workspaces, label: t("teams.analytics.activeProjects"), value: fmtNum(s.active_projects), accent: "#8b5cf6" },
          { icon: Api, label: t("teams.analytics.directAccessCost"), value: fmtCost(s.direct_access_cost), sub: `${fmtNum(s.direct_access_messages)} ${t("teams.analytics.messages").toLowerCase()}`, accent: "#f59e0b" },
          { icon: Speed, label: t("teams.analytics.avgLatency"), value: fmtLatency(s.avg_latency_ms), accent: "#10b981" },
        ].map((c, i) => (
          <Grid item xs={6} sm={4} md={3} lg={1.7} key={c.label}>
            <StatCard {...c} index={i} />
          </Grid>
        ))}
      </Grid>

      {/* TRENDS */}
      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <SectionCard icon={Paid} title={t("teams.analytics.costOverTime")} subtitle={monthLabel}>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={filledDaily} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={ACCENT} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={ACCENT} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" />
                <XAxis dataKey="date" tickFormatter={xTick} fontSize={11} interval={Math.ceil(monthDays / 10)} />
                <YAxis fontSize={11} tickFormatter={(v) => "$" + fmtNum(v)} width={48} />
                <RTooltip formatter={(v) => fmtCost(v)} labelFormatter={(l) => l} />
                <Area type="monotone" dataKey="cost" stroke={ACCENT} strokeWidth={2} fill="url(#costGrad)" name={t("teams.analytics.cost")} />
              </AreaChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <SectionCard icon={Bolt} title={t("teams.analytics.tokensOverTime")} subtitle={monthLabel}>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={filledDaily} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" />
                <XAxis dataKey="date" tickFormatter={xTick} fontSize={11} interval={Math.ceil(monthDays / 10)} />
                <YAxis fontSize={11} tickFormatter={fmtNum} width={48} />
                <RTooltip formatter={(v, n) => [fmtNum(v), n]} />
                <Area type="monotone" dataKey="input_tokens" stackId="1" stroke="#6366f1" fill="#6366f1" fillOpacity={0.35} name={t("teams.analytics.inputTokens")} />
                <Area type="monotone" dataKey="output_tokens" stackId="1" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.35} name={t("teams.analytics.outputTokens")} />
              </AreaChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>
      </Grid>

      {/* BY PROJECT + BY LLM */}
      <Grid container spacing={2.5} sx={{ mb: 3 }}>
        <Grid item xs={12} md={7}>
          <SectionCard icon={Workspaces} title={t("teams.analytics.byProject")} subtitle={t("teams.analytics.byProjectSub")}>
            <BreakdownTable t={t} rows={data.per_project} labelKey="project_id" labelHeader={t("teams.analytics.project")} total={totalCost} renderLabel={projLabel} />
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={5}>
          <SectionCard icon={Hub} title={t("teams.analytics.byLlm")} subtitle={t("teams.analytics.byLlmSub")}>
            {llmPie.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie data={llmPie} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={48} outerRadius={80} paddingAngle={2}>
                      {llmPie.map((e, i) => <Cell key={e.name} fill={PALETTE[i % PALETTE.length]} />)}
                    </Pie>
                    <RTooltip formatter={(v) => fmtCost(v)} />
                  </PieChart>
                </ResponsiveContainer>
                <Table size="small">
                  <TableBody>
                    {(data.per_llm || []).map((l, i) => (
                      <TableRow key={l.llm}>
                        <TableCell sx={{ pl: 0 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                            <Box sx={{ width: 8, height: 8, borderRadius: "2px", background: PALETTE[i % PALETTE.length] }} />
                            <Typography noWrap sx={{ fontSize: "0.8rem", fontWeight: 600, maxWidth: 150 }}>{l.llm}</Typography>
                          </Box>
                        </TableCell>
                        <TableCell align="right" sx={{ fontFamily: FONT_MONO, fontSize: "0.76rem" }}>{fmtNum(l.tokens)}</TableCell>
                        <TableCell align="right" sx={{ pr: 0, fontFamily: FONT_MONO, fontSize: "0.76rem", fontWeight: 700 }}>{fmtCost(l.cost)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            ) : <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>{t("teams.analytics.noData")}</Typography>}
          </SectionCard>
        </Grid>
      </Grid>

      {/* BY USER */}
      <Box sx={{ mb: 3 }}>
        <SectionCard icon={Group} title={t("teams.analytics.byUser")} subtitle={t("teams.analytics.byUserSub")}>
          <BreakdownTable t={t} rows={data.per_user} labelKey="user_id" labelHeader={t("teams.analytics.user")} total={totalCost}
            renderLabel={(r) => r.username || t("teams.analytics.unknownUser")}
            capHeader={t("teams.budget.cap")}
            renderCap={(r) => {
              const cap = r.budget;
              return (
                <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, justifyContent: "flex-end" }}>
                  <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.76rem" }}>
                    {cap != null ? fmtCost(cap) : "—"}
                  </Box>
                  {isCurrentMonth && r.user_id && (
                    <IconButton size="small" onClick={() => setCapTarget({ user_id: r.user_id, username: r.username, budget: r.budget ?? null, spending: r.cost ?? 0 })}>
                      <EditIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  )}
                </Box>
              );
            }}
          />
        </SectionCard>
      </Box>

      {/* RELIABILITY */}
      <Grid container spacing={2.5}>
        <Grid item xs={12} md={4}>
          <SectionCard icon={Forum} title={t("teams.analytics.outcomes")}>
            {(data.status_breakdown || []).length > 0 ? (
              <Table size="small">
                <TableBody>
                  {data.status_breakdown.map((row) => (
                    <TableRow key={row.status}>
                      <TableCell sx={{ pl: 0, textTransform: "capitalize" }}>{String(row.status).replace(/_/g, " ")}</TableCell>
                      <TableCell align="right" sx={{ pr: 0, fontFamily: FONT_MONO }}>{fmtNum(row.count)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: "center" }}>{t("teams.analytics.noData")}</Typography>}
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={4}>
          <SectionCard icon={Speed} title={t("teams.analytics.latency")}>
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={data.latency_buckets || []} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" />
                <XAxis dataKey="bucket" fontSize={10} />
                <YAxis fontSize={11} allowDecimals={false} width={36} />
                <RTooltip />
                <Bar dataKey="count" fill={ACCENT} radius={[3, 3, 0, 0]} name={t("teams.analytics.requests")} />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>
        <Grid item xs={12} md={4}>
          <SectionCard icon={Insights} title={t("teams.analytics.hourly")}>
            <ResponsiveContainer width="100%" height={190}>
              <BarChart data={data.hourly || []} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,23,42,0.06)" />
                <XAxis dataKey="hour" fontSize={10} tickFormatter={(v) => `${v}h`} interval={3} />
                <YAxis fontSize={11} allowDecimals={false} width={36} />
                <RTooltip labelFormatter={(v) => `${v}:00`} />
                <Bar dataKey="messages" fill="#6366f1" radius={[3, 3, 0, 0]} name={t("teams.analytics.messages")} />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        </Grid>
      </Grid>

      {capTarget && (
        <MemberBudgetDialog
          open={!!capTarget}
          onClose={() => setCapTarget(null)}
          teamId={id}
          member={capTarget}
          onSaved={() => { setCapTarget(null); fetchAnalytics(); }}
        />
      )}
    </Container>
  );
}
