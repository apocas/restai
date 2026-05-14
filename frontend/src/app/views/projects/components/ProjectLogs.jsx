import React, { useEffect, useMemo, useState } from "react";
import {
  Box, Card, Chip, CircularProgress, Collapse, IconButton,
  InputAdornment, MenuItem, styled, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Tooltip, Typography,
} from "@mui/material";
import {
  Article, ChevronLeft, ChevronRight, Search, Close, ExpandMore,
  ExpandLess, CheckCircle, Error as ErrorIcon, Warning, Info as InfoIcon,
  Image as ImageIcon, AttachFile, PlayCircleOutline,
} from "@mui/icons-material";
import ReactJson from "@microlink/react-json-view";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";
import ChatReplayDialog from "./ChatReplayDialog";

// Logs = inference history / trace. Violet = unique vs cron-amber and
// audit-indigo so the user knows which "log" surface they're on.
const ACCENT = "#8b5cf6";
const ACCENT_SOFT = "rgba(139,92,246,0.10)";

const STATUS_META = {
  success:     { color: "#10b981", soft: "rgba(16,185,129,0.12)", icon: CheckCircle, label: "OK" },
  error:       { color: "#ef4444", soft: "rgba(239,68,68,0.12)",  icon: ErrorIcon,   label: "ERROR" },
  guard_block: { color: "#f59e0b", soft: "rgba(245,158,11,0.12)", icon: Warning,     label: "GUARD" },
  rate_limit:  { color: "#f59e0b", soft: "rgba(245,158,11,0.12)", icon: Warning,     label: "RATE" },
  budget:      { color: "#f59e0b", soft: "rgba(245,158,11,0.12)", icon: Warning,     label: "BUDGET" },
  quota:       { color: "#f59e0b", soft: "rgba(245,158,11,0.12)", icon: Warning,     label: "QUOTA" },
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

function StatusPill({ status }) {
  const meta = STATUS_META[status] || STATUS_META.success;
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.65,
        px: 1,
        py: 0.4,
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
          textTransform: "uppercase",
        }}
      >
        {meta.label}
      </Box>
    </Box>
  );
}

function StatusSummary({ icon: Icon, count, color, label }) {
  return (
    <Tooltip title={label} arrow>
      <Box
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.5,
          px: 1,
          py: 0.5,
          borderRadius: 1,
          color: count > 0 ? color : "text.disabled",
          backgroundColor: count > 0 ? `${color}10` : "rgba(15,23,42,0.025)",
          border: `1px solid ${count > 0 ? `${color}33` : "rgba(15,23,42,0.06)"}`,
        }}
      >
        <Icon sx={{ fontSize: 14 }} />
        <Box
          component="span"
          sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", fontWeight: 700 }}
        >
          {count}
        </Box>
      </Box>
    </Tooltip>
  );
}

// ── Latency badge — green <1s, amber <5s, red ≥5s. Helps spot slow
// turns in a glance.
function LatencyBadge({ ms }) {
  if (ms == null) return <Box component="span" sx={{ color: "text.disabled" }}>—</Box>;
  const color = ms < 1000 ? "#10b981" : ms < 5000 ? "#f59e0b" : "#ef4444";
  const label = ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 0.85,
        py: 0.25,
        borderRadius: 0.75,
        fontFamily: FONT_MONO,
        fontSize: "0.7rem",
        fontWeight: 700,
        color,
        backgroundColor: `${color}10`,
        border: `1px solid ${color}33`,
      }}
    >
      {label}
    </Box>
  );
}

