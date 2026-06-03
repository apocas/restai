import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Chip, Grid, IconButton, Typography, styled,
  TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Table, TableBody, TableCell, TableHead, TableRow,
  FormControl, FormGroup, FormControlLabel, Checkbox, CircularProgress,
  Tooltip,
} from "@mui/material";
import {
  Add, Delete, Edit, Close, PlayArrow, Science, Dataset, Insights, TrendingUp,
  CheckCircle, Cancel, HourglassEmpty,
} from "@mui/icons-material";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer,
} from "recharts";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const ACCENT = "#14b8a6";
const ACCENT_SOFT = "rgba(20,184,166,0.10)";

const METRIC_COLORS = {
  answer_relevancy: "#3b82f6",  // blue   — relevance
  faithfulness:     "#10b981",  // green  — grounded
  correctness:      "#f59e0b",  // amber  — match expected
};

const STATUS_META = {
  pending:   { color: "#94a3b8", soft: "rgba(148,163,184,0.12)", icon: HourglassEmpty, label: "PENDING" },
  running:   { color: "#0891b2", soft: "rgba(8,145,178,0.12)",   icon: PlayArrow,      label: "RUNNING" },
  completed: { color: "#10b981", soft: "rgba(16,185,129,0.12)",  icon: CheckCircle,    label: "DONE" },
  failed:    { color: "#ef4444", soft: "rgba(239,68,68,0.12)",   icon: Cancel,         label: "FAILED" },
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
        px: 2.5, pt: 2, pb: 1.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid rgba(15,23,42,0.06)",
        flexWrap: "wrap",
      }}
    >
      <Box
        sx={{
          width: 36, height: 36,
          flexShrink: 0,
          borderRadius: 1.5,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
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

function StatusPill({ status }) {
  const meta = STATUS_META[status] || STATUS_META.pending;
  const isRunning = status === "running" || status === "pending";
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.65,
        px: 1, py: 0.4,
        borderRadius: 1,
        backgroundColor: meta.soft,
        border: `1px solid ${meta.color}33`,
      }}
    >
      <Box
        sx={{
          width: 7, height: 7,
          borderRadius: "50%",
          background: meta.color,
          boxShadow: `0 0 6px ${meta.color}88`,
          ...(isRunning && { animation: `${pulse} 2s ease-out infinite` }),
        }}
      />
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.68rem",
          fontWeight: 700,
          letterSpacing: "0.06em",
          color: meta.color,
        }}
      >
        {meta.label}
      </Box>
    </Box>
  );
}

function MetricScoreBar({ name, score }) {
  const color = METRIC_COLORS[name] || ACCENT;
  const pct = (score * 100).toFixed(0);
  const label = name.replace(/_/g, " ");
  return (
    <Box sx={{ minWidth: 130, mb: 0.5 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          mb: 0.25,
        }}
      >
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.62rem",
            color: "text.secondary",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            fontWeight: 600,
          }}
        >
          {label}
        </Box>
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            fontWeight: 700,
            color,
          }}
        >
          {pct}%
        </Box>
      </Box>
      <Box
        sx={{
          height: 4,
          borderRadius: 2,
          backgroundColor: "rgba(15,23,42,0.06)",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 2,
            transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
          }}
        />
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
        minWidth: 160,
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
            {(entry.value * 100).toFixed(1)}%
          </Box>
        </Box>
      ))}
    </Box>
  );
}

function EmptyState({ icon: Icon = Science, label, hint, accent = ACCENT, action }) {
  return (
    <Box
      sx={{
        py: 5,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 1.25,
      }}
    >
      <Box
        sx={{
          width: 52, height: 52,
          borderRadius: "50%",
          background: `${accent}10`,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          animation: `${pulse} 3s ease-out infinite`,
        }}
      >
        <Icon sx={{ fontSize: 26, color: accent }} />
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", maxWidth: 320 }}>
        {label}
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center" }}>
          {hint}
        </Typography>
      )}
      {action}
    </Box>
  );
}

function AccentDialog({ open, onClose, title, subtitle, accent = ACCENT, children, actions, maxWidth = "sm" }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth
      PaperProps={{ sx: { borderRadius: 3, overflow: "hidden" } }}
    >
      <Box sx={{ height: 4, background: `linear-gradient(90deg, ${accent}, ${accent}cc, ${accent})` }} />
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2 }}>
        <Box
          sx={{
            width: 36, height: 36,
            borderRadius: 1.5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `${accent}1a`,
            color: accent,
          }}
        >
          <Science fontSize="small" />
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>{title}</Typography>
          {subtitle && (
            <Typography variant="caption" color="text.secondary">{subtitle}</Typography>
          )}
        </Box>
      </DialogTitle>
      <DialogContent sx={{ pt: 2.5 }}>{children}</DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>{actions}</DialogActions>
    </Dialog>
  );
}

