import React, { useState, useEffect, useMemo } from "react";
import {
  Box, Card, CircularProgress, IconButton, InputAdornment, MenuItem,
  styled, Switch, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Tooltip, Typography,
} from "@mui/material";
import ScheduleIcon from "@mui/icons-material/Schedule";
import RefreshIcon from "@mui/icons-material/Refresh";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import BoltIcon from "@mui/icons-material/Bolt";
import PauseCircleIcon from "@mui/icons-material/PauseCircle";
import { Link as RouterLink } from "react-router-dom";
import PageHero from "app/components/page/PageHero";
import ProjectTypeChip from "app/components/ProjectTypeChip";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Routines = scheduled automations that "run things". Emerald reads as
// "live / active". Distinct from cron-logs amber and audit indigo.
const ACCENT = "#10b981";
const ACCENT_SOFT = "rgba(16,185,129,0.10)";

// "Recently fired" threshold — anything inside this window gets a green
// pulsing dot in the table to show it's actively cycling. Tuned a bit
// generously since some routines run every few hours.
const RECENT_MS = 1000 * 60 * 60; // 1h

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

// Render minutes as "1h 30m", "45m", "2d", etc. Keeps the column tight
// without losing precision for both short (5 min poll) and long (daily)
// schedules.
function formatInterval(mins) {
  if (mins == null) return "—";
  if (mins < 60) return `${mins}m`;
  if (mins < 60 * 24) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }
  const d = Math.floor(mins / (60 * 24));
  const h = Math.floor((mins % (60 * 24)) / 60);
  return h === 0 ? `${d}d` : `${d}d ${h}h`;
}

// Bucket the interval into a colour band — short polls get a hot
// colour, long-running daily-style routines a cooler one. Helps an
// admin see at a glance whether they have any chatty schedules.
function intervalAccent(mins) {
  if (mins == null) return { color: "#6b7280", soft: "rgba(107,114,128,0.10)" };
  if (mins < 15)        return { color: "#ef4444", soft: "rgba(239,68,68,0.10)"  };  // <15m  red
  if (mins < 60)        return { color: "#f59e0b", soft: "rgba(245,158,11,0.10)" };  // <1h   amber
  if (mins < 60 * 24)   return { color: "#10b981", soft: "rgba(16,185,129,0.10)" };  // <1d   emerald
  return                       { color: "#0891b2", soft: "rgba(8,145,178,0.10)"  };  // ≥1d   cyan
}

