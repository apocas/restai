import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, CircularProgress, IconButton, InputAdornment,
  MenuItem, styled, Table, TableBody, TableCell, TableHead, TableRow,
  TablePagination, TableSortLabel, TextField, Tooltip, Typography,
} from "@mui/material";
import { History, FileDownload, Search, Close, CheckCircle, Error as ErrorIcon, Warning, Info as InfoIcon } from "@mui/icons-material";
import sha256 from "crypto-js/sha256";
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

// Audit = formal record book / trail. Indigo reads as "official ledger".
// Distinct from cron=amber, proxy=cyan, classifier=violet.
const ACCENT = "#6366f1";
const ACCENT_SOFT = "rgba(99,102,241,0.10)";

// Per-action verb meta — colour-codes the verb pill so the pattern of
// changes is scannable at a glance.
const ACTION_META = {
  POST:    { color: "#10b981", soft: "rgba(16,185,129,0.12)" },  // emerald — create
  PATCH:   { color: "#0891b2", soft: "rgba(8,145,178,0.12)"  },  // cyan    — update
  PUT:     { color: "#0891b2", soft: "rgba(8,145,178,0.12)"  },
  DELETE:  { color: "#ef4444", soft: "rgba(239,68,68,0.12)"  },  // red     — destroy
  GET:     { color: "#6b7280", soft: "rgba(107,114,128,0.12)"},  // grey    — read
};

// Per-status-class meta — 2xx green, 3xx cyan, 4xx amber, 5xx red.
function statusClassFor(code) {
  if (!code) return { key: "unknown", color: "#6b7280", icon: InfoIcon, label: "—" };
  if (code < 300) return { key: "success", color: "#10b981", icon: CheckCircle, label: "2xx" };
  if (code < 400) return { key: "redirect", color: "#0891b2", icon: InfoIcon, label: "3xx" };
  if (code < 500) return { key: "client", color: "#f59e0b", icon: Warning, label: "4xx" };
  return { key: "server", color: "#ef4444", icon: ErrorIcon, label: "5xx" };
}

// ── Tile card with indigo accent rail + hover sweep — same vocabulary
// as the cron-logs / proxy / classifier pages.
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

function VerbPill({ action }) {
  const meta = ACTION_META[action] || { color: "#6b7280", soft: "rgba(107,114,128,0.12)" };
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 1,
        py: 0.35,
        borderRadius: 0.75,
        fontFamily: FONT_MONO,
        fontSize: "0.68rem",
        fontWeight: 700,
        letterSpacing: "0.06em",
        color: meta.color,
        backgroundColor: meta.soft,
        border: `1px solid ${meta.color}33`,
        minWidth: 56,
        textAlign: "center",
      }}
    >
      {action}
    </Box>
  );
}

function StatusBadge({ code }) {
  const meta = statusClassFor(code);
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.65,
        px: 1,
        py: 0.4,
        borderRadius: 1,
        backgroundColor: `${meta.color}10`,
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
          fontSize: "0.72rem",
          fontWeight: 700,
          color: meta.color,
        }}
      >
        {code ?? "—"}
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

const formatRelative = (iso) => {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
};

const FETCH_LIMIT = 1000;