// ── Score-trend "console" — full-width dark band that sits above the tiles ──
function MetricDelta({ name, latest, prev }) {
  const color = METRIC_COLORS[name] || ACCENT;
  const delta = prev != null ? latest - prev : null;
  const up = delta != null && delta >= 0;
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 1.5,
        py: 0.75,
        borderBottom: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.85, minWidth: 0 }}>
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", background: color, boxShadow: `0 0 8px ${color}aa`, flexShrink: 0 }} />
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.66rem",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "rgba(255,255,255,0.65)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {name.replace(/_/g, " ")}
        </Box>
      </Box>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.6, flexShrink: 0 }}>
        <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "1rem", fontWeight: 700, color: "#fff" }}>
          {(latest * 100).toFixed(0)}
          <Box component="span" sx={{ fontSize: "0.6rem", color: "rgba(255,255,255,0.5)" }}>%</Box>
        </Box>
        {delta != null && Math.abs(delta) >= 0.005 && (
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.62rem",
              fontWeight: 700,
              color: up ? "#34d399" : "#f87171",
            }}
          >
            {up ? "▲" : "▼"}{Math.abs(delta * 100).toFixed(0)}
          </Box>
        )}
      </Box>
    </Box>
  );
}

function TrendHero({ chartData, chartMetrics, t }) {
  const latest = chartData[chartData.length - 1] || {};
  const prev = chartData[chartData.length - 2] || {};
  return (
    <Box
      sx={{
        position: "relative",
        borderRadius: "16px",
        overflow: "hidden",
        background: "linear-gradient(135deg, #0b1220 0%, #0f1b2e 50%, #0b1220 100%)",
        border: "1px solid rgba(20,184,166,0.18)",
        boxShadow: "0 14px 36px rgba(8,15,30,0.30)",
      }}
    >
      <Box sx={{ position: "absolute", inset: 0, background: "radial-gradient(120% 120% at 85% -10%, rgba(20,184,166,0.20), transparent 55%)", pointerEvents: "none" }} />
      <Box
        sx={{
          position: "absolute", inset: 0, opacity: 0.5, pointerEvents: "none",
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />
      <Box sx={{ position: "absolute", left: 0, right: 0, top: 0, height: 3, background: `linear-gradient(90deg, transparent, ${ACCENT}, #38bdf8, ${ACCENT}, transparent)` }} />
      <Box sx={{ position: "relative", display: "flex", flexDirection: { xs: "column", md: "row" }, p: { xs: 2.5, md: 0 } }}>
        <Box
          sx={{
            width: { xs: "100%", md: 252 },
            flexShrink: 0,
            p: { md: 3 },
            pr: { md: 2.5 },
            borderRight: { md: "1px solid rgba(255,255,255,0.07)" },
            mb: { xs: 2, md: 0 },
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <TrendingUp sx={{ fontSize: 18, color: ACCENT }} />
            <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", color: "#fff" }}>
              {t("projects.edit.knowledge.evals.scoreTrend")}
            </Box>
          </Box>
          <Box component="span" sx={{ display: "block", fontFamily: FONT_MONO, fontSize: "0.62rem", color: "rgba(255,255,255,0.45)", mt: 0.5, letterSpacing: "0.05em" }}>
            {chartData.length} runs · {chartMetrics.length} metric{chartMetrics.length === 1 ? "" : "s"}
          </Box>
          <Box sx={{ mt: 2 }}>
            {chartMetrics.map((m) => (
              <MetricDelta
                key={m}
                name={m}
                latest={Number(latest[m]) || 0}
                prev={prev[m] != null ? Number(prev[m]) : null}
              />
            ))}
          </Box>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0, p: { md: 2.5 } }}>
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 5" stroke="rgba(255,255,255,0.07)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontFamily: FONT_MONO, fontSize: 10, fill: "rgba(255,255,255,0.4)" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                domain={[0, 1]}
                tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                tick={{ fontFamily: FONT_MONO, fontSize: 10, fill: "rgba(255,255,255,0.4)" }}
                axisLine={false}
                tickLine={false}
              />
              <RTooltip content={<ChartTooltip />} cursor={{ stroke: ACCENT, strokeWidth: 1, strokeDasharray: "3 3" }} />
              {chartMetrics.map((m) => (
                <Line
                  key={m}
                  type="monotone"
                  dataKey={m}
                  name={m.replace(/_/g, " ")}
                  stroke={METRIC_COLORS[m] || ACCENT}
                  strokeWidth={2.5}
                  dot={{ fill: "#0b1220", stroke: METRIC_COLORS[m] || ACCENT, strokeWidth: 2, r: 3.5 }}
                  activeDot={{ r: 6 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </Box>
      </Box>
    </Box>
  );
}

// ── Run-results modal ──────────────────────────────────────────────────────
function FieldBlock({ label, value, mono }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.6rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "text.disabled", fontWeight: 700 }}>
        {label}
      </Box>
      <Box
        sx={{
          mt: 0.5,
          fontSize: "0.83rem",
          fontFamily: mono ? FONT_MONO : "inherit",
          color: "text.primary",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          backgroundColor: "rgba(15,23,42,0.03)",
          border: "1px solid rgba(15,23,42,0.06)",
          borderRadius: 1,
          p: 1.25,
          maxHeight: 220,
          overflow: "auto",
        }}
      >
        {value || "—"}
      </Box>
    </Box>
  );
}

function ResultMetricRow({ r }) {
  const mc = METRIC_COLORS[r.metric_name] || ACCENT;
  const passed = !!r.passed;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75, py: 1.25, borderTop: "1px dashed rgba(15,23,42,0.10)" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
        <Box
          component="span"
          sx={{
            px: 0.85, py: 0.3, borderRadius: 0.75,
            backgroundColor: `${mc}15`, color: mc, border: `1px solid ${mc}33`,
            fontFamily: FONT_MONO, fontSize: "0.66rem", fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.05em",
          }}
        >
          {r.metric_name.replace(/_/g, " ")}
        </Box>
        <Box
          sx={{
            display: "inline-flex", alignItems: "center", gap: 0.5,
            px: 0.85, py: 0.3, borderRadius: 0.75,
            backgroundColor: passed ? "rgba(16,185,129,0.10)" : "rgba(239,68,68,0.10)",
            border: `1px solid ${passed ? "#10b981" : "#ef4444"}33`,
          }}
        >
          {passed ? <CheckCircle sx={{ fontSize: 12, color: "#10b981" }} /> : <Cancel sx={{ fontSize: 12, color: "#ef4444" }} />}
          <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.74rem", fontWeight: 700, color: passed ? "#10b981" : "#ef4444" }}>
            {r.score != null ? `${(r.score * 100).toFixed(0)}%` : "—"}
          </Box>
        </Box>
        {r.latency_ms != null && (
          <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled" }}>
            {r.latency_ms} ms
          </Box>
        )}
      </Box>
      {r.reason && (
        <Box
          sx={{
            fontSize: "0.8rem",
            color: "text.secondary",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            backgroundColor: "rgba(15,23,42,0.03)",
            borderRadius: 1,
            p: 1,
            maxHeight: 180,
            overflow: "auto",
          }}
        >
          {r.reason}
        </Box>
      )}
    </Box>
  );
}

function RunResultsDialog({ open, onClose, run, t }) {
  const groups = useMemo(() => {
    if (!run || !run.results) return [];
    const map = new Map();
    for (const r of run.results) {
      if (!map.has(r.test_case_id)) {
        map.set(r.test_case_id, {
          test_case_id: r.test_case_id,
          question: r.question,
          expected_answer: r.expected_answer,
          actual_answer: r.actual_answer,
          metrics: [],
        });
      }
      const g = map.get(r.test_case_id);
      if (!g.question && r.question) g.question = r.question;
      if ((g.expected_answer == null || g.expected_answer === "") && r.expected_answer) g.expected_answer = r.expected_answer;
      if (!g.actual_answer && r.actual_answer) g.actual_answer = r.actual_answer;
      g.metrics.push(r);
    }
    return [...map.values()];
  }, [run]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { borderRadius: 3, overflow: "hidden" } }}>
      <Box sx={{ height: 4, background: `linear-gradient(90deg, ${ACCENT}, ${ACCENT}cc, ${ACCENT})` }} />
      <DialogTitle sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, py: 2 }}>
        <Box sx={{ width: 36, height: 36, borderRadius: 1.5, display: "inline-flex", alignItems: "center", justifyContent: "center", background: `${ACCENT}1a`, color: ACCENT, flexShrink: 0 }}>
          <Insights fontSize="small" />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              {run ? t("projects.edit.knowledge.evals.runResults", { id: run.id }) : ""}
            </Typography>
            {run && <StatusPill status={run.status} />}
          </Box>
          {run && (run.summary || run.prompt_version_id) && (
            <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mt: 0.85 }}>
              {run.summary && Object.entries(run.summary).map(([k, v]) => {
                const c = METRIC_COLORS[k] || ACCENT;
                return (
                  <Box
                    key={k}
                    component="span"
                    sx={{
                      display: "inline-flex", alignItems: "center", gap: 0.5,
                      fontFamily: FONT_MONO, fontSize: "0.66rem", fontWeight: 700,
                      px: 0.85, py: 0.3, borderRadius: 0.75,
                      backgroundColor: `${c}12`, color: c, border: `1px solid ${c}30`,
                    }}
                  >
                    <Box sx={{ width: 7, height: 7, borderRadius: "50%", background: c }} />
                    {k.replace(/_/g, " ")} {(v * 100).toFixed(0)}%
                  </Box>
                );
              })}
              {run.prompt_version_id && (
                <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.66rem", fontWeight: 700, px: 0.85, py: 0.3, borderRadius: 0.75, backgroundColor: ACCENT_SOFT, color: ACCENT }}>
                  v{run.prompt_version ?? run.prompt_version_id}
                </Box>
              )}
            </Box>
          )}
        </Box>
        <IconButton onClick={onClose} size="small" sx={{ color: "text.disabled" }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ backgroundColor: "rgba(15,23,42,0.015)" }}>
        {!run ? (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <CircularProgress size={28} sx={{ color: ACCENT }} />
          </Box>
        ) : run.error ? (
          <Box
            sx={{
              p: 1.5, borderRadius: 1.5,
              backgroundColor: "rgba(239,68,68,0.06)", border: "1px solid rgba(239,68,68,0.25)",
              fontFamily: FONT_MONO, fontSize: "0.8rem", color: "#9f3a38",
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}
          >
            {run.error}
          </Box>
        ) : groups.length === 0 ? (
          <Box sx={{ py: 5, textAlign: "center" }}>
            <HourglassEmpty sx={{ fontSize: 30, mb: 1, color: "text.disabled" }} />
            <Typography variant="body2" color="text.secondary">
              {t("projects.edit.knowledge.evals.noResultsYet")}
            </Typography>
          </Box>
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, py: 1 }}>
            {groups.map((g, i) => {
              const hasExpected = g.expected_answer != null && g.expected_answer !== "";
              return (
                <Box key={g.test_case_id} sx={{ borderRadius: 2, border: "1px solid rgba(15,23,42,0.08)", backgroundColor: "#fff", overflow: "hidden" }}>
                  <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid rgba(15,23,42,0.06)", display: "flex", alignItems: "center", gap: 1 }}>
                    <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.66rem", fontWeight: 700, color: ACCENT, backgroundColor: ACCENT_SOFT, px: 0.85, py: 0.3, borderRadius: 0.75, flexShrink: 0 }}>
                      #{i + 1}
                    </Box>
                    <Box component="span" sx={{ fontWeight: 600, fontSize: "0.9rem", color: "text.primary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {g.question || "—"}
                    </Box>
                  </Box>
                  <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 1.5 }}>
                    <FieldBlock label={t("projects.edit.knowledge.evals.question")} value={g.question} />
                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: hasExpected ? "1fr 1fr" : "1fr" }, gap: 1.5 }}>
                      {hasExpected && (
                        <FieldBlock label={t("projects.edit.knowledge.evals.expectedAnswer")} value={g.expected_answer} mono />
                      )}
                      <FieldBlock label={t("projects.edit.knowledge.evals.answer")} value={g.actual_answer} />
                    </Box>
                    <Box>
                      {g.metrics.map((r) => <ResultMetricRow key={r.id} r={r} />)}
                    </Box>
                  </Box>
                </Box>
              );
            })}
          </Box>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onClose} sx={{ textTransform: "none", color: "text.secondary" }}>
          {t("common.close")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function ProjectEvals({ project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [datasets, setDatasets] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [caseModalOpen, setCaseModalOpen] = useState(false);
  const [caseEditId, setCaseEditId] = useState(null);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [newDataset, setNewDataset] = useState({ name: "", description: "" });
  const [newCase, setNewCase] = useState({ question: "", expected_answer: "" });
  const [runMetrics, setRunMetrics] = useState(["answer_relevancy"]);
  const [runDatasetId, setRunDatasetId] = useState(null);
  const [loading, setLoading] = useState(false);

  const isRag = project.type === "rag";

  const fetchDatasets = () => {
    api.get(`/projects/${project.id}/evals/datasets`, auth.user.token)
      .then(setDatasets)
      .catch(() => {});
  };
  const fetchRuns = () => {
    api.get(`/projects/${project.id}/evals/runs`, auth.user.token)
      .then(setRuns)
      .catch(() => {});
  };
  const fetchDatasetDetail = (id) => {
    api.get(`/projects/${project.id}/evals/datasets/${id}`, auth.user.token)
      .then(setSelectedDataset)
      .catch(() => {});
  };
  const fetchRunDetail = (id) => {
    api.get(`/projects/${project.id}/evals/runs/${id}`, auth.user.token)
      .then(setSelectedRun)
      .catch(() => {});
  };

  useEffect(() => {
    fetchDatasets();
    fetchRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  useEffect(() => {
    const running = runs.some((r) => r.status === "running" || r.status === "pending");
    if (!running) return;
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);

  const handleCreateDataset = () => {
    api.post(`/projects/${project.id}/evals/datasets`, newDataset, auth.user.token)
      .then((created) => {
        setCreateOpen(false);
        setNewDataset({ name: "", description: "" });
        fetchDatasets();
        if (created && created.id) fetchDatasetDetail(created.id);
      })
      .catch(() => {});
  };

  const handleDeleteDataset = (id) => {
    if (!window.confirm(t("projects.edit.knowledge.evals.confirmDeleteDataset"))) return;
    api.delete(`/projects/${project.id}/evals/datasets/${id}`, auth.user.token)
      .then(() => {
        fetchDatasets();
        if (selectedDataset?.id === id) setSelectedDataset(null);
      })
      .catch(() => {});
  };

  const openAddCase = () => {
    setNewCase({ question: "", expected_answer: "" });
    setCaseEditId(null);
    setCaseModalOpen(true);
  };

  const openEditCase = (tc) => {
    setNewCase({ question: tc.question || "", expected_answer: tc.expected_answer || "" });
    setCaseEditId(tc.id);
    setCaseModalOpen(true);
  };

  const handleSaveCase = () => {
    if (!selectedDataset) return;
    const base = `/projects/${project.id}/evals/datasets/${selectedDataset.id}/cases`;
    const req = caseEditId != null
      ? api.patch(`${base}/${caseEditId}`, newCase, auth.user.token)
      : api.post(base, newCase, auth.user.token);
    req
      .then(() => {
        setCaseModalOpen(false);
        setCaseEditId(null);
        setNewCase({ question: "", expected_answer: "" });
        fetchDatasetDetail(selectedDataset.id);
      })
      .catch(() => {});
  };

  const handleDeleteCase = (caseId) => {
    api.delete(`/projects/${project.id}/evals/datasets/${selectedDataset.id}/cases/${caseId}`, auth.user.token)
      .then(() => fetchDatasetDetail(selectedDataset.id))
      .catch(() => {});
  };

  const handleStartRun = () => {
    setLoading(true);
    api.post(`/projects/${project.id}/evals/runs`, { dataset_id: runDatasetId, metrics: runMetrics }, auth.user.token)
      .then(() => { setRunOpen(false); fetchRuns(); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const handleDeleteRun = (id) => {
    if (!window.confirm(t("projects.edit.knowledge.evals.confirmDeleteRun"))) return;
    api.delete(`/projects/${project.id}/evals/runs/${id}`, auth.user.token)
      .then(() => {
        fetchRuns();
        if (selectedRun?.id === id) { setSelectedRun(null); setResultsOpen(false); }
      })
      .catch(() => {});
  };

  const openRunResults = (id) => {
    if (!selectedRun || selectedRun.id !== id) setSelectedRun(null);
    fetchRunDetail(id);
    setResultsOpen(true);
  };

  const toggleMetric = (metric) => {
    setRunMetrics((prev) => prev.includes(metric) ? prev.filter((m) => m !== metric) : [...prev, metric]);
  };

  const metricOptions = [
    { key: "answer_relevancy", label: t("projects.edit.knowledge.evals.answerRelevancy") },
    ...(isRag ? [{ key: "faithfulness", label: t("projects.edit.knowledge.evals.faithfulness") }] : []),
    { key: "correctness", label: t("projects.edit.knowledge.evals.correctness") },
  ];

  const { chartData, chartMetrics } = useMemo(() => {
    const completed = runs.filter((r) => r.status === "completed" && r.summary).slice().reverse();
    const data = completed.map((r) => ({
      date: r.completed_at ? new Date(r.completed_at).toLocaleDateString() : `#${r.id}`,
      ...r.summary,
    }));
    const metrics = [...new Set(runs.flatMap((r) => r.summary ? Object.keys(r.summary) : []))];
    return { chartData: data, chartMetrics: metrics };
  }, [runs]);

  const runningCount = runs.filter((r) => r.status === "running" || r.status === "pending").length;

  return (
    <Grid container spacing={3}>
      {chartData.length > 1 && (
        <Grid item xs={12}>
          <TrendHero chartData={chartData} chartMetrics={chartMetrics} t={t} />
        </Grid>
      )}

      <Grid item xs={12} md={6}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<Dataset />}
            title={t("projects.edit.knowledge.evals.datasets")}
            subtitle={`${datasets.length} dataset${datasets.length === 1 ? "" : "s"}`}
            accent={ACCENT}
            action={
              <Button
                size="small"
                variant="contained"
                startIcon={<Add />}
                onClick={() => setCreateOpen(true)}
                sx={{
                  textTransform: "none",
                  fontWeight: 600,
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #0d9488 100%)`,
                  boxShadow: `0 4px 14px ${ACCENT}55`,
                  "&:hover": {
                    background: `linear-gradient(135deg, ${ACCENT} 0%, #0f766e 100%)`,
                    boxShadow: `0 6px 18px ${ACCENT}77`,
                  },
                }}
              >
                {t("projects.edit.knowledge.evals.newDataset")}
              </Button>
            }
          />
          {datasets.length === 0 ? (
            <EmptyState
              icon={Dataset}
              label={t("projects.edit.knowledge.evals.noDatasets")}
              accent={ACCENT}
            />
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
                  <TableCell sx={{ pl: 3 }}>{t("projects.edit.knowledge.evals.name")}</TableCell>
                  <TableCell align="center">{t("projects.edit.knowledge.evals.cases")}</TableCell>
                  <TableCell align="right" sx={{ pr: 3 }}>{t("projects.edit.knowledge.evals.actions")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {datasets.map((d) => {
                  const isSel = selectedDataset?.id === d.id;
                  return (
                    <TableRow
                      key={d.id}
                      onClick={() => fetchDatasetDetail(d.id)}
                      sx={{
                        cursor: "pointer",
                        backgroundColor: isSel ? `${ACCENT}08` : undefined,
                        borderLeft: isSel ? `2px solid ${ACCENT}` : "2px solid transparent",
                        transition: "background-color 0.15s ease",
                        "&:hover": { backgroundColor: isSel ? `${ACCENT}10` : "rgba(15,23,42,0.025)" },
                      }}
                    >
                      <TableCell sx={{ pl: 3, py: 1.25 }}>
                        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.1 }}>
                          <Box component="span" sx={{ fontWeight: 600, fontSize: "0.85rem" }}>{d.name}</Box>
                          {d.description && (
                            <Box component="span" sx={{ fontSize: "0.72rem", color: "text.disabled" }}>
                              {d.description.length > 60 ? d.description.slice(0, 60) + "…" : d.description}
                            </Box>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell align="center">
                        <Box
                          component="span"
                          sx={{
                            display: "inline-block",
                            px: 0.85, py: 0.25,
                            borderRadius: 0.75,
                            background: ACCENT_SOFT,
                            color: ACCENT,
                            fontFamily: FONT_MONO,
                            fontWeight: 700,
                            fontSize: "0.72rem",
                            minWidth: 28,
                          }}
                        >
                          {d.test_case_count}
                        </Box>
                      </TableCell>
                      <TableCell align="right" sx={{ pr: 3 }}>
                        <Tooltip title="Run evaluation">
                          <IconButton
                            size="small"
                            onClick={(e) => { e.stopPropagation(); setRunDatasetId(d.id); setRunOpen(true); }}
                            sx={{ color: ACCENT, "&:hover": { backgroundColor: `${ACCENT}10` } }}
                          >
                            <PlayArrow fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete dataset">
                          <IconButton
                            size="small"
                            onClick={(e) => { e.stopPropagation(); handleDeleteDataset(d.id); }}
                            sx={{ color: "text.disabled", "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.06)" } }}
                          >
                            <Delete fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </TileCard>

        {selectedDataset && (
          <Box sx={{ mt: 3 }}>
            <TileCard elevation={0} accent={ACCENT}>
              <TileHeader
                icon={<Science />}
                title={t("projects.edit.knowledge.evals.testCases", { name: selectedDataset.name })}
                subtitle={`${(selectedDataset.test_cases || []).length} case${(selectedDataset.test_cases || []).length === 1 ? "" : "s"}`}
                accent={ACCENT}
                action={
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<Add />}
                    onClick={openAddCase}
                    sx={{
                      textTransform: "none",
                      color: ACCENT,
                      borderColor: `${ACCENT}55`,
                      "&:hover": { borderColor: ACCENT, backgroundColor: `${ACCENT}0c` },
                    }}
                  >
                    {t("projects.edit.knowledge.evals.addCase")}
                  </Button>
                }
              />
              {(!selectedDataset.test_cases || selectedDataset.test_cases.length === 0) ? (
                <EmptyState
                  icon={Science}
                  label={t("projects.edit.knowledge.evals.noCases")}
                  accent={ACCENT}
                  action={
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<Add />}
                      onClick={openAddCase}
                      sx={{
                        mt: 1,
                        textTransform: "none",
                        color: ACCENT,
                        borderColor: `${ACCENT}55`,
                        "&:hover": { borderColor: ACCENT, backgroundColor: `${ACCENT}0c` },
                      }}
                    >
                      {t("projects.edit.knowledge.evals.addFirstCase")}
                    </Button>
                  }
                />
              ) : (
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
                      <TableCell sx={{ pl: 3 }}>{t("projects.edit.knowledge.evals.question")}</TableCell>
                      <TableCell>{t("projects.edit.knowledge.evals.expectedAnswer")}</TableCell>
                      <TableCell align="right" sx={{ pr: 3 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {selectedDataset.test_cases.map((tc) => (
                      <TableRow
                        key={tc.id}
                        sx={{
                          "&:hover": { backgroundColor: "rgba(15,23,42,0.025)" },
                          transition: "background-color 0.15s ease",
                        }}
                      >
                        <TableCell sx={{ pl: 3, maxWidth: 280 }}>
                          <Tooltip title={tc.question} placement="top-start" arrow>
                            <Box
                              sx={{
                                fontSize: "0.85rem",
                                color: "text.primary",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {tc.question}
                            </Box>
                          </Tooltip>
                        </TableCell>
                        <TableCell sx={{ maxWidth: 280 }}>
                          {tc.expected_answer ? (
                            <Tooltip title={tc.expected_answer} placement="top-start" arrow>
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
                                {tc.expected_answer}
                              </Box>
                            </Tooltip>
                          ) : (
                            <Box component="span" sx={{ color: "text.disabled", fontStyle: "italic" }}>—</Box>
                          )}
                        </TableCell>
                        <TableCell align="right" sx={{ pr: 3, whiteSpace: "nowrap" }}>
                          <Tooltip title={t("common.edit")}>
                            <IconButton
                              size="small"
                              onClick={() => openEditCase(tc)}
                              sx={{ color: "text.disabled", "&:hover": { color: ACCENT, backgroundColor: `${ACCENT}10` } }}
                            >
                              <Edit fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title={t("common.delete")}>
                            <IconButton
                              size="small"
                              onClick={() => handleDeleteCase(tc.id)}
                              sx={{ color: "text.disabled", "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.06)" } }}
                            >
                              <Delete fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </TileCard>
          </Box>
        )}
      </Grid>

      <Grid item xs={12} md={6}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<Insights />}
            title={t("projects.edit.knowledge.evals.runs")}
            subtitle={
              runningCount > 0
                ? `${runs.length} runs · ${runningCount} in flight`
                : `${runs.length} run${runs.length === 1 ? "" : "s"}`
            }
            accent={ACCENT}
          />
          {runs.length === 0 ? (
            <EmptyState
              icon={Insights}
              label={t("projects.edit.knowledge.evals.noRuns")}
              accent={ACCENT}
            />
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
                  <TableCell sx={{ pl: 3 }}>{t("projects.edit.knowledge.evals.run")}</TableCell>
                  <TableCell>{t("projects.edit.knowledge.evals.status")}</TableCell>
                  <TableCell>{t("projects.edit.knowledge.evals.scores")}</TableCell>
                  <TableCell align="right" sx={{ pr: 3 }} />
                </TableRow>
              </TableHead>
              <TableBody>
                {runs.map((r) => {
                  const isSel = selectedRun?.id === r.id;
                  const sMeta = STATUS_META[r.status] || STATUS_META.pending;
                  return (
                    <TableRow
                      key={r.id}
                      onClick={() => openRunResults(r.id)}
                      sx={{
                        cursor: "pointer",
                        backgroundColor: isSel ? `${ACCENT}08` : undefined,
                        borderLeft: isSel ? `2px solid ${ACCENT}` : "2px solid transparent",
                        transition: "background-color 0.15s ease",
                        "&:hover": { backgroundColor: isSel ? `${ACCENT}10` : `${sMeta.color}05` },
                      }}
                    >
                      <TableCell sx={{ pl: 3, py: 1.25 }}>
                        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.15 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                            <Box
                              component="span"
                              sx={{
                                fontFamily: FONT_MONO,
                                fontSize: "0.78rem",
                                fontWeight: 700,
                                color: "text.primary",
                              }}
                            >
                              #{r.id}
                            </Box>
                            {r.prompt_version_id && (
                              <Chip
                                label={`v${r.prompt_version ?? r.prompt_version_id}`}
                                size="small"
                                sx={{
                                  height: 16,
                                  fontFamily: FONT_MONO,
                                  fontSize: "0.6rem",
                                  fontWeight: 600,
                                  backgroundColor: ACCENT_SOFT,
                                  color: ACCENT,
                                  "& .MuiChip-label": { px: 0.5 },
                                }}
                              />
                            )}
                          </Box>
                          {r.completed_at && (
                            <Box
                              component="span"
                              sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled" }}
                            >
                              {formatRelative(r.completed_at)}
                            </Box>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <StatusPill status={r.status} />
                      </TableCell>
                      <TableCell>
                        {r.summary
                          ? Object.entries(r.summary).map(([k, v]) => (
                              <MetricScoreBar key={k} name={k} score={v} />
                            ))
                          : <Box component="span" sx={{ color: "text.disabled" }}>—</Box>}
                      </TableCell>
                      <TableCell align="right" sx={{ pr: 3 }}>
                        <IconButton
                          size="small"
                          onClick={(e) => { e.stopPropagation(); handleDeleteRun(r.id); }}
                          sx={{ color: "text.disabled", "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.06)" } }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </TileCard>
      </Grid>

      <AccentDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t("projects.edit.knowledge.evals.newDatasetTitle")}
        subtitle="A dataset is a collection of test cases evaluated together"
        accent={ACCENT}
        actions={
          <>
            <Button onClick={() => setCreateOpen(false)} sx={{ textTransform: "none", color: "text.secondary" }}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="contained"
              onClick={handleCreateDataset}
              disabled={!newDataset.name}
              sx={{
                textTransform: "none",
                fontWeight: 700,
                background: `linear-gradient(135deg, ${ACCENT} 0%, #0d9488 100%)`,
                "&:hover": { background: `linear-gradient(135deg, ${ACCENT} 0%, #0f766e 100%)` },
              }}
            >
              {t("common.create")}
            </Button>
          </>
        }
      >
        <TextField
          autoFocus fullWidth margin="dense" size="small"
          label={t("projects.edit.knowledge.evals.name")}
          value={newDataset.name}
          onChange={(e) => setNewDataset({ ...newDataset, name: e.target.value })}
        />
        <TextField
          fullWidth margin="dense" size="small" multiline rows={2}
          label={t("projects.edit.knowledge.evals.description")}
          value={newDataset.description}
          onChange={(e) => setNewDataset({ ...newDataset, description: e.target.value })}
        />
      </AccentDialog>

      <AccentDialog
        open={caseModalOpen}
        onClose={() => setCaseModalOpen(false)}
        title={caseEditId != null
          ? t("projects.edit.knowledge.evals.editTestCase")
          : t("projects.edit.knowledge.evals.addTestCase")}
        accent={ACCENT}
        actions={
          <>
            <Button onClick={() => setCaseModalOpen(false)} sx={{ textTransform: "none", color: "text.secondary" }}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="contained"
              onClick={handleSaveCase}
              disabled={!newCase.question}
              sx={{
                textTransform: "none",
                fontWeight: 700,
                background: `linear-gradient(135deg, ${ACCENT} 0%, #0d9488 100%)`,
                "&:hover": { background: `linear-gradient(135deg, ${ACCENT} 0%, #0f766e 100%)` },
              }}
            >
              {caseEditId != null ? t("common.save") : t("common.add")}
            </Button>
          </>
        }
      >
        <TextField
          autoFocus fullWidth margin="dense" size="small" multiline rows={3}
          label={t("projects.edit.knowledge.evals.question")}
          value={newCase.question}
          onChange={(e) => setNewCase({ ...newCase, question: e.target.value })}
        />
        <TextField
          fullWidth margin="dense" size="small" multiline rows={3}
          label={t("projects.edit.knowledge.evals.expectedOptional")}
          value={newCase.expected_answer}
          onChange={(e) => setNewCase({ ...newCase, expected_answer: e.target.value })}
          helperText={t("projects.edit.knowledge.evals.expectedHelp")}
        />
      </AccentDialog>

      <AccentDialog
        open={runOpen}
        onClose={() => setRunOpen(false)}
        title={t("projects.edit.knowledge.evals.runEval")}
        subtitle={t("projects.edit.knowledge.evals.selectMetrics")}
        accent={ACCENT}
        actions={
          <>
            <Button onClick={() => setRunOpen(false)} sx={{ textTransform: "none", color: "text.secondary" }}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="contained"
              onClick={handleStartRun}
              disabled={loading || runMetrics.length === 0}
              startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <PlayArrow />}
              sx={{
                textTransform: "none",
                fontWeight: 700,
                background: `linear-gradient(135deg, ${ACCENT} 0%, #0d9488 100%)`,
                boxShadow: `0 4px 14px ${ACCENT}55`,
                "&:hover": {
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #0f766e 100%)`,
                  boxShadow: `0 6px 18px ${ACCENT}77`,
                },
              }}
            >
              {loading ? t("projects.edit.knowledge.evals.starting") : t("projects.edit.knowledge.evals.start")}
            </Button>
          </>
        }
      >
        <Box
          sx={{
            display: "flex", alignItems: "center", gap: 1,
            mb: 2, p: 1, borderRadius: 1.5,
            backgroundColor: ACCENT_SOFT, border: `1px solid ${ACCENT}30`,
          }}
        >
          <Science sx={{ fontSize: 16, color: ACCENT, flexShrink: 0 }} />
          <Box component="span" sx={{ fontSize: "0.78rem", color: "text.secondary" }}>
            {t("projects.edit.knowledge.evals.judgedBy")}{" "}
            <Box component="span" sx={{ fontFamily: FONT_MONO, fontWeight: 700, color: ACCENT }}>
              {project.options?.eval_llm || project.llm || "—"}
            </Box>
          </Box>
        </Box>
        <FormControl component="fieldset" sx={{ width: "100%" }}>
          <FormGroup>
            {metricOptions.map((m) => {
              const checked = runMetrics.includes(m.key);
              const color = METRIC_COLORS[m.key];
              return (
                <Box
                  key={m.key}
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                    p: 1,
                    mb: 0.5,
                    borderRadius: 1.5,
                    border: `1px solid ${checked ? `${color}55` : "rgba(15,23,42,0.08)"}`,
                    backgroundColor: checked ? `${color}08` : "transparent",
                    transition: "all 0.15s ease",
                    cursor: "pointer",
                    "&:hover": { borderColor: `${color}55` },
                  }}
                  onClick={() => toggleMetric(m.key)}
                >
                  <FormControlLabel
                    sx={{ m: 0, flex: 1 }}
                    control={
                      <Checkbox
                        checked={checked}
                        onChange={() => toggleMetric(m.key)}
                        sx={{
                          color: `${color}88`,
                          "&.Mui-checked": { color },
                        }}
                      />
                    }
                    label={
                      <Box>
                        <Box
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.78rem",
                            fontWeight: 700,
                            color,
                            letterSpacing: "0.04em",
                            textTransform: "uppercase",
                          }}
                        >
                          {m.key.replace(/_/g, " ")}
                        </Box>
                        <Box
                          component="span"
                          sx={{
                            display: "block",
                            fontSize: "0.78rem",
                            color: "text.secondary",
                            mt: 0.25,
                          }}
                        >
                          {m.label}
                        </Box>
                      </Box>
                    }
                  />
                </Box>
              );
            })}
          </FormGroup>
          {!isRag && (
            <Typography variant="caption" color="text.disabled" sx={{ mt: 1, display: "block" }}>
              {t("projects.edit.knowledge.evals.faithfulnessRagOnly")}
            </Typography>
          )}
        </FormControl>
      </AccentDialog>

      <RunResultsDialog
        open={resultsOpen}
        onClose={() => setResultsOpen(false)}
        run={resultsOpen ? selectedRun : null}
        t={t}
      />
    </Grid>
  );
}