// Terminal-style code block — same vocabulary as cron-logs / audit.
function LogBlock({ label, content, accent, mono = true }) {
  return (
    <Box
      sx={{
        borderRadius: 2,
        overflow: "hidden",
        border: "1px solid rgba(15,23,42,0.08)",
        backgroundColor: "#0b1220",
        boxShadow: "0 6px 18px rgba(15,23,42,0.16)",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 0.85,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          backgroundColor: "rgba(255,255,255,0.02)",
        }}
      >
        <Box sx={{ display: "flex", gap: 0.6 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <Box
              key={c}
              sx={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: c, opacity: 0.85 }}
            />
          ))}
        </Box>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.65rem",
            color: accent || "#7dd3fc",
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            fontWeight: 700,
          }}
        >
          {label}
        </Typography>
      </Box>
      <Box
        component="pre"
        sx={{
          margin: 0,
          padding: "12px 16px",
          fontFamily: mono ? FONT_MONO : "inherit",
          fontSize: "0.76rem",
          lineHeight: 1.6,
          color: "#cbd5e1",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          maxHeight: 320,
          overflow: "auto",
        }}
      >
        {content}
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

const safeJson = (s) => {
  if (!s) return null;
  try { return JSON.parse(s); } catch { return null; }
};

const truncate = (s, n) => {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
};