export default function AuditLog() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState("");
  const [filterAction, setFilterAction] = useState("");
  const [filterStatusClass, setFilterStatusClass] = useState("");
  const [sortKey, setSortKey] = useState("date");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("audit.title");
    setLoading(true);
    api.get(`/audit?start=0&end=${FETCH_LIMIT}`, auth.user.token, { silent: true })
      .then((data) => {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  // ── Local search / filter / sort over the fetched slice.
  const processed = useMemo(() => {
    let out = entries;
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      out = out.filter((e) =>
        (e.username || "").toLowerCase().includes(needle) ||
        (e.action || "").toLowerCase().includes(needle) ||
        (e.resource || "").toLowerCase().includes(needle) ||
        String(e.status_code || "").includes(needle)
      );
    }
    if (filterAction) out = out.filter((e) => e.action === filterAction);
    if (filterStatusClass) {
      out = out.filter((e) => statusClassFor(e.status_code).key === filterStatusClass);
    }

    const cmp = (a, b) => {
      let av, bv;
      switch (sortKey) {
        case "date":     av = a.date || ""; bv = b.date || ""; break;
        case "username": av = a.username || ""; bv = b.username || ""; break;
        case "action":   av = a.action || ""; bv = b.action || ""; break;
        case "resource": av = a.resource || ""; bv = b.resource || ""; break;
        case "status":   av = a.status_code || 0; bv = b.status_code || 0; break;
        default:         return 0;
      }
      if (typeof av === "number") return sortDir === "asc" ? av - bv : bv - av;
      return sortDir === "asc"
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    };
    return [...out].sort(cmp);
  }, [entries, search, filterAction, filterStatusClass, sortKey, sortDir]);

  const paged = useMemo(
    () => processed.slice(page * rowsPerPage, (page + 1) * rowsPerPage),
    [processed, page, rowsPerPage]
  );

  // Tally for the toolbar — based on the *filtered* set so the badges
  // reflect what the admin is currently looking at.
  const tally = useMemo(() => {
    const acc = { success: 0, redirect: 0, client: 0, server: 0 };
    for (const e of processed) {
      const k = statusClassFor(e.status_code).key;
      if (acc[k] != null) acc[k]++;
    }
    return acc;
  }, [processed]);

  const distinctActors = useMemo(
    () => new Set(processed.map((e) => e.username).filter(Boolean)).size,
    [processed]
  );

  const lastIso = entries[0]?.date;

  const handleSort = (key) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir(key === "date" ? "desc" : "asc"); }
  };

  const exportCsv = () => {
    if (processed.length === 0) return;
    const csv = toCsv(processed, [
      { key: "date", header: t("audit.columns.date") },
      { key: "username", header: t("audit.columns.user") },
      { key: "action", header: t("audit.columns.action") },
      { key: "resource", header: t("audit.columns.resource") },
      { key: "status_code", header: t("audit.columns.status") },
    ]);
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    downloadCsv(`audit-log-${stamp}.csv`, csv);
  };

  // Reset paging whenever filters change so we don't land on an empty page.
  useEffect(() => { setPage(0); }, [search, filterAction, filterStatusClass]);

  return (
    <Container>
      <PageHero
        icon={<History sx={{ color: "#fff" }} />}
        eyebrow="AUDIT TRAIL"
        title={t("audit.title") || "Audit Log"}
        subtitle="Privileged operations across the platform — every write is logged with actor, action and target."
        showStatusDot
        statusLabel={lastIso ? `last event · ${formatRelative(lastIso)}` : "no activity"}
        stats={[
          { glyph: "◆", color: "#a5b4fc", label: `${total} total events` },
          { glyph: "★", color: "#7dd3fc", label: `${distinctActors} distinct actor${distinctActors === 1 ? "" : "s"}` },
          ...(tally.client + tally.server > 0
            ? [{ glyph: "⚠", color: "#fcd34d", label: `${tally.client + tally.server} failed` }]
            : []),
        ]}
        actions={
          <Button
            size="small"
            variant="outlined"
            startIcon={<FileDownload />}
            disabled={processed.length === 0}
            onClick={exportCsv}
            sx={{
              color: "#fff",
              borderColor: "rgba(255,255,255,0.4)",
              "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" },
              "&.Mui-disabled": { color: "rgba(255,255,255,0.4)", borderColor: "rgba(255,255,255,0.2)" },
            }}
          >
            {t("audit.exportCsv")}
          </Button>
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
            placeholder="Search actor, action or resource…"
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

          {/* Status-class tally */}
          <Box sx={{ display: "flex", gap: 0.75 }}>
            <StatusSummary icon={CheckCircle} count={tally.success}  color="#10b981" label={`${tally.success} 2xx`} />
            <StatusSummary icon={InfoIcon}    count={tally.redirect} color="#0891b2" label={`${tally.redirect} 3xx`} />
            <StatusSummary icon={Warning}     count={tally.client}   color="#f59e0b" label={`${tally.client} 4xx`} />
            <StatusSummary icon={ErrorIcon}   count={tally.server}   color="#ef4444" label={`${tally.server} 5xx`} />
          </Box>

          <TextField
            select
            size="small"
            label={t("audit.filterAction")}
            value={filterAction}
            onChange={(e) => setFilterAction(e.target.value)}
            sx={{ width: 140 }}
          >
            <MenuItem value="">All</MenuItem>
            {["POST", "PATCH", "PUT", "DELETE"].map((a) => (
              <MenuItem key={a} value={a}>
                <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", fontWeight: 600 }}>{a}</Box>
              </MenuItem>
            ))}
          </TextField>
          <TextField
            select
            size="small"
            label={t("audit.columns.status")}
            value={filterStatusClass}
            onChange={(e) => setFilterStatusClass(e.target.value)}
            sx={{ width: 130 }}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="success">2xx success</MenuItem>
            <MenuItem value="redirect">3xx redirect</MenuItem>
            <MenuItem value="client">4xx client</MenuItem>
            <MenuItem value="server">5xx server</MenuItem>
          </TextField>
        </Box>

        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
              <TableCell sx={{ pl: 3 }}>
                <TableSortLabel
                  active={sortKey === "date"}
                  direction={sortKey === "date" ? sortDir : "asc"}
                  onClick={() => handleSort("date")}
                >{t("audit.columns.date")}</TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortKey === "username"}
                  direction={sortKey === "username" ? sortDir : "asc"}
                  onClick={() => handleSort("username")}
                >{t("audit.columns.user")}</TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortKey === "action"}
                  direction={sortKey === "action" ? sortDir : "asc"}
                  onClick={() => handleSort("action")}
                >{t("audit.columns.action")}</TableSortLabel>
              </TableCell>
              <TableCell>
                <TableSortLabel
                  active={sortKey === "resource"}
                  direction={sortKey === "resource" ? sortDir : "asc"}
                  onClick={() => handleSort("resource")}
                >{t("audit.columns.resource")}</TableSortLabel>
              </TableCell>
              <TableCell align="center" sx={{ pr: 3 }}>
                <TableSortLabel
                  active={sortKey === "status"}
                  direction={sortKey === "status" ? sortDir : "asc"}
                  onClick={() => handleSort("status")}
                >{t("audit.columns.status")}</TableSortLabel>
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} align="center" sx={{ py: 5 }}>
                  <CircularProgress size={24} sx={{ color: ACCENT }} />
                </TableCell>
              </TableRow>
            ) : paged.length === 0 ? (
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
                      <History sx={{ fontSize: 28, color: ACCENT }} />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {search || filterAction || filterStatusClass
                        ? "No events match the current filters."
                        : t("audit.noEntries")}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              paged.map((e) => {
                const sMeta = statusClassFor(e.status_code);
                return (
                  <TableRow
                    key={e.id}
                    sx={{
                      "&:hover": { backgroundColor: "rgba(15,23,42,0.025)" },
                      transition: "background-color 0.15s ease",
                    }}
                  >
                    {/* Date — ISO + relative below */}
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

                    {/* Actor — gravatar + username */}
                    <TableCell>
                      {e.username ? (
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                          <Box
                            component="img"
                            src={`https://www.gravatar.com/avatar/${sha256(e.username).toString()}?d=identicon&s=48`}
                            alt={e.username}
                            sx={{
                              width: 24, height: 24,
                              borderRadius: "50%",
                              border: "1px solid rgba(15,23,42,0.08)",
                              backgroundColor: "rgba(15,23,42,0.04)",
                            }}
                          />
                          <Box
                            component="span"
                            sx={{ fontWeight: 500, fontSize: "0.85rem", color: "text.primary" }}
                          >
                            {e.username}
                          </Box>
                        </Box>
                      ) : (
                        <Box component="span" sx={{ color: "text.disabled" }}>
                          system
                        </Box>
                      )}
                    </TableCell>

                    <TableCell>
                      <VerbPill action={e.action} />
                    </TableCell>

                    {/* Resource — mono path with tooltip */}
                    <TableCell sx={{ maxWidth: 380 }}>
                      <Tooltip title={e.resource || ""} placement="top-start" arrow>
                        <Box
                          component="code"
                          sx={{
                            display: "inline-block",
                            maxWidth: "100%",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            verticalAlign: "middle",
                            fontFamily: FONT_MONO,
                            fontSize: "0.76rem",
                            color: "text.secondary",
                            backgroundColor: "rgba(15,23,42,0.04)",
                            px: 0.75,
                            py: 0.25,
                            borderRadius: 0.75,
                          }}
                        >
                          {e.resource}
                        </Box>
                      </Tooltip>
                    </TableCell>

                    <TableCell align="center" sx={{ pr: 3 }}>
                      <Tooltip title={sMeta.label} arrow>
                        <Box sx={{ display: "inline-block" }}>
                          <StatusBadge code={e.status_code} />
                        </Box>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        {processed.length > rowsPerPage && (
          <TablePagination
            component="div"
            count={processed.length}
            page={page}
            onPageChange={(_, p) => setPage(p)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value, 10)); setPage(0); }}
            rowsPerPageOptions={[10, 25, 50, 100]}
            sx={{
              borderTop: "1px solid rgba(15,23,42,0.06)",
              "& .MuiTablePagination-toolbar": { minHeight: 48 },
            }}
          />
        )}
      </TileCard>

      {total > entries.length && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 1.5, ml: 1, fontFamily: FONT_MONO }}
        >
          Showing the {entries.length} most recent of {total} total events.
        </Typography>
      )}
    </Container>
  );
}
