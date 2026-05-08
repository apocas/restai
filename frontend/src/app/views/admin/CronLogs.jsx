import React, { useState, useEffect } from "react";
import {
  Box, Button, Card, CircularProgress, Collapse, styled, Typography,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, MenuItem, IconButton, InputAdornment, Tooltip,
} from "@mui/material";
import ScheduleIcon from "@mui/icons-material/Schedule";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import WarningIcon from "@mui/icons-material/Warning";
import PageHero from "app/components/page/PageHero";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toCsv, downloadCsv } from "app/utils/csvExport";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Cron = scheduled clockwork / machinery → amber accent. Distinct from
// the other modernized pages (chat=emerald, embeddings=indigo,
// images=violet, audio=cyan, classifier=purple, proxy=cyan).
const ACCENT = "#f59e0b";
const ACCENT_SOFT = "rgba(245,158,11,0.10)";

// ── Per-status visual config (dot colour + label colour + icon).
const STATUS_META = {
  success: { color: "#10b981", soft: "rgba(16,185,129,0.12)", icon: CheckCircleIcon },
  error:   { color: "#ef4444", soft: "rgba(239,68,68,0.12)",  icon: ErrorIcon },
  warning: { color: "#f59e0b", soft: "rgba(245,158,11,0.12)", icon: WarningIcon },
};

const JOBS = ["sync", "telegram", "docker_cleanup", "routines"];

// ── Tile card — same accent-rail vocabulary as the project library
// cards / direct-access / proxy / classifier pages.
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

// ── Status pill: dot + label, tinted by status.
function StatusPill({ status }) {
  const meta = STATUS_META[status] || { color: "#6b7280", soft: "rgba(107,114,128,0.12)" };
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
          width: 7,
          height: 7,
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
        {status}
      </Box>
    </Box>
  );
}

// ── Mini summary stat for the toolbar (success/error/warning counts in
// the current page).
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

// ── Terminal-style block for log message + traceback. Same look as the
// other modernized pages.
function LogBlock({ label, content, accent }) {
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
          padding: "14px 18px",
          fontFamily: FONT_MONO,
          fontSize: "0.76rem",
          lineHeight: 1.6,
          color: "#cbd5e1",
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          maxHeight: 320,
          overflow: "auto",
        }}
      >
        {content}
      </Box>
    </Box>
  );
}

const formatDuration = (ms) => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
};