export default function ProjectLogs({ project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [replayChatId, setReplayChatId] = useState(null);

  const fetchLogs = (projectID, start, end) => {
    setLoading(true);
    return api.get(`/projects/${projectID}/logs?start=${start}&end=${end}`, auth.user.token)
      .then((d) => {
        if (d.logs) setLogs(d.logs);
        return d;
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (project?.id) {
      fetchLogs(project.id, page * rowsPerPage, (page + 1) * rowsPerPage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.id, page, rowsPerPage]);

  // Reset paging when filters change.
  useEffect(() => { setPage(0); }, [filterStatus]);

  // Local search/filter applied on top of the current page slice.
  const filtered = useMemo(() => {
    return logs.filter((l) => {
      if (filterStatus) {
        if (filterStatus === "non_success" && (l.status || "success") === "success") return false;
        if (filterStatus !== "non_success" && (l.status || "success") !== filterStatus) return false;
      }
      if (search.trim()) {
        const needle = search.trim().toLowerCase();
        const hit =
          (l.question || "").toLowerCase().includes(needle) ||
          (l.answer || "").toLowerCase().includes(needle) ||
          (l.llm || "").toLowerCase().includes(needle) ||
          (l.error || "").toLowerCase().includes(needle);
        if (!hit) return false;
      }
      return true;
    });
  }, [logs, filterStatus, search]);

  // Tally for the toolbar — based on the visible (filtered) page.
  const tally = useMemo(() => {
    const acc = { success: 0, error: 0, guard: 0, slow: 0 };
    for (const l of logs) {
      const s = l.status || "success";
      if (s === "success") acc.success++;
      else if (s === "error") acc.error++;
      else acc.guard++;
      if ((l.latency_ms || 0) >= 5000) acc.slow++;
    }
    return acc;
  }, [logs]);

  const handleNextPage = () => setPage((p) => p + 1);
  const handlePrevPage = () => setPage((p) => Math.max(0, p - 1));

  return (
    <>
    <TileCard elevation={0} accent={ACCENT}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          flexWrap: "wrap",
          p: 2,
          borderBottom: "1px solid rgba(15,23,42,0.06)",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mr: 0.5 }}>
          <Box
            sx={{
              width: 36, height: 36,
              flexShrink: 0,
              borderRadius: 1.5,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              background: ACCENT_SOFT,
              color: ACCENT,
            }}
          >
            <Article fontSize="small" />
          </Box>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
              Inference logs
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {logs.length === 0 ? "no entries on this page" : `${logs.length} entries on page ${page + 1}`}
            </Typography>
          </Box>
        </Box>

        <TextField
          size="small"
          placeholder="Search question, answer, LLM or error…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: 1, minWidth: 240 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" sx={{ color: "text.disabled" }} />
              </InputAdornment>
            ),
            endAdornment: search ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setSearch("")}>
                  <Close fontSize="small" />
                </IconButton>
              </InputAdornment>
            ) : null,
          }}
        />

        {/* Status tally on the visible page */}
        <Box sx={{ display: "flex", gap: 0.75 }}>
          <StatusSummary icon={CheckCircle} count={tally.success} color="#10b981" label={`${tally.success} OK`} />
          <StatusSummary icon={Warning}     count={tally.guard}   color="#f59e0b" label={`${tally.guard} guard/limit`} />
          <StatusSummary icon={ErrorIcon}   count={tally.error}   color="#ef4444" label={`${tally.error} errors`} />
          <StatusSummary icon={InfoIcon}    count={tally.slow}    color="#8b5cf6" label={`${tally.slow} slow (≥5s)`} />
        </Box>

        <TextField
          select
          size="small"
          label="Status"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          sx={{ width: 150 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="success">OK only</MenuItem>
          <MenuItem value="non_success">Failures</MenuItem>
          <MenuItem value="error">Errors</MenuItem>
          <MenuItem value="guard_block">Guard blocks</MenuItem>
          <MenuItem value="rate_limit">Rate limit</MenuItem>
          <MenuItem value="budget">Budget</MenuItem>
        </TextField>

        <TextField
          select
          size="small"
          label="Per page"
          value={rowsPerPage}
          onChange={(e) => { setRowsPerPage(Number(e.target.value)); setPage(0); }}
          sx={{ width: 110 }}
        >
          {[10, 25, 50, 100, 500].map((n) => (
            <MenuItem key={n} value={n} sx={{ fontFamily: FONT_MONO }}>{n}</MenuItem>
          ))}
        </TextField>
      </Box>

      <Table size="small">
        <TableHead>
          <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
            <TableCell sx={{ pl: 3, width: 40 }} />
            <TableCell sx={{ width: 110 }}>Status</TableCell>
            <TableCell sx={{ width: 180, whiteSpace: "nowrap" }}>Date</TableCell>
            <TableCell>Question</TableCell>
            <TableCell>Answer</TableCell>
            <TableCell align="right" sx={{ width: 90 }}>Latency</TableCell>
            <TableCell align="right" sx={{ width: 100 }}>Tokens</TableCell>
            <TableCell align="right" sx={{ pr: 3, width: 60 }} />
          </TableRow>
        </TableHead>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={8} align="center" sx={{ py: 5 }}>
                <CircularProgress size={24} sx={{ color: ACCENT }} />
              </TableCell>
            </TableRow>
          ) : filtered.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                <Box sx={{ display: "inline-flex", flexDirection: "column", alignItems: "center", gap: 1.25 }}>
                  <Box
                    sx={{
                      width: 56, height: 56,
                      borderRadius: "50%",
                      background: ACCENT_SOFT,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      animation: `${pulse} 3s ease-out infinite`,
                    }}
                  >
                    <Article sx={{ fontSize: 28, color: ACCENT }} />
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    {search || filterStatus
                      ? "No log entries match the current filters."
                      : page === 0
                        ? "No logs yet — run an inference to see it here."
                        : "End of the log."}
                  </Typography>
                </Box>
              </TableCell>
            </TableRow>
          ) : (
            filtered.map((log) => {
              const isOpen = expandedId === log.id;
              const sMeta = STATUS_META[log.status || "success"] || STATUS_META.success;
              const attachments = safeJson(log.attachments) || [];
              const contextData = safeJson(log.context);
              const toolTrace = safeJson(log.tool_trace);
              const imageSrc = log.image
                ? (log.image.startsWith("data:") ? log.image : `data:image/png;base64,${log.image}`)
                : null;
              const totalTokens = (log.input_tokens || 0) + (log.output_tokens || 0);
              return (
                <React.Fragment key={log.id}>
                  <TableRow
                    hover
                    sx={{
                      cursor: "pointer",
                      transition: "background-color 0.15s ease",
                      backgroundColor: isOpen ? `${sMeta.color}06` : undefined,
                    }}
                    onClick={() => setExpandedId(isOpen ? null : log.id)}
                  >
                    <TableCell sx={{ pl: 3, width: 40 }}>
                      <IconButton size="small" sx={{ color: sMeta.color }}>
                        {isOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                      </IconButton>
                    </TableCell>
                    <TableCell><StatusPill status={log.status || "success"} /></TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap", py: 1.25 }}>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.1 }}>
                        <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", color: "text.primary" }}>
                          {log.date ? new Date(log.date).toLocaleString() : "—"}
                        </Box>
                        <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled" }}>
                          {formatRelative(log.date)}
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
                        {imageSrc && (
                          <Box
                            component="img"
                            src={imageSrc}
                            alt=""
                            sx={{
                              width: 40, height: 40, objectFit: "cover",
                              borderRadius: 1,
                              border: "1px solid rgba(15,23,42,0.08)",
                              flexShrink: 0,
                            }}
                          />
                        )}
                        <Box sx={{ minWidth: 0, flex: 1 }}>
                          <Box
                            sx={{
                              fontSize: "0.85rem",
                              color: "text.primary",
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                              overflow: "hidden",
                              wordBreak: "break-word",
                            }}
                          >
                            {log.question || "—"}
                          </Box>
                          {attachments.length > 0 && (
                            <Box sx={{ display: "flex", gap: 0.5, mt: 0.5, flexWrap: "wrap" }}>
                              {attachments.slice(0, 3).map((a, i) => (
                                <Chip
                                  key={i}
                                  icon={<AttachFile sx={{ fontSize: 11 }} />}
                                  label={a.name}
                                  size="small"
                                  sx={{
                                    height: 18,
                                    fontSize: "0.62rem",
                                    fontFamily: FONT_MONO,
                                    backgroundColor: "rgba(15,23,42,0.04)",
                                    "& .MuiChip-label": { px: 0.5 },
                                  }}
                                />
                              ))}
                              {attachments.length > 3 && (
                                <Chip
                                  label={`+${attachments.length - 3}`}
                                  size="small"
                                  sx={{ height: 18, fontSize: "0.62rem", "& .MuiChip-label": { px: 0.5 } }}
                                />
                              )}
                            </Box>
                          )}
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Box
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.78rem",
                          color: "text.secondary",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                          wordBreak: "break-word",
                        }}
                      >
                        {log.answer || "—"}
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <LatencyBadge ms={log.latency_ms} />
                    </TableCell>
                    <TableCell align="right">
                      {totalTokens > 0 ? (
                        <Tooltip title={`${log.input_tokens || 0} in · ${log.output_tokens || 0} out`} arrow>
                          <Box
                            component="span"
                            sx={{
                              fontFamily: FONT_MONO,
                              fontSize: "0.78rem",
                              fontWeight: 700,
                              color: ACCENT,
                            }}
                          >
                            {totalTokens.toLocaleString()}
                          </Box>
                        </Tooltip>
                      ) : (
                        <Box component="span" sx={{ color: "text.disabled" }}>—</Box>
                      )}
                    </TableCell>
                    <TableCell align="right" sx={{ pr: 3 }} onClick={(e) => e.stopPropagation()}>
                      {log.chat_id ? (
                        <Tooltip title={t("projects.logs.replay.button", "Replay conversation")} arrow>
                          <IconButton
                            size="small"
                            onClick={() => setReplayChatId(log.chat_id)}
                            sx={{ color: ACCENT }}
                          >
                            <PlayCircleOutline fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      ) : null}
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell
                      colSpan={8}
                      sx={{
                        p: 0,
                        borderBottom: isOpen ? undefined : "none",
                        backgroundColor: isOpen ? `${sMeta.color}04` : undefined,
                      }}
                    >
                      <Collapse in={isOpen}>
                        <Box sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 2 }}>
                          {log.error && (log.status || "success") !== "success" && (
                            <LogBlock label="Error" content={log.error} accent="#fca5a5" />
                          )}

                          {imageSrc && (
                            <Box>
                              <Typography
                                sx={{
                                  fontFamily: FONT_MONO,
                                  fontSize: "0.65rem",
                                  letterSpacing: "0.18em",
                                  color: "text.disabled",
                                  fontWeight: 700,
                                  mb: 0.75,
                                }}
                              >
                                <ImageIcon sx={{ fontSize: 14, mr: 0.5, verticalAlign: "text-bottom" }} />
                                UPLOADED IMAGE
                              </Typography>
                              <Box
                                component="img"
                                src={imageSrc}
                                alt=""
                                sx={{
                                  maxWidth: 320,
                                  maxHeight: 240,
                                  borderRadius: 1.5,
                                  border: "1px solid rgba(15,23,42,0.08)",
                                  boxShadow: "0 4px 12px rgba(15,23,42,0.08)",
                                }}
                              />
                            </Box>
                          )}

                          {attachments.length > 0 && (
                            <Box>
                              <Typography
                                sx={{
                                  fontFamily: FONT_MONO,
                                  fontSize: "0.65rem",
                                  letterSpacing: "0.18em",
                                  color: "text.disabled",
                                  fontWeight: 700,
                                  mb: 0.75,
                                }}
                              >
                                ATTACHMENTS
                              </Typography>
                              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                                {attachments.map((a, i) => (
                                  <Chip
                                    key={i}
                                    icon={<AttachFile sx={{ fontSize: 12 }} />}
                                    label={`${a.name}${a.size ? ` · ${Math.round(a.size / 1024)} KB` : ""}`}
                                    size="small"
                                    sx={{
                                      fontFamily: FONT_MONO,
                                      fontSize: "0.7rem",
                                      backgroundColor: ACCENT_SOFT,
                                      color: ACCENT,
                                      border: `1px solid ${ACCENT}33`,
                                    }}
                                  />
                                ))}
                              </Box>
                            </Box>
                          )}

                          {log.system_prompt && (
                            <LogBlock label="System prompt" content={log.system_prompt} accent="#7dd3fc" />
                          )}

                          {contextData && Object.keys(contextData).length > 0 && (
                            <Box>
                              <Typography
                                sx={{
                                  fontFamily: FONT_MONO,
                                  fontSize: "0.65rem",
                                  letterSpacing: "0.18em",
                                  color: "text.disabled",
                                  fontWeight: 700,
                                  mb: 0.75,
                                }}
                              >
                                CONTEXT
                              </Typography>
                              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                                {Object.entries(contextData).map(([k, v]) => (
                                  <Chip
                                    key={k}
                                    label={`${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`}
                                    size="small"
                                    sx={{
                                      fontFamily: FONT_MONO,
                                      fontSize: "0.7rem",
                                      backgroundColor: "rgba(15,23,42,0.04)",
                                    }}
                                  />
                                ))}
                              </Box>
                            </Box>
                          )}

                          {toolTrace && toolTrace.length > 0 && (
                            <Box>
                              <Typography
                                sx={{
                                  fontFamily: FONT_MONO,
                                  fontSize: "0.65rem",
                                  letterSpacing: "0.18em",
                                  color: "text.disabled",
                                  fontWeight: 700,
                                  mb: 0.75,
                                }}
                              >
                                TOOL TRACE · {toolTrace.length} CALL{toolTrace.length === 1 ? "" : "S"}
                              </Typography>
                              <Box
                                sx={{
                                  borderRadius: 2,
                                  border: "1px solid rgba(15,23,42,0.08)",
                                  backgroundColor: "#fff",
                                  overflow: "hidden",
                                }}
                              >
                                {toolTrace.map((step, i) => {
                                  const isErr = step.status === "error";
                                  const stepColor = isErr ? "#ef4444" : ACCENT;
                                  return (
                                    <Box
                                      key={i}
                                      sx={{
                                        display: "flex",
                                        alignItems: "flex-start",
                                        gap: 1.5,
                                        p: 1.25,
                                        borderTop: i === 0 ? 0 : "1px solid rgba(15,23,42,0.06)",
                                        backgroundColor: isErr ? "rgba(239,68,68,0.04)" : "transparent",
                                      }}
                                    >
                                      <Box
                                        sx={{
                                          width: 6, height: 6,
                                          mt: 0.85,
                                          borderRadius: "50%",
                                          background: stepColor,
                                          boxShadow: `0 0 6px ${stepColor}88`,
                                          flexShrink: 0,
                                        }}
                                      />
                                      <Box sx={{ flex: 1, minWidth: 0 }}>
                                        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
                                          <Box
                                            component="span"
                                            sx={{
                                              fontFamily: FONT_MONO,
                                              fontSize: "0.78rem",
                                              fontWeight: 700,
                                              color: stepColor,
                                            }}
                                          >
                                            {step.tool}
                                          </Box>
                                          <Box
                                            component="code"
                                            sx={{
                                              fontFamily: FONT_MONO,
                                              fontSize: "0.7rem",
                                              color: "text.secondary",
                                              backgroundColor: "rgba(15,23,42,0.04)",
                                              px: 0.65,
                                              py: 0.15,
                                              borderRadius: 0.5,
                                              maxWidth: "100%",
                                              overflow: "hidden",
                                              textOverflow: "ellipsis",
                                              whiteSpace: "nowrap",
                                            }}
                                          >
                                            {step.args || "(no args)"}
                                          </Box>
                                        </Box>
                                        {isErr && step.error && (
                                          <Box
                                            sx={{
                                              mt: 0.75,
                                              fontFamily: FONT_MONO,
                                              fontSize: "0.7rem",
                                              color: "#9f3a38",
                                              whiteSpace: "pre-wrap",
                                            }}
                                          >
                                            {truncate(step.error, 280)}
                                          </Box>
                                        )}
                                      </Box>
                                      <LatencyBadge ms={step.latency_ms} />
                                    </Box>
                                  );
                                })}
                              </Box>
                            </Box>
                          )}

                          {/* Raw JSON for debugging */}
                          <Box>
                            <Typography
                              sx={{
                                fontFamily: FONT_MONO,
                                fontSize: "0.65rem",
                                letterSpacing: "0.18em",
                                color: "text.disabled",
                                fontWeight: 700,
                                mb: 0.75,
                              }}
                            >
                              RAW
                            </Typography>
                            <Box
                              sx={{
                                p: 1.5,
                                borderRadius: 1.5,
                                border: "1px solid rgba(15,23,42,0.08)",
                                backgroundColor: "rgba(15,23,42,0.02)",
                              }}
                            >
                              <ReactJson
                                src={log}
                                enableClipboard={false}
                                collapsed={1}
                                displayDataTypes={false}
                                displayObjectSize={false}
                                style={{ fontFamily: FONT_MONO, fontSize: "0.75rem", backgroundColor: "transparent" }}
                              />
                            </Box>
                          </Box>
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              );
            })
          )}
        </TableBody>
      </Table>

      {/* Pager footer */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          p: 1.5,
          borderTop: "1px solid rgba(15,23,42,0.06)",
        }}
      >
        <Typography
          variant="caption"
          sx={{ fontFamily: FONT_MONO, color: "text.secondary" }}
        >
          Page {page + 1}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <IconButton
            size="small"
            onClick={handlePrevPage}
            disabled={page === 0 || loading}
          >
            <ChevronLeft fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            onClick={handleNextPage}
            // Disable Next when the *unfiltered* page is empty (we hit
            // the end of the server's data) or when the page is shorter
            // than the requested rowsPerPage.
            disabled={loading || logs.length === 0 || logs.length < rowsPerPage}
          >
            <ChevronRight fontSize="small" />
          </IconButton>
        </Box>
      </Box>
    </TileCard>
    <ChatReplayDialog
      open={!!replayChatId}
      onClose={() => setReplayChatId(null)}
      projectId={project?.id}
      projectName={project?.name}
      chatId={replayChatId}
    />
    </>
  );
}
