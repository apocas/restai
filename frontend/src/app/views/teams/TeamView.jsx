import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, CircularProgress, Grid, IconButton,
  LinearProgress, Tab, Tabs, Tooltip, Typography, styled,
} from "@mui/material";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import {
  Person, Settings, Delete, Group, Code, Psychology,
  AccountBalanceWallet, Receipt, AllInclusive, Image, Speaker,
  Star, Workspaces, GroupsOutlined,
} from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import ReactJson from "@microlink/react-json-view";
import api from "app/utils/api";
import PageHero from "app/components/page/PageHero";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Same fuchsia family as the Teams list so the pages read as siblings.
const ACCENT = "#c026d3";        // fuchsia-600
const ACCENT_DARK = "#a21caf";   // fuchsia-700
const ACCENT_SOFT = "rgba(192,38,211,0.10)";

// Per-section accents — used for the per-list cards inside tabs so each
// resource type stays visually distinct.
const SECTION = {
  members:    { c: "#7c3aed", soft: "rgba(124,58,237,0.10)" },
  admins:     { c: "#dc2626", soft: "rgba(220,38,38,0.10)"  },
  projects:   { c: ACCENT,    soft: ACCENT_SOFT             },
  llms:       { c: "#1d4ed8", soft: "rgba(29,78,216,0.10)"  },
  embeddings: { c: "#0d9488", soft: "rgba(13,148,136,0.10)" },
  imageGen:   { c: "#f43f5e", soft: "rgba(244,63,94,0.10)"  },
  audioGen:   { c: "#f59e0b", soft: "rgba(245,158,11,0.10)" },
};

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

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
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
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

function TileHeader({ icon, title, subtitle, accent = ACCENT, count, action }) {
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
          width: 36, height: 36, flexShrink: 0,
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
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: accent,
            lineHeight: 1,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.4 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {count != null && (
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            px: 1, py: 0.4,
            borderRadius: 0.75,
            backgroundColor: `${accent}10`,
            border: `1px solid ${accent}33`,
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            fontWeight: 700,
            color: accent,
          }}
        >
          {count}
        </Box>
      )}
      {action}
    </Box>
  );
}

// Stat tile shared with the Teams list page — in-page metric strip.
const StatCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  padding: 16,
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
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
}));