const formatRelative = (iso) => {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

export default function CronLogs() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [filterJob, setFilterJob] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [running, setRunning] = useState(false);
  const pageSize = 25;

  const fetchEntries = () => {
    const params = new URLSearchParams({
      start: page * pageSize,
      end: (page + 1) * pageSize,
    });
    if (filterJob) params.set("job", filterJob);
    if (filterStatus) params.set("status", filterStatus);

    api.get("/cron-logs?" + params.toString(), auth.user.token, { silent: true })
      .then((data) => {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      })
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("cron.title");
    fetchEntries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filterJob, filterStatus, t]);

  const totalPages = Math.ceil(total / pageSize);

  const handleRunNow = () => {
    setRunning(true);
    api.post("/cron-logs/run", {}, auth.user.token)
      .then(() => {
        setTimeout(() => {
          fetchEntries();
          setRunning(false);
        }, 3000);
      })
      .catch(() => setRunning(false));
  };

  const exportCsv = () => {
    const csv = toCsv(entries, [
      { key: "date", header: t("cron.columns.date") },
      { key: "job", header: t("cron.columns.job") },
      { key: "status", header: t("cron.columns.status") },
      { key: "items_processed", header: t("cron.columns.itemsLong") },
      { key: "duration_ms", header: t("cron.columns.durationMs") },
      { key: "message", header: t("cron.columns.message") },
    ]);
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    downloadCsv(`cron-logs-${stamp}.csv`, csv);
  };

  // Page-local search across job + message.
  const filtered = entries.filter((e) => {
    if (!search.trim()) return true;
    const needle = search.trim().toLowerCase();
    return (e.job || "").toLowerCase().includes(needle) ||
           (e.message || "").toLowerCase().includes(needle);
  });

  // Status tally for the toolbar — based on the current page (server
  // already filters by status if a filter is set).
  const tally = entries.reduce(
    (acc, e) => {
      acc.total++;
      if (e.status === "success") acc.success++;
      else if (e.status === "error") acc.error++;
      else if (e.status === "warning") acc.warning++;
      return acc;
    },
    { total: 0, success: 0, error: 0, warning: 0 }
  );

  const lastRunIso = entries[0]?.date;
  const distinctJobs = new Set(entries.map((e) => e.job).filter(Boolean)).size;

  return (
    <Container>
      <PageHero
        icon={<ScheduleIcon sx={{ color: "#fff" }} />}
        eyebrow="BACKGROUND JOBS"
        title={t("cron.title") || "Cron Logs"}
        subtitle="Per-tick log of every cron job invocation: status, message, duration, items processed, and traceback on failure."
        showStatusDot
        statusLabel={lastRunIso ? `last run · ${formatRelative(lastRunIso)}` : "idle"}
        stats={[
          { glyph: "◆", color: "#fcd34d", label: `${total} total` },
          { glyph: "▣", color: "#7dd3fc", label: `${distinctJobs} job${distinctJobs === 1 ? "" : "s"} on screen` },
          ...(tally.error > 0 ? [{ glyph: "✕", color: "#fca5a5", label: `${tally.error} failed` }] : []),
        ]}
        actions={
          <Button
            size="small"
            variant="outlined"
            startIcon={running ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : <PlayArrowIcon />}
            disabled={running}
            onClick={handleRunNow}
            sx={{
              color: "#fff",
              borderColor: "rgba(255,255,255,0.4)",
              "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" },
              "&.Mui-disabled": { color: "rgba(255,255,255,0.4)", borderColor: "rgba(255,255,255,0.2)" },
            }}
          >
            {running ? t("cron.running") : t("cron.runNow")}
          </Button>
        }
      />

      <TileCard elevation={0} accent={ACCENT}>
        {/* Toolbar — search + status tally + filter dropdowns + actions */}
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
          <TextField
            size="small"
            placeholder="Search job or message…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ flex: 1, minWidth: 220 }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
                </InputAdornment>
              ),
              endAdornment: search ? (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => setSearch("")}>
                    <CloseIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : null,
            }}
          />

          {/* Status tally */}
          <Box sx={{ display: "flex", gap: 0.75 }}>
            <StatusSummary icon={CheckCircleIcon} count={tally.success} color="#10b981" label={`${tally.success} success`} />
            <StatusSummary icon={WarningIcon}     count={tally.warning} color="#f59e0b" label={`${tally.warning} warning`} />
            <StatusSummary icon={ErrorIcon}       count={tally.error}   color="#ef4444" label={`${tally.error} error`} />
          </Box>

          <TextField
            select
            size="small"
            label={t("cron.filterJob")}
            value={filterJob}
            onChange={(e) => { setFilterJob(e.target.value); setPage(0); }}
            sx={{ width: 160 }}
          >
            <MenuItem value="">{t("cron.filterAll")}</MenuItem>
            {JOBS.map((j) => (
              <MenuItem key={j} value={j}>
                <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>{j}</Box>
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label={t("cron.filterStatus")}
            value={filterStatus}
            onChange={(e) => { setFilterStatus(e.target.value); setPage(0); }}
            sx={{ width: 130 }}
          >
            <MenuItem value="">{t("cron.filterAll")}</MenuItem>
            <MenuItem value="success">{t("cron.filterSuccess")}</MenuItem>
            <MenuItem value="warning">{t("cron.filterWarning")}</MenuItem>
            <MenuItem value="error">{t("cron.filterError")}</MenuItem>
          </TextField>

          <Tooltip title={t("cron.exportCsv")}>
            <span>
              <IconButton
                size="small"
                onClick={exportCsv}
                disabled={entries.length === 0}
                sx={{
                  color: "text.secondary",
                  border: "1px solid rgba(15,23,42,0.12)",
                  borderRadius: 1.5,
                  "&:hover": { color: ACCENT, borderColor: ACCENT },
                }}
              >
                <FileDownloadIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title={t("cron.purge")}>
            <IconButton
              size="small"
              onClick={() => {
                if (window.confirm(t("cron.purgeConfirm"))) {
                  api.delete("/cron-logs", auth.user.token)
                    .then(() => { setPage(0); fetchEntries(); })
                    .catch(() => {});
                }
              }}
              sx={{
                color: "text.secondary",
                border: "1px solid rgba(15,23,42,0.12)",
                borderRadius: 1.5,
                "&:hover": { color: "#ef4444", borderColor: "#ef4444", backgroundColor: "rgba(239,68,68,0.06)" },
              }}
            >
              <DeleteSweepIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Table */}
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
              <TableCell sx={{ pl: 3, width: 40 }} />
              <TableCell>{t("cron.columns.date")}</TableCell>
              <TableCell>{t("cron.columns.job")}</TableCell>
              <TableCell>{t("cron.columns.status")}</TableCell>
              <TableCell>{t("cron.columns.message")}</TableCell>
              <TableCell align="center">{t("cron.columns.items")}</TableCell>
              <TableCell align="right" sx={{ pr: 3 }}>{t("cron.columns.duration")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 6 }}>
                  <Box
                    sx={{
                      display: "inline-flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 1.25,
                    }}
                  >
                    <Box
                      sx={{
                        width: 56,
                        height: 56,
                        borderRadius: "50%",
                        background: ACCENT_SOFT,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        animation: `${pulse} 3s ease-out infinite`,
                      }}
                    >
                      <ScheduleIcon sx={{ fontSize: 28, color: ACCENT }} />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {search
                        ? `No entries match "${search}".`
                        : t("cron.noEntries")}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((e) => {
                const isOpen = expandedId === e.id;
                const meta = STATUS_META[e.status] || { color: "#6b7280" };
                return (
                  <React.Fragment key={e.id}>
                    <TableRow
                      hover
                      sx={{
                        cursor: "pointer",
                        transition: "background-color 0.15s ease",
                        backgroundColor: isOpen ? `${meta.color}06` : undefined,
                      }}
                      onClick={() => setExpandedId(isOpen ? null : e.id)}
                    >
                      <TableCell sx={{ pl: 3, width: 40 }}>
                        <IconButton size="small" sx={{ color: meta.color }}>
                          {isOpen ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                        </IconButton>
                      </TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>
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
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.78rem",
                            fontWeight: 600,
                            color: "text.primary",
                          }}
                        >
                          {e.job}
                        </Box>
                      </TableCell>
                      <TableCell>
                        <StatusPill status={e.status} />
                      </TableCell>
                      <TableCell
                        sx={{
                          maxWidth: 380,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          color: "text.secondary",
                          fontSize: "0.85rem",
                        }}
                      >
                        {e.message || "—"}
                      </TableCell>
                      <TableCell align="center">
                        {(e.items_processed ?? 0) > 0 ? (
                          <Box
                            component="span"
                            sx={{
                              display: "inline-block",
                              minWidth: 28,
                              px: 1,
                              py: 0.25,
                              borderRadius: 0.75,
                              background: ACCENT_SOFT,
                              color: ACCENT,
                              fontFamily: FONT_MONO,
                              fontWeight: 700,
                              fontSize: "0.72rem",
                            }}
                          >
                            {e.items_processed}
                          </Box>
                        ) : (
                          <Box component="span" sx={{ color: "text.disabled" }}>—</Box>
                        )}
                      </TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          pr: 3,
                          fontFamily: FONT_MONO,
                          fontSize: "0.78rem",
                          color: e.duration_ms != null ? "text.primary" : "text.disabled",
                        }}
                      >
                        {formatDuration(e.duration_ms)}
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell
                        colSpan={7}
                        sx={{
                          p: 0,
                          borderBottom: isOpen ? undefined : "none",
                          backgroundColor: isOpen ? `${meta.color}04` : undefined,
                        }}
                      >
                        <Collapse in={isOpen}>
                          <Box
                            sx={{
                              p: 2.5,
                              display: "flex",
                              flexDirection: "column",
                              gap: 2,
                            }}
                          >
                            <LogBlock
                              label={t("cron.columns.message") || "Message"}
                              content={e.message || t("cron.noOutput")}
                              accent="#7dd3fc"
                            />
                            {e.details && (
                              <LogBlock
                                label={t("cron.details") || "Traceback"}
                                content={e.details}
                                accent="#fca5a5"
                              />
                            )}
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

        {totalPages > 1 && (
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              p: 2,
              gap: 1,
              borderTop: "1px solid rgba(15,23,42,0.06)",
            }}
          >
            <IconButton
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              size="small"
              sx={{ color: "text.secondary" }}
            >
              <ChevronLeftIcon />
            </IconButton>
            <Typography
              variant="body2"
              sx={{
                fontFamily: FONT_MONO,
                fontSize: "0.78rem",
                color: "text.secondary",
                minWidth: 90,
                textAlign: "center",
              }}
            >
              {t("cron.page", { page: page + 1, total: totalPages })}
            </Typography>
            <IconButton
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              size="small"
              sx={{ color: "text.secondary" }}
            >
              <ChevronRightIcon />
            </IconButton>
          </Box>
        )}
      </TileCard>
    </Container>
  );
}
