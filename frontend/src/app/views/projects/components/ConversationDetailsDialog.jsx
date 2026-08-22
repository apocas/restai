import { Fragment, useEffect, useMemo, useState } from "react";
import {
  Box, Chip, CircularProgress, Dialog, DialogContent, DialogTitle,
  IconButton, Table, TableBody, TableCell, TableHead, TableRow,
  Tooltip, Typography, useTheme,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import QueryStatsIcon from "@mui/icons-material/QueryStats";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { formatCost } from "app/utils/utils";
import { formatMs } from "app/utils/runTelemetry";
import { TraceTimelineBar, TimelineLegend } from "./RunTelemetry";

const FONT_MONO = '"JetBrains Mono", "Fira Code", monospace';

// Same validated reference palette as RunTelemetry: blue = input/latency
// (categorical slot 1), orange = output (slot 2).
const SERIES = {
  light: { input: "#2a78d6", output: "#eb6834", error: "#d03b3b" },
  dark: { input: "#3987e5", output: "#d95926", error: "#d03b3b" },
};

// Cap the mini charts at the most recent N turns so a 500-turn conversation
// still renders instantly; the table below always lists everything.
const CHART_TURNS = 30;

// Repo-native section header: mono, uppercase, tracked-out — the same micro
// label language ProjectLogs uses, so the dialog reads as part of the log
// viewer rather than a stock MUI surface.
function SectionLabel({ children, sx }) {
  return (
    <Typography
      sx={{
        fontFamily: FONT_MONO, fontSize: "0.62rem", letterSpacing: "0.18em",
        color: "text.disabled", fontWeight: 700, textTransform: "uppercase",
        ...sx,
      }}
    >
      {children}
    </Typography>
  );
}

function StatTile({ label, value, sub, danger }) {
  return (
    <Box
      sx={{
        px: 1.5, py: 1, borderRadius: 1.5, minWidth: 96,
        backgroundColor: "action.hover",
        border: "1px solid", borderColor: "divider",
      }}
    >
      <SectionLabel sx={{ fontSize: "0.58rem", letterSpacing: "0.14em" }}>{label}</SectionLabel>
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "1.05rem", fontWeight: 700, color: danger ? "error.main" : "text.primary", lineHeight: 1.3 }}>
        {value}
      </Typography>
      {sub && (
        <Typography sx={{ fontSize: "0.65rem", color: "text.secondary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 200 }}>
          {sub}
        </Typography>
      )}
    </Box>
  );
}

// Compact vertical bar strip built in plain HTML (per-mark tooltips, 2px
// gaps, baseline-anchored bars). One value accessor for single-series,
// stacked input/output for the token variant.
function MiniBars({ turns, mode, colors }) {
  const maxValue = Math.max(
    1,
    ...turns.map((t) =>
      mode === "latency" ? (t.latency_ms || 0) : (t.input_tokens || 0) + (t.output_tokens || 0)
    ),
  );
  return (
    <Box sx={{ display: "flex", alignItems: "flex-end", gap: "2px", height: 72 }}>
      {turns.map((t, i) => {
        if (mode === "latency") {
          const v = t.latency_ms || 0;
          return (
            <Tooltip key={t.id ?? i} arrow title={`Turn ${t.turn}: ${formatMs(v)}`}>
              <Box sx={{
                flex: 1, minWidth: 4, borderRadius: "4px 4px 0 0",
                height: `${Math.max(3, (v / maxValue) * 100)}%`,
                backgroundColor: t.status !== "success" && t.status !== "guard" ? colors.error : colors.input,
              }} />
            </Tooltip>
          );
        }
        const inTok = t.input_tokens || 0;
        const outTok = t.output_tokens || 0;
        const total = inTok + outTok;
        return (
          <Tooltip key={t.id ?? i} arrow title={`Turn ${t.turn}: ${inTok.toLocaleString()} in · ${outTok.toLocaleString()} out`}>
            <Box sx={{
              flex: 1, minWidth: 4, display: "flex", flexDirection: "column-reverse",
              height: `${Math.max(3, (total / maxValue) * 100)}%`, gap: "2px",
            }}>
              <Box sx={{ flexGrow: inTok, backgroundColor: colors.input, borderRadius: outTok ? 0 : "4px 4px 0 0" }} />
              {outTok > 0 && <Box sx={{ flexGrow: outTok, backgroundColor: colors.output, borderRadius: "4px 4px 0 0" }} />}
            </Box>
          </Tooltip>
        );
      })}
    </Box>
  );
}

function OutcomeChips({ turn }) {
  return (
    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
      {turn.status && turn.status !== "success" && (
        <Chip label={turn.status.replace("_", " ")} size="small" color="error" variant="outlined" sx={{ height: 18, fontSize: "0.62rem" }} />
      )}
      {turn.stop_reason && (
        <Chip label={turn.stop_reason.replace("_", " ")} size="small" sx={{ height: 18, fontSize: "0.62rem" }} />
      )}
      {turn.retries > 0 && (
        <Chip label={`retries ${turn.retries}`} size="small" sx={{ height: 18, fontSize: "0.62rem" }} />
      )}
      {turn.fallbacks > 0 && (
        <Chip label={`fallbacks ${turn.fallbacks}`} size="small" sx={{ height: 18, fontSize: "0.62rem" }} />
      )}
      {turn.token_accuracy && (
        <Chip label={`tokens ${turn.token_accuracy}`} size="small" variant="outlined" sx={{ height: 18, fontSize: "0.62rem" }} />
      )}
    </Box>
  );
}

export default function ConversationDetailsDialog({ open, onClose, projectId, chatId }) {
  const auth = useAuth();
  const theme = useTheme();
  const colors = SERIES[theme.palette.mode === "dark" ? "dark" : "light"];
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [expandedTurn, setExpandedTurn] = useState(null);

  useEffect(() => {
    if (!open || !chatId) return;
    setData(null);
    setError(null);
    setExpandedTurn(null);
    api.get(`/projects/${projectId}/logs/conversation/${encodeURIComponent(chatId)}/details`, auth.user.token)
      .then(setData)
      .catch((e) => setError((e && e.detail) || "Failed to load conversation details."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, chatId, projectId]);

  const turns = useMemo(
    () => (data?.turns || []).map((t, i) => ({ ...t, turn: i + 1 })),
    [data],
  );
  const chartTurns = turns.slice(-CHART_TURNS);
  const s = data?.summary || {};
  const toolStats = data?.tools?.tools || [];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pr: 6 }}>
        <QueryStatsIcon fontSize="small" />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          Conversation details
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", color: "text.secondary", overflow: "hidden", textOverflow: "ellipsis" }}>
            {chatId}
          </Typography>
        </Box>
        <IconButton onClick={onClose} sx={{ position: "absolute", right: 8, top: 8 }} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {error && <Typography color="error">{error}</Typography>}
        {!data && !error && (
          <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress size={26} /></Box>
        )}
        {data && (
          <>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 2 }}>
              <StatTile label="TURNS" value={s.turns} sub={s.distinct_users > 1 ? `${s.distinct_users} users` : null} />
              <StatTile
                label="TOKENS"
                value={(s.total_tokens || 0).toLocaleString()}
                sub={`${(s.input_tokens || 0).toLocaleString()} in · ${(s.output_tokens || 0).toLocaleString()} out`}
              />
              <StatTile label="COST" value={formatCost ? formatCost(s.cost || 0) : `$${(s.cost || 0).toFixed(4)}`} />
              <StatTile label="AVG LATENCY" value={formatMs(s.avg_latency_ms)} sub={`p95 ${formatMs(s.p95_latency_ms)}`} />
              <StatTile label="ERROR TURNS" value={s.error_turns || 0} danger={(s.error_turns || 0) > 0} />
              <StatTile label="MODELS" value={(s.models || []).length || "—"} sub={(s.models || []).join(", ") || null} />
            </Box>

            {chartTurns.length > 1 && (
              <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap", mb: 2 }}>
                <Box sx={{ flex: 1, minWidth: 260 }}>
                  <SectionLabel sx={{ mb: 0.75 }}>
                    Latency per turn{turns.length > CHART_TURNS ? ` (last ${CHART_TURNS})` : ""}
                  </SectionLabel>
                  <MiniBars turns={chartTurns} mode="latency" colors={colors} />
                </Box>
                <Box sx={{ flex: 1, minWidth: 260 }}>
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
                    <SectionLabel>Tokens per turn</SectionLabel>
                    <Box sx={{ display: "flex", gap: 1.5 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: "3px", backgroundColor: colors.input }} />
                        <Typography sx={{ fontSize: "0.65rem", color: "text.secondary" }}>Input</Typography>
                      </Box>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: "3px", backgroundColor: colors.output }} />
                        <Typography sx={{ fontSize: "0.65rem", color: "text.secondary" }}>Output</Typography>
                      </Box>
                    </Box>
                  </Box>
                  <MiniBars turns={chartTurns} mode="tokens" colors={colors} />
                </Box>
              </Box>
            )}

            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
              <SectionLabel>Turns</SectionLabel>
              <TimelineLegend />
            </Box>
            <Table size="small" sx={{ mb: 2 }}>
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Time</TableCell>
                  <TableCell sx={{ width: "34%" }}>Run timeline</TableCell>
                  <TableCell>Outcome</TableCell>
                  <TableCell align="right">Tokens</TableCell>
                  <TableCell align="right">Cost</TableCell>
                  <TableCell align="right">Latency</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {turns.map((t) => (
                  <Fragment key={t.id ?? t.turn}>
                    <TableRow
                      hover
                      onClick={() => setExpandedTurn(expandedTurn === t.turn ? null : t.turn)}
                      sx={{ cursor: "pointer" }}
                    >
                      <TableCell sx={{ fontFamily: FONT_MONO }}>{t.turn}</TableCell>
                      <TableCell sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", whiteSpace: "nowrap" }}>
                        {t.date ? new Date(t.date).toLocaleTimeString() : "—"}
                      </TableCell>
                      <TableCell>
                        {t.tool_trace?.length > 0
                          ? <TraceTimelineBar trace={t.tool_trace} />
                          : <Typography sx={{ fontSize: "0.7rem", color: "text.disabled" }}>—</Typography>}
                      </TableCell>
                      <TableCell><OutcomeChips turn={t} /></TableCell>
                      <TableCell align="right" sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                        {((t.input_tokens || 0) + (t.output_tokens || 0)).toLocaleString()}
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem" }}>
                        {formatCost ? formatCost(t.cost || 0) : (t.cost || 0).toFixed(4)}
                      </TableCell>
                      <TableCell align="right" sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem" }}>
                        {formatMs(t.latency_ms)}
                      </TableCell>
                    </TableRow>
                    {expandedTurn === t.turn && (
                      <TableRow>
                        <TableCell colSpan={7} sx={{ backgroundColor: "action.hover" }}>
                          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled", fontWeight: 700 }}>QUESTION</Typography>
                          <Typography sx={{ fontSize: "0.78rem", whiteSpace: "pre-wrap", mb: 1 }}>
                            {(t.question || "").slice(0, 1200) || "—"}
                          </Typography>
                          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled", fontWeight: 700 }}>ANSWER</Typography>
                          <Typography sx={{ fontSize: "0.78rem", whiteSpace: "pre-wrap", mb: 1 }}>
                            {(t.answer || "").slice(0, 1200) || "—"}
                          </Typography>
                          {t.error && (
                            <>
                              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "error.main", fontWeight: 700 }}>ERROR</Typography>
                              <Typography sx={{ fontSize: "0.75rem", color: "error.main", whiteSpace: "pre-wrap", mb: 1 }}>
                                {t.error.slice(0, 600)}
                              </Typography>
                            </>
                          )}
                          {(t.tool_trace || []).filter((r) => r.tool !== "llm_turn").length > 0 && (
                            <>
                              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled", fontWeight: 700 }}>TOOL CALLS</Typography>
                              {(t.tool_trace || []).filter((r) => r.tool !== "llm_turn").map((r, i) => (
                                <Typography key={i} sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", color: r.status === "error" ? "error.main" : "text.secondary" }}>
                                  {r.tool} · {formatMs(r.latency_ms)}{r.status === "error" ? ` · ${(r.error || "error").slice(0, 160)}` : ""}
                                </Typography>
                              ))}
                            </>
                          )}
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                ))}
              </TableBody>
            </Table>

            {toolStats.length > 0 && (
              <>
                <SectionLabel sx={{ mb: 0.75 }}>Tool usage in this conversation</SectionLabel>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Tool</TableCell>
                      <TableCell align="right">Calls</TableCell>
                      <TableCell align="right">Errors</TableCell>
                      <TableCell align="right">p50</TableCell>
                      <TableCell align="right">p95</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {toolStats.map((row) => (
                      <TableRow key={row.tool}>
                        <TableCell sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem" }}>{row.tool}</TableCell>
                        <TableCell align="right">{row.calls}</TableCell>
                        <TableCell align="right" sx={{ color: row.errors > 0 ? "error.main" : undefined }}>{row.errors}</TableCell>
                        <TableCell align="right">{formatMs(row.p50_ms)}</TableCell>
                        <TableCell align="right">{formatMs(row.p95_ms)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