const formatRelative = (iso) => {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

export default function Routines() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [routines, setRoutines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState(""); // "" | "enabled" | "disabled" | "recent" | "never"

  const fetchRoutines = () => {
    setLoading(true);
    api.get("/admin/routines", auth.user.token, { silent: true })
      .then((data) => setRoutines(data.routines || []))
      .catch(() => setRoutines([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("routines.title");
    fetchRoutines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const handleToggle = (r) => {
    const next = !r.enabled;
    setRoutines((cur) => cur.map((x) => (x.id === r.id ? { ...x, enabled: next } : x)));
    setPendingId(r.id);
    api.patch(`/admin/routines/${r.id}`, { enabled: next }, auth.user.token)
      .catch(() => {
        setRoutines((cur) => cur.map((x) => (x.id === r.id ? { ...x, enabled: !next } : x)));
      })
      .finally(() => setPendingId(null));
  };

  const isRecent = (iso) => {
    if (!iso) return false;
    return Date.now() - new Date(iso).getTime() < RECENT_MS;
  };

  // Tally based on the full set (toolbar gives the global pulse).
  const tally = useMemo(() => {
    const acc = { enabled: 0, disabled: 0, recent: 0, never: 0 };
    for (const r of routines) {
      if (r.enabled) acc.enabled++; else acc.disabled++;
      if (!r.last_run) acc.never++;
      else if (isRecent(r.last_run)) acc.recent++;
    }
    return acc;
  }, [routines]);

  const filtered = useMemo(() => {
    return routines.filter((r) => {
      if (search.trim()) {
        const needle = search.trim().toLowerCase();
        const hit =
          (r.name || "").toLowerCase().includes(needle) ||
          (r.project_name || "").toLowerCase().includes(needle) ||
          (r.project_type || "").toLowerCase().includes(needle);
        if (!hit) return false;
      }
      if (filterStatus === "enabled" && !r.enabled) return false;
      if (filterStatus === "disabled" && r.enabled) return false;
      if (filterStatus === "recent" && !isRecent(r.last_run)) return false;
      if (filterStatus === "never" && r.last_run) return false;
      return true;
    });
  }, [routines, search, filterStatus]);

  const distinctProjects = useMemo(
    () => new Set(routines.map((r) => r.project_id)).size,
    [routines]
  );

  return (
    <Container>
      <PageHero
        icon={<ScheduleIcon sx={{ color: "#fff" }} />}
        eyebrow="SCHEDULED ROUTINES"
        title={t("routines.title") || "Routines"}
        subtitle="Per-project automated triggers that fire on a schedule and run through the normal chat/question pipeline."
        showStatusDot
        statusLabel={tally.recent > 0 ? `${tally.recent} fired in the last hour` : "idle"}
        stats={[
          { glyph: "◆", color: "#a7f3d0", label: `${routines.length} routine${routines.length === 1 ? "" : "s"}` },
          { glyph: "▣", color: "#7dd3fc", label: `${distinctProjects} project${distinctProjects === 1 ? "" : "s"}` },
          { glyph: "✓", color: "#86efac", label: `${tally.enabled} enabled` },
          ...(tally.disabled > 0
            ? [{ glyph: "⏸", color: "#cbd5e1", label: `${tally.disabled} paused` }]
            : []),
        ]}
        actions={
          <Tooltip title={t("routines.refresh") || "Refresh"}>
            <span>
              <IconButton
                size="small"
                onClick={fetchRoutines}
                disabled={loading}
                sx={{
                  color: "#fff",
                  border: "1px solid rgba(255,255,255,0.4)",
                  borderRadius: 1.5,
                  "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" },
                  "&.Mui-disabled": { color: "rgba(255,255,255,0.4)", borderColor: "rgba(255,255,255,0.2)" },
                }}
              >
                {loading ? <CircularProgress size={16} sx={{ color: "#fff" }} /> : <RefreshIcon fontSize="small" />}
              </IconButton>
            </span>
          </Tooltip>
        }
      />

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
          <TextField
            size="small"
            placeholder="Search routine, project or type…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ flex: 1, minWidth: 240 }}
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

          <Box sx={{ display: "flex", gap: 0.75 }}>
            <StatusSummary icon={BoltIcon}         count={tally.enabled}  color="#10b981" label={`${tally.enabled} enabled`} />
            <StatusSummary icon={PauseCircleIcon}  count={tally.disabled} color="#94a3b8" label={`${tally.disabled} paused`} />
            <StatusSummary icon={RefreshIcon}      count={tally.recent}   color="#0891b2" label={`${tally.recent} fired in last hour`} />
            <StatusSummary icon={ScheduleIcon}     count={tally.never}    color="#f59e0b" label={`${tally.never} never run`} />
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
            <MenuItem value="enabled">Enabled</MenuItem>
            <MenuItem value="disabled">Paused</MenuItem>
            <MenuItem value="recent">Recently fired</MenuItem>
            <MenuItem value="never">Never run</MenuItem>
          </TextField>
        </Box>

        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
              <TableCell sx={{ pl: 3 }}>{t("routines.columns.project")}</TableCell>
              <TableCell>{t("routines.columns.name")}</TableCell>
              <TableCell align="center">{t("routines.columns.interval")}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{t("routines.columns.lastRun")}</TableCell>
              <TableCell align="center" sx={{ pr: 3 }}>{t("routines.columns.enabled")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 5 }}>
                  <CircularProgress size={24} sx={{ color: ACCENT }} />
                </TableCell>
              </TableRow>
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 6 }}>
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
                      <ScheduleIcon sx={{ fontSize: 28, color: ACCENT }} />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {search || filterStatus
                        ? "No routines match the current filters."
                        : t("routines.empty")}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((r) => {
                const intervalMeta = intervalAccent(r.schedule_minutes);
                const recent = isRecent(r.last_run);
                return (
                  <TableRow
                    key={r.id}
                    sx={{
                      "&:hover": { backgroundColor: "rgba(15,23,42,0.025)" },
                      transition: "background-color 0.15s ease",
                      opacity: r.enabled ? 1 : 0.65,
                    }}
                  >
                    {/* Project: type chip + name link + open icon */}
                    <TableCell sx={{ pl: 3, py: 1.25 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <ProjectTypeChip type={r.project_type} />
                        <RouterLink
                          to={`/project/${r.project_id}/edit`}
                          style={{ color: "inherit", textDecoration: "none" }}
                        >
                          <Box
                            component="span"
                            sx={{
                              fontWeight: 500,
                              fontSize: "0.85rem",
                              "&:hover": { color: ACCENT, textDecoration: "underline" },
                              transition: "color 0.15s ease",
                            }}
                          >
                            {r.project_name}
                          </Box>
                        </RouterLink>
                        <Tooltip title={t("routines.openProject") || "Open project"}>
                          <IconButton
                            component={RouterLink}
                            to={`/project/${r.project_id}/edit`}
                            size="small"
                            sx={{ color: "text.disabled", "&:hover": { color: ACCENT } }}
                          >
                            <OpenInNewIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>

                    <TableCell>
                      <Box
                        component="span"
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.82rem",
                          fontWeight: 600,
                          color: "text.primary",
                        }}
                      >
                        {r.name}
                      </Box>
                    </TableCell>

                    {/* Interval — colour-banded pill */}
                    <TableCell align="center">
                      <Box
                        component="span"
                        sx={{
                          display: "inline-block",
                          px: 1,
                          py: 0.4,
                          borderRadius: 0.75,
                          fontFamily: FONT_MONO,
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          color: intervalMeta.color,
                          backgroundColor: intervalMeta.soft,
                          border: `1px solid ${intervalMeta.color}33`,
                          minWidth: 56,
                        }}
                      >
                        {formatInterval(r.schedule_minutes)}
                      </Box>
                    </TableCell>

                    {/* Last run — ISO + relative + recent dot */}
                    <TableCell sx={{ whiteSpace: "nowrap", py: 1.25 }}>
                      {r.last_run ? (
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                          {recent && (
                            <Tooltip title="Fired in the last hour">
                              <Box
                                sx={{
                                  width: 8,
                                  height: 8,
                                  borderRadius: "50%",
                                  background: ACCENT,
                                  boxShadow: `0 0 8px ${ACCENT}`,
                                  animation: `${pulse} 2s ease-out infinite`,
                                  flexShrink: 0,
                                }}
                              />
                            </Tooltip>
                          )}
                          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.1 }}>
                            <Box
                              component="span"
                              sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", color: "text.primary" }}
                            >
                              {new Date(r.last_run).toLocaleString()}
                            </Box>
                            <Box
                              component="span"
                              sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: "text.disabled" }}
                            >
                              {formatRelative(r.last_run)}
                            </Box>
                          </Box>
                        </Box>
                      ) : (
                        <Box
                          component="span"
                          sx={{
                            display: "inline-block",
                            px: 1,
                            py: 0.3,
                            borderRadius: 0.75,
                            fontFamily: FONT_MONO,
                            fontSize: "0.7rem",
                            fontWeight: 600,
                            color: "#f59e0b",
                            backgroundColor: "rgba(245,158,11,0.10)",
                            border: "1px solid rgba(245,158,11,0.33)",
                          }}
                        >
                          NEVER RUN
                        </Box>
                      )}
                    </TableCell>

                    {/* Enabled switch */}
                    <TableCell align="center" sx={{ pr: 3 }}>
                      <Switch
                        checked={r.enabled}
                        disabled={pendingId === r.id}
                        onChange={() => handleToggle(r)}
                        size="small"
                        sx={{
                          "& .MuiSwitch-switchBase.Mui-checked": {
                            color: ACCENT,
                            "&:hover": {
                              backgroundColor: `${ACCENT}14`,
                            },
                          },
                          "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": {
                            backgroundColor: ACCENT,
                          },
                        }}
                      />
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TileCard>
    </Container>
  );
}