function StatTile({ icon, label, value, accent = ACCENT, sub }) {
  return (
    <StatCard accent={accent} elevation={0}>
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25 }}>
        <Box
          sx={{
            width: 38, height: 38, flexShrink: 0,
            borderRadius: 1.5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${accent}25, ${accent}12)`,
            border: `1px solid ${accent}33`,
            color: accent,
            "& svg": { fontSize: 20 },
          }}
        >
          {icon}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.6rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
              color: "text.secondary",
              lineHeight: 1,
            }}
          >
            {label}
          </Box>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "1.4rem",
              fontWeight: 800,
              color: accent,
              lineHeight: 1.1,
              mt: 0.4,
            }}
          >
            {value}
          </Box>
          {sub && (
            <Box
              component="span"
              sx={{
                display: "block",
                fontFamily: FONT_MONO,
                fontSize: "0.62rem",
                color: "text.disabled",
                mt: 0.3,
              }}
            >
              {sub}
            </Box>
          )}
        </Box>
      </Box>
    </StatCard>
  );
}

// Initial-letter avatar with deterministic per-name hue (mirrors Teams list).
const hueFor = (s) => {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

function UserAvatar({ name, size = 32, isAdmin = false }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase();
  const h = hueFor(name || "?");
  // Bias admins toward warm reds, members toward purple/fuchsia so the
  // role is readable from the avatar alone.
  const baseHue = isAdmin ? (340 + (h % 30)) : (260 + (h % 70));
  return (
    <Box
      sx={{
        width: size, height: size, flexShrink: 0,
        borderRadius: 1.25,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: FONT_MONO,
        fontWeight: 800,
        fontSize: size > 32 ? "1.05rem" : "0.85rem",
        background: `linear-gradient(135deg, hsl(${baseHue}, 75%, 52%) 0%, hsl(${(baseHue + 30) % 360}, 75%, 42%) 100%)`,
        boxShadow: `0 3px 8px hsla(${baseHue}, 75%, 50%, 0.35)`,
        textShadow: "0 1px 2px rgba(0,0,0,0.18)",
      }}
    >
      {initial}
    </Box>
  );
}

// Generic resource row used by every per-tab list (members, projects,
// LLMs, embeddings, image/audio gen). Optional click + remove.
function ResourceRow({ avatar, primary, secondary, accent, onClick, onRemove, removeLabel }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        px: 1.25, py: 1.25,
        borderRadius: 1.5,
        cursor: onClick ? "pointer" : "default",
        transition: "background-color 0.15s ease, border-color 0.15s ease",
        border: "1px solid transparent",
        "&:hover": onClick
          ? { backgroundColor: `${accent}08`, borderColor: `${accent}33` }
          : { backgroundColor: "rgba(15,23,42,0.025)" },
      }}
    >
      {avatar}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box
          component="span"
          sx={{
            display: "block",
            fontWeight: 600,
            fontSize: "0.88rem",
            color: "text.primary",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            lineHeight: 1.2,
          }}
        >
          {primary}
        </Box>
        {secondary && (
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.66rem",
              color: "text.disabled",
              letterSpacing: "0.04em",
              mt: 0.15,
            }}
          >
            {secondary}
          </Box>
        )}
      </Box>
      {onRemove && (
        <Tooltip title={removeLabel} arrow>
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); onRemove(); }}
            sx={{
              color: "text.disabled",
              "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.08)" },
            }}
          >
            <Delete fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  );
}

function IconWell({ icon, accent }) {
  return (
    <Box
      sx={{
        width: 32, height: 32, flexShrink: 0,
        borderRadius: 1.25,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: `${accent}15`,
        border: `1px solid ${accent}33`,
        color: accent,
        "& svg": { fontSize: 16 },
      }}
    >
      {icon}
    </Box>
  );
}

function EmptyState({ icon: Icon, label, accent }) {
  return (
    <Box
      sx={{
        py: 4,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 1,
      }}
    >
      <Box
        sx={{
          width: 44, height: 44,
          borderRadius: "50%",
          background: `${accent}10`,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          animation: `${pulse} 3s ease-out infinite`,
        }}
      >
        <Icon sx={{ fontSize: 20, color: accent }} />
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
        {label}
      </Typography>
    </Box>
  );
}

function TabPanel({ children, value, index }) {
  if (value !== index) return null;
  return <Box sx={{ pt: 2 }}>{children}</Box>;
}

export default function TeamView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [team, setTeam] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);

  const [transactions, setTransactions] = useState([]);
  const [txPage, setTxPage] = useState(0);
  const [txRows, setTxRows] = useState(100);
  const [txCount, setTxCount] = useState(0);
  const [txLog, setTxLog] = useState({});
  const [txRowsExpanded, setTxRowsExpanded] = useState([]);

  const isTeamAdmin = team?.admins?.some((a) => a.id === user.id) || user.is_admin;

  const fetchTeam = async () => {
    setLoading(true);
    try {
      const data = await api.get(`/teams/${id}`, user.token);
      setTeam(data);
    } catch (e) {} finally { setLoading(false); }
  };

  useEffect(() => { fetchTeam(); /* eslint-disable-next-line */ }, [id]);

  useEffect(() => {
    if (team) document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - Team: ${team.name}`;
  }, [team]);

  const fetchTransactions = async () => {
    try {
      const data = await api.get(`/teams/${id}/transactions?start=${txPage * txRows}&end=${txPage * txRows + txRows}`, user.token);
      if (data.transactions) {
        setTransactions(data.transactions);
        setTxCount(data.total);
      }
    } catch (e) {}
  };

  useEffect(() => {
    if (tabValue === 3 && team) fetchTransactions();
    // eslint-disable-next-line
  }, [tabValue, team, txPage, txRows]);

  const handleEditTeam = () => navigate(`/team/${id}/edit`);

  const removeUser = async (username) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: username }))) return;
    try { await api.delete(`/teams/${id}/users/${username}`, user.token); toast.success(t("teams.view.removed", { name: username })); fetchTeam(); } catch (e) {}
  };
  const removeAdmin = async (username) => {
    if (!window.confirm(t("teams.view.confirmRemoveAdmin", { name: username }))) return;
    try { await api.delete(`/teams/${id}/admins/${username}`, user.token); toast.success(t("teams.view.adminRemoved", { name: username })); fetchTeam(); } catch (e) {}
  };
  const removeProject = async (pid) => {
    if (!window.confirm(t("teams.view.confirmRemoveProject"))) return;
    try { await api.delete(`/teams/${id}/projects/${pid}`, user.token); toast.success(t("teams.view.projectRemoved")); fetchTeam(); } catch (e) {}
  };
  const removeLLM = async (llm) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: llm.name }))) return;
    try { await api.delete(`/teams/${id}/llms/${llm.id}`, user.token); toast.success(t("teams.view.removed", { name: llm.name })); fetchTeam(); } catch (e) {}
  };
  const removeEmbedding = async (em) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: em.name }))) return;
    try { await api.delete(`/teams/${id}/embeddings/${em.id}`, user.token); toast.success(t("teams.view.removed", { name: em.name })); fetchTeam(); } catch (e) {}
  };
  const removeImageGen = async (n) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: n }))) return;
    try { await api.delete(`/teams/${id}/image_generators/${n}`, user.token); toast.success(t("teams.view.removed", { name: n })); fetchTeam(); } catch (e) {}
  };
  const removeAudioGen = async (n) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: n }))) return;
    try { await api.delete(`/teams/${id}/audio_generators/${n}`, user.token); toast.success(t("teams.view.removed", { name: n })); fetchTeam(); } catch (e) {}
  };

  const counts = useMemo(() => team ? {
    users:      (team.users        || []).length,
    admins:     (team.admins       || []).length,
    projects:   (team.projects     || []).length,
    llms:       (team.llms         || []).length,
    embeddings: (team.embeddings   || []).length,
    imageGen:   (team.image_generators || []).length,
    audioGen:   (team.audio_generators || []).length,
  } : {}, [team]);

  // Loading splash with pulsing fuchsia halo.
  if (loading) {
    return (
      <Container>
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 12, gap: 2 }}>
          <Box
            sx={{
              width: 64, height: 64,
              borderRadius: "50%",
              background: ACCENT_SOFT,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              animation: `${pulse} 2s ease-out infinite`,
            }}
          >
            <CircularProgress size={28} sx={{ color: ACCENT }} />
          </Box>
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.7rem",
              color: "text.secondary",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {t("teams.view.loading")}
          </Box>
        </Box>
      </Container>
    );
  }

  if (!team) {
    return (
      <Container>
        <PageHero
          icon={<GroupsOutlined sx={{ color: "#fff" }} />}
          eyebrow={`TEAM/${String(id).padStart(4, "0")}`}
          title={t("teams.view.notFoundTitle")}
          subtitle={t("teams.view.notFound")}
          compact
        />
      </Container>
    );
  }

  const hasBudget = team.budget >= 0;
  const spent = team.spending ?? 0;
  const budget = team.budget;
  const pct = hasBudget && budget > 0 ? Math.min((spent / budget) * 100, 100) : 0;
  const barColor = pct > 90 ? "#dc2626" : pct > 70 ? "#f59e0b" : ACCENT;

  return (
    <Container>
      <PageHero
        icon={<GroupsOutlined sx={{ color: "#fff" }} />}
        eyebrow={`TEAM/${String(team.id).padStart(4, "0")}`}
        title={team.name}
        subtitle={team.description || t("teams.view.noDescription")}
        stats={[
          { glyph: "◆", color: "#f0abfc", label: `${counts.users} member${counts.users === 1 ? "" : "s"}` },
          { glyph: "★", color: "#fca5a5", label: `${counts.admins} admin${counts.admins === 1 ? "" : "s"}` },
          { glyph: "⌬", color: "#fcd34d", label: `${counts.projects} project${counts.projects === 1 ? "" : "s"}` },
          ...(hasBudget
            ? [{ glyph: "$", color: pct > 90 ? "#fca5a5" : "#a7f3d0", label: `$${spent.toFixed(2)} / $${budget.toFixed(2)}` }]
            : [{ glyph: "∞", color: "#94a3b8", label: t("teams.view.unlimited") }]),
        ]}
        actions={
          isTeamAdmin && (
            <Button
              variant="contained"
              startIcon={<Settings />}
              onClick={handleEditTeam}
              sx={{
                textTransform: "none",
                fontWeight: 700,
                background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                boxShadow: `0 4px 14px ${ACCENT}66`,
                "&:hover": {
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #86198f 100%)`,
                  boxShadow: `0 6px 18px ${ACCENT}88`,
                },
              }}
            >
              {t("teams.view.edit")}
            </Button>
          )
        }
        compact
      />

      {/* Metric strip */}
      <Grid container spacing={2} sx={{ mt: 1, mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatTile icon={<Group />}      label={t("teams.edit.members")}    value={counts.users}    accent={SECTION.members.c} sub={`${counts.admins} admin${counts.admins === 1 ? "" : "s"}`} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile icon={<Workspaces />} label={t("teams.edit.tabs.projects")} value={counts.projects} accent={SECTION.projects.c} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile icon={<Psychology />} label="LLM / Embedding" value={`${counts.llms} / ${counts.embeddings}`} accent={SECTION.llms.c} sub={`${counts.imageGen} img · ${counts.audioGen} audio`} />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={hasBudget ? <AccountBalanceWallet /> : <AllInclusive />}
            label={hasBudget ? t("teams.view.spent") : t("teams.view.unlimited")}
            value={hasBudget ? `$${spent.toFixed(2)}` : "∞"}
            accent={hasBudget ? barColor : "#64748b"}
            sub={hasBudget ? `of $${budget.toFixed(2)}` : "no cap"}
          />
        </Grid>
      </Grid>

      {/* Budget progress (only when capped) */}
      {hasBudget && (
        <TileCard elevation={0} accent={barColor} sx={{ mb: 2 }}>
          <Box sx={{ p: 2 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                <AccountBalanceWallet sx={{ fontSize: 16, color: barColor }} />
                <Box
                  component="span"
                  sx={{
                    fontFamily: FONT_MONO,
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    color: barColor,
                  }}
                >
                  {pct.toFixed(0)}% used
                </Box>
              </Box>
              <Box
                component="span"
                sx={{
                  fontFamily: FONT_MONO,
                  fontSize: "0.78rem",
                  fontWeight: 700,
                  color: barColor,
                }}
              >
                ${(team.remaining ?? 0).toFixed(2)} {t("teams.view.left")}
              </Box>
            </Box>
            <LinearProgress
              variant="determinate"
              value={pct}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: "rgba(15,23,42,0.06)",
                "& .MuiLinearProgress-bar": {
                  background: `linear-gradient(90deg, ${barColor}88, ${barColor})`,
                  borderRadius: 4,
                },
              }}
            />
          </Box>
        </TileCard>
      )}

      {/* Tabs in their own card */}
      <TileCard elevation={0} accent={ACCENT}>
        <Box sx={{ borderBottom: "1px solid rgba(15,23,42,0.06)", px: 1.5 }}>
          <Tabs
            value={tabValue}
            onChange={(_, v) => setTabValue(v)}
            TabIndicatorProps={{ sx: { background: `linear-gradient(90deg, ${ACCENT}, ${ACCENT_DARK})`, height: 3, borderRadius: 2 } }}
            sx={{
              minHeight: 48,
              "& .MuiTab-root": {
                textTransform: "none",
                fontWeight: 700,
                fontSize: "0.85rem",
                color: "text.secondary",
                minHeight: 48,
                "&.Mui-selected": { color: ACCENT },
              },
            }}
          >
            <Tab label={t("teams.edit.tabs.users")}    icon={<Group />}     iconPosition="start" />
            <Tab label={t("teams.edit.tabs.projects")} icon={<Code />}      iconPosition="start" />
            <Tab label={t("teams.edit.tabs.models")}   icon={<Psychology />} iconPosition="start" />
            {isTeamAdmin && (
              <Tab label={t("teams.view.tabs.transactions")} icon={<Receipt />} iconPosition="start" />
            )}
          </Tabs>
        </Box>

        {/* USERS / ADMINS */}
        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={2} sx={{ p: 2 }}>
            <Grid item xs={12} md={6}>
              <TileCard elevation={0} accent={SECTION.members.c}>
                <TileHeader
                  icon={<Group />}
                  title={t("teams.edit.members")}
                  subtitle={t("teams.view.membersSubtitle") || "Read + write access via roles"}
                  accent={SECTION.members.c}
                  count={counts.users}
                />
                <Box sx={{ p: 1.25 }}>
                  {(team.users || []).length === 0
                    ? <EmptyState icon={Person} label={t("teams.view.noMembers")} accent={SECTION.members.c} />
                    : team.users.map((m) => (
                      <ResourceRow
                        key={m.id}
                        avatar={<UserAvatar name={m.username} />}
                        primary={m.username}
                        secondary={m.id === user.id ? t("teams.view.you") : `USER/${String(m.id).padStart(4, "0")}`}
                        accent={SECTION.members.c}
                        onRemove={isTeamAdmin ? () => removeUser(m.username) : null}
                        removeLabel={t("teams.view.removeUser")}
                      />
                    ))}
                </Box>
              </TileCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <TileCard elevation={0} accent={SECTION.admins.c}>
                <TileHeader
                  icon={<Star />}
                  title={t("teams.edit.admins")}
                  subtitle={t("teams.view.adminsSubtitle") || "Can manage members & resources"}
                  accent={SECTION.admins.c}
                  count={counts.admins}
                />
                <Box sx={{ p: 1.25 }}>
                  {(team.admins || []).length === 0
                    ? <EmptyState icon={Star} label={t("teams.view.noAdmins")} accent={SECTION.admins.c} />
                    : team.admins.map((a) => (
                      <ResourceRow
                        key={a.id}
                        avatar={<UserAvatar name={a.username} isAdmin />}
                        primary={a.username}
                        secondary={a.id === user.id ? t("teams.view.you") : `USER/${String(a.id).padStart(4, "0")}`}
                        accent={SECTION.admins.c}
                        onRemove={isTeamAdmin ? () => removeAdmin(a.username) : null}
                        removeLabel={t("teams.view.removeAdmin")}
                      />
                    ))}
                </Box>
              </TileCard>
            </Grid>
          </Grid>
        </TabPanel>

        {/* PROJECTS */}
        <TabPanel value={tabValue} index={1}>
          <Box sx={{ p: 2 }}>
            <TileCard elevation={0} accent={SECTION.projects.c}>
              <TileHeader
                icon={<Workspaces />}
                title={t("teams.edit.projectsHeading")}
                subtitle={t("teams.view.projectsSubtitle") || "Click any project to open its info page"}
                accent={SECTION.projects.c}
                count={counts.projects}
              />
              <Box sx={{ p: 1.25 }}>
                {(team.projects || []).length === 0
                  ? <EmptyState icon={Workspaces} label={t("teams.view.noProjects")} accent={SECTION.projects.c} />
                  : (
                    <Grid container spacing={1}>
                      {team.projects.map((p) => (
                        <Grid item xs={12} md={6} key={p.id}>
                          <ResourceRow
                            avatar={<IconWell icon={<Code />} accent={SECTION.projects.c} />}
                            primary={p.name}
                            secondary={`PROJECT/${String(p.id).padStart(4, "0")}`}
                            accent={SECTION.projects.c}
                            onClick={() => navigate(`/project/${p.id}`)}
                            onRemove={isTeamAdmin ? () => removeProject(p.id) : null}
                            removeLabel={t("teams.view.removeProject")}
                          />
                        </Grid>
                      ))}
                    </Grid>
                  )}
              </Box>
            </TileCard>
          </Box>
        </TabPanel>

        {/* MODELS */}
        <TabPanel value={tabValue} index={2}>
          <Grid container spacing={2} sx={{ p: 2 }}>
            <Grid item xs={12} md={6}>
              <TileCard elevation={0} accent={SECTION.llms.c}>
                <TileHeader icon={<Psychology />} title={t("teams.edit.llms")} accent={SECTION.llms.c} count={counts.llms} />
                <Box sx={{ p: 1.25 }}>
                  {(team.llms || []).length === 0
                    ? <EmptyState icon={Psychology} label={t("teams.view.noLlms")} accent={SECTION.llms.c} />
                    : team.llms.map((l) => (
                      <ResourceRow
                        key={l.id}
                        avatar={<IconWell icon={<Psychology />} accent={SECTION.llms.c} />}
                        primary={l.name}
                        accent={SECTION.llms.c}
                        onRemove={isTeamAdmin ? () => removeLLM(l) : null}
                        removeLabel={t("teams.view.removeLlm")}
                      />
                    ))}
                </Box>
              </TileCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <TileCard elevation={0} accent={SECTION.embeddings.c}>
                <TileHeader icon={<Psychology />} title={t("teams.edit.embeddings")} accent={SECTION.embeddings.c} count={counts.embeddings} />
                <Box sx={{ p: 1.25 }}>
                  {(team.embeddings || []).length === 0
                    ? <EmptyState icon={Psychology} label={t("teams.view.noEmbeddings")} accent={SECTION.embeddings.c} />
                    : team.embeddings.map((e) => (
                      <ResourceRow
                        key={e.id}
                        avatar={<IconWell icon={<Psychology />} accent={SECTION.embeddings.c} />}
                        primary={e.name}
                        accent={SECTION.embeddings.c}
                        onRemove={isTeamAdmin ? () => removeEmbedding(e) : null}
                        removeLabel={t("teams.view.removeEmbedding")}
                      />
                    ))}
                </Box>
              </TileCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <TileCard elevation={0} accent={SECTION.imageGen.c}>
                <TileHeader icon={<Image />} title={t("teams.edit.imageGen")} accent={SECTION.imageGen.c} count={counts.imageGen} />
                <Box sx={{ p: 1.25 }}>
                  {(team.image_generators || []).length === 0
                    ? <EmptyState icon={Image} label={t("teams.view.noImageGen")} accent={SECTION.imageGen.c} />
                    : team.image_generators.map((g) => (
                      <ResourceRow
                        key={g}
                        avatar={<IconWell icon={<Image />} accent={SECTION.imageGen.c} />}
                        primary={g}
                        accent={SECTION.imageGen.c}
                        onRemove={isTeamAdmin ? () => removeImageGen(g) : null}
                        removeLabel={t("teams.view.removeImageGen")}
                      />
                    ))}
                </Box>
              </TileCard>
            </Grid>
            <Grid item xs={12} md={6}>
              <TileCard elevation={0} accent={SECTION.audioGen.c}>
                <TileHeader icon={<Speaker />} title={t("teams.edit.audioGen")} accent={SECTION.audioGen.c} count={counts.audioGen} />
                <Box sx={{ p: 1.25 }}>
                  {(team.audio_generators || []).length === 0
                    ? <EmptyState icon={Speaker} label={t("teams.view.noAudioGen")} accent={SECTION.audioGen.c} />
                    : team.audio_generators.map((g) => (
                      <ResourceRow
                        key={g}
                        avatar={<IconWell icon={<Speaker />} accent={SECTION.audioGen.c} />}
                        primary={g}
                        accent={SECTION.audioGen.c}
                        onRemove={isTeamAdmin ? () => removeAudioGen(g) : null}
                        removeLabel={t("teams.view.removeAudioGen")}
                      />
                    ))}
                </Box>
              </TileCard>
            </Grid>
          </Grid>
        </TabPanel>

        {/* TRANSACTIONS */}
        {isTeamAdmin && (
          <TabPanel value={tabValue} index={3}>
            <Box sx={{ p: 2 }}>
              <MUIDataTable
                title={
                  <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                    <Receipt sx={{ color: ACCENT }} />
                    <Box
                      component="span"
                      sx={{
                        fontFamily: FONT_MONO,
                        fontSize: "0.78rem",
                        fontWeight: 800,
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                        color: ACCENT,
                      }}
                    >
                      {t("teams.view.transactions")}
                    </Box>
                  </Box>
                }
                options={{
                  print: false,
                  selectableRows: "none",
                  expandableRows: true,
                  expandableRowsHeader: false,
                  expandableRowsOnClick: true,
                  download: false,
                  filter: false,
                  viewColumns: false,
                  rowsExpanded: txRowsExpanded,
                  rowsPerPage: txRows,
                  rowsPerPageOptions: [50, 100, 500],
                  elevation: 0,
                  count: txCount,
                  page: txPage,
                  serverSide: true,
                  textLabels: { body: { noMatch: t("teams.view.tx.noTransactions") } },
                  onTableChange: (action, tableState) => {
                    if (action === "changePage") setTxPage(tableState.page);
                    else if (action === "changeRowsPerPage") { setTxRows(tableState.rowsPerPage); setTxPage(0); }
                  },
                  isRowExpandable: () => true,
                  renderExpandableRow: (rowData) => {
                    const colSpan = rowData.length + 1;
                    return (
                      <TableRow>
                        <TableCell sx={{ p: 2, backgroundColor: "#0b1220" }} colSpan={colSpan}>
                          <Box sx={{ borderRadius: 1, overflow: "hidden", "& .react-json-view": { backgroundColor: "transparent !important" } }}>
                            <ReactJson src={txLog} enableClipboard={false} theme="ocean" style={{ backgroundColor: "transparent" }} />
                          </Box>
                        </TableCell>
                      </TableRow>
                    );
                  },
                  onRowExpansionChange: (_, allRowsExpanded) => {
                    setTxRowsExpanded(allRowsExpanded.slice(-1).map((i) => i.index));
                    if (allRowsExpanded.length > 0) setTxLog(transactions[allRowsExpanded[0].dataIndex]);
                  },
                }}
                data={transactions.map((tx) => [
                  tx.date, tx.project, tx.user, tx.llm, tx.input_tokens, tx.output_tokens, (tx.total_cost || 0),
                ])}
                columns={[
                  { name: t("teams.view.tx.date"), options: {
                    customHeadRender: ({ index, ...c }) => <TableCell key={index} style={{ width: 180 }}>{c.label}</TableCell>,
                    customBodyRender: (v) => (
                      <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>
                        {new Date(v).toLocaleString()}
                      </Box>
                    ),
                  } },
                  { name: t("teams.view.tx.project") },
                  { name: t("teams.view.tx.user") },
                  { name: t("teams.view.tx.llm"), options: {
                    customBodyRender: (v) => (
                      <Box
                        component="span"
                        sx={{
                          display: "inline-block",
                          px: 0.7, py: 0.2,
                          borderRadius: 0.75,
                          backgroundColor: SECTION.llms.soft,
                          color: SECTION.llms.c,
                          fontFamily: FONT_MONO,
                          fontSize: "0.7rem",
                          fontWeight: 700,
                        }}
                      >
                        {v}
                      </Box>
                    ),
                  } },
                  { name: t("teams.view.tx.inTokens"),  options: { customBodyRender: (v) => <Box component="span" sx={{ fontFamily: FONT_MONO }}>{(v || 0).toLocaleString()}</Box> } },
                  { name: t("teams.view.tx.outTokens"), options: { customBodyRender: (v) => <Box component="span" sx={{ fontFamily: FONT_MONO }}>{(v || 0).toLocaleString()}</Box> } },
                  { name: t("teams.view.tx.cost"),      options: { customBodyRender: (v) => <Box component="span" sx={{ fontFamily: FONT_MONO, fontWeight: 700, color: "#10b981" }}>${(v || 0).toFixed(4)}</Box> } },
                ]}
              />
            </Box>
          </TabPanel>
        )}
      </TileCard>
    </Container>
  );
}
