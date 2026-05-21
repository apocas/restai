import { useState, useEffect, useMemo } from "react";
import {
  Avatar, Box, Card, Chip, CircularProgress, Grid, IconButton,
  LinearProgress, Tooltip, Typography, styled,
} from "@mui/material";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import sha256 from "crypto-js/sha256";
import {
  Person, Settings, Delete, Group, Psychology,
  AccountBalanceWallet, Receipt, AllInclusive, Image, Speaker,
  Star, Workspaces, ArrowDropDown, ArrowRight,
} from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import ReactJson from "@microlink/react-json-view";
import BAvatar from "boring-avatars";
import api from "app/utils/api";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";
import { FONT_MONO, sweep, pulse, shimmer, blink } from "app/components/page/pageStyles";

// Same per-type pixel-avatar palette as the projects list / library
// cards so a project's pixel identity stays consistent across the app.
const PROJECT_AVATAR_PALETTES = {
  rag:   ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#1e1b4b"],
  agent: ["#10b981", "#34d399", "#6ee7b7", "#a7f3d0", "#064e3b"],
  block: ["#6b7280", "#9ca3af", "#d1d5db", "#e5e7eb", "#1f2937"],
  app:   ["#0891b2", "#22d3ee", "#67e8f9", "#a5f3fc", "#164e63"],
};

function ProjectPixelAvatar({ project, size = 32 }) {
  return (
    <Box sx={{ flexShrink: 0, lineHeight: 0 }}>
      <BAvatar
        name={project.name || String(project.id)}
        size={size}
        variant="pixel"
        colors={PROJECT_AVATAR_PALETTES[project.type] || PROJECT_AVATAR_PALETTES.block}
        square
      />
    </Box>
  );
}

// One quiet platform accent. The previous file declared a 7-color
// SECTION map that left every team page looking like a status board;
// this matches the calmer Evals / Logs / Project sub-pages.
const ACCENT = "#0891b2";        // cyan-600
const ACCENT_SOFT = "rgba(8,145,178,0.10)";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Hero card retains the navy/cyan mesh used everywhere else in the
// app so the team landing page stays in the wider visual family.
const HeroCard = styled(Card)(({ theme }) => ({
  position: "relative",
  padding: theme.spacing(4),
  marginBottom: theme.spacing(3),
  borderRadius: 20,
  overflow: "hidden",
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
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background:
      "linear-gradient(90deg, transparent, rgba(125,211,252,0.55), rgba(56,189,248,0.55), transparent)",
    animation: `${sweep} 6s ease-in-out infinite`,
    pointerEvents: "none",
    zIndex: 2,
  },
  "& > *": { position: "relative", zIndex: 1 },
}));

const ActionBar = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(0.5),
  flexWrap: "wrap",
  marginTop: theme.spacing(3),
  paddingTop: theme.spacing(2),
  borderTop: "1px solid rgba(255,255,255,0.12)",
}));

const pillSx = {
  backgroundColor: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.92)",
  backdropFilter: "blur(12px)",
  fontWeight: 500,
  "& .MuiChip-icon": { color: "rgba(255,255,255,0.85)" },
};
const pillWarnSx = {
  ...pillSx,
  backgroundColor: "rgba(245,158,11,0.18)",
  border: "1px solid rgba(245,158,11,0.5)",
  color: "#fde68a",
  "& .MuiChip-icon": { color: "#fde68a" },
};
const pillDangerSx = {
  ...pillSx,
  backgroundColor: "rgba(239,68,68,0.18)",
  border: "1px solid rgba(239,68,68,0.5)",
  color: "#fecaca",
  "& .MuiChip-icon": { color: "#fecaca" },
};
const pillGoodSx = {
  ...pillSx,
  backgroundColor: "rgba(16,185,129,0.18)",
  border: "1px solid rgba(16,185,129,0.5)",
  color: "#a7f3d0",
  "& .MuiChip-icon": { color: "#a7f3d0" },
};

const heroIconBtnSx = {
  color: "rgba(255,255,255,0.85)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 1.5,
  background: "rgba(255,255,255,0.06)",
  backdropFilter: "blur(12px)",
  transition: "all 0.2s ease",
  "&:hover": {
    color: "#fff",
    background: "rgba(255,255,255,0.14)",
    borderColor: "rgba(255,255,255,0.32)",
  },
};

// Body section card — mirrors `sectionShellSx` from the project
// Integrations kit so team pages sit in the same visual family as the
// rest of the platform: thin animated accent sweep at the top, soft
// border, no hover lift (full-page surface, not a list tile).
const sectionCardSx = {
  position: "relative",
  borderRadius: 2,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background: `linear-gradient(90deg, transparent, ${ACCENT}, transparent)`,
    transform: "translateX(-100%)",
    animation: `${sweep} 6s linear infinite`,
    pointerEvents: "none",
    opacity: 0.55,
    zIndex: 2,
  },
};

// Section header strip — mono-uppercase title in slate (matching the
// rest of the platform's section headers), small slate icon, optional
// count pill. Plain dark text without the accent rainbow that used to
// shout at the user.
function SectionHeader({ icon: Icon, title, subtitle, count, action }) {
  return (
    <Box
      sx={{
        px: 2.5, pt: 2, pb: 1.5,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid",
        borderColor: "divider",
        flexWrap: "wrap",
      }}
    >
      {Icon && <Icon sx={{ fontSize: 16, color: "text.secondary", flexShrink: 0 }} />}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.74rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: "#0f172a",
            lineHeight: 1.1,
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
            fontFamily: FONT_MONO,
            fontSize: "0.68rem",
            fontWeight: 700,
            color: "text.secondary",
            px: 0.9, py: 0.25,
            borderRadius: 0.75,
            background: "rgba(15,23,42,0.04)",
            border: "1px solid rgba(15,23,42,0.08)",
            letterSpacing: "0.04em",
          }}
        >
          {count}
        </Box>
      )}
      {action}
    </Box>
  );
}

// Team / generic name avatar — initial in muted slate. Used only for
// non-user surfaces (team hero) since teams don't have an email to
// hash against Gravatar.
function NameAvatar({ name, size = 30 }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase();
  return (
    <Box
      sx={{
        width: size, height: size, flexShrink: 0,
        borderRadius: 1,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: FONT_MONO,
        fontWeight: 700,
        fontSize: size > 32 ? "1rem" : "0.78rem",
        background: "linear-gradient(135deg, #475569 0%, #334155 100%)",
        boxShadow: "0 1px 2px rgba(15,23,42,0.15)",
      }}
    >
      {initial}
    </Box>
  );
}

// Member / admin row avatar — Gravatar identicon, matching the
// platform-wide pattern used on Users list / project members.
// Admin ring is cyan (matches platform accent) to distinguish from
// regular members without going back to the old red.
function UserGravatar({ username, isAdmin = false, size = 30 }) {
  const ring = isAdmin ? ACCENT : "rgba(15,23,42,0.12)";
  return (
    <Avatar
      src={`https://www.gravatar.com/avatar/${sha256(username || "")}?d=identicon`}
      alt={username}
      sx={{
        width: size, height: size,
        flexShrink: 0,
        border: `2px solid ${ring}`,
        boxShadow: isAdmin
          ? `0 0 0 1px #fff, 0 2px 6px ${ACCENT}33`
          : "0 1px 2px rgba(15,23,42,0.08)",
      }}
    />
  );
}

function ResourceRow({ avatar, primary, secondary, onClick, onRemove, removeLabel }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        gap: 1.25,
        px: 1.25, py: 1,
        borderRadius: 1,
        cursor: onClick ? "pointer" : "default",
        transition: "background-color 0.15s ease",
        "&:hover": { backgroundColor: "rgba(15,23,42,0.03)" },
      }}
    >
      {avatar}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box
          component="span"
          sx={{
            display: "block",
            fontWeight: 600,
            fontSize: "0.85rem",
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
              fontSize: "0.62rem",
              color: "text.disabled",
              letterSpacing: "0.04em",
              mt: 0.1,
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

function IconWell({ icon }) {
  return (
    <Box
      sx={{
        width: 30, height: 30, flexShrink: 0,
        borderRadius: 1,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(15,23,42,0.04)",
        border: "1px solid rgba(15,23,42,0.08)",
        color: "text.secondary",
        "& svg": { fontSize: 15 },
      }}
    >
      {icon}
    </Box>
  );
}

function EmptyState({ icon: Icon, label }) {
  return (
    <Box
      sx={{
        py: 3,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 0.75,
      }}
    >
      <Box
        sx={{
          width: 36, height: 36,
          borderRadius: "50%",
          background: "rgba(15,23,42,0.04)",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          animation: `${pulse} 3s ease-out infinite`,
        }}
      >
        <Icon sx={{ fontSize: 16, color: "text.disabled" }} />
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
        {label}
      </Typography>
    </Box>
  );
}

function CollapsiblePanel({ title, icon: Icon, children, open, onToggle }) {
  return (
    <Card variant="outlined" sx={sectionCardSx}>
      <Box
        onClick={onToggle}
        sx={{
          px: 2.5, py: 1.5,
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          cursor: "pointer",
          transition: "background-color 0.15s ease",
          "&:hover": { backgroundColor: "rgba(15,23,42,0.02)" },
          borderBottom: open ? "1px solid" : "none",
          borderColor: "divider",
        }}
      >
        {Icon && <Icon sx={{ fontSize: 16, color: "text.secondary" }} />}
        <Typography
          sx={{
            flex: 1,
            fontFamily: FONT_MONO,
            fontSize: "0.74rem",
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: "#0f172a",
          }}
        >
          {title}
        </Typography>
        {open
          ? <ArrowDropDown sx={{ color: "text.secondary" }} />
          : <ArrowRight sx={{ color: "text.secondary" }} />}
      </Box>
      {open && children}
    </Card>
  );
}

export default function TeamView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [team, setTeam] = useState(null);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);

  const [transactions, setTransactions] = useState([]);
  const [txPage, setTxPage] = useState(0);
  const [txRows, setTxRows] = useState(100);
  const [txCount, setTxCount] = useState(0);
  const [txLog, setTxLog] = useState({});
  const [txRowsExpanded, setTxRowsExpanded] = useState([]);
  const [txOpen, setTxOpen] = useState(false);

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
    if (txOpen && team) fetchTransactions();
    // eslint-disable-next-line
  }, [txOpen, team, txPage, txRows]);

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

  if (loading) {
    return (
      <Container>
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 12, gap: 2 }}>
          <Box
            sx={{
              width: 56, height: 56,
              borderRadius: "50%",
              background: ACCENT_SOFT,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              animation: `${pulse} 2s ease-out infinite`,
            }}
          >
            <CircularProgress size={24} sx={{ color: ACCENT }} />
          </Box>
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.7rem",
              color: "text.disabled",
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
        <Typography variant="h6" sx={{ p: 4, textAlign: "center", color: "text.secondary" }}>
          {t("teams.view.notFound")}
        </Typography>
      </Container>
    );
  }

  const hasBudget = team.budget >= 0;
  const spent = team.spending ?? 0;
  const budget = team.budget;
  const pct = hasBudget && budget > 0 ? Math.min((spent / budget) * 100, 100) : 0;
  const barColor = pct > 90 ? "#ef4444" : pct > 70 ? "#f59e0b" : "#10b981";

  return (
    <Container>
      {/* ── HERO ──────────────────────────────────────────────── */}
      <HeroCard elevation={0}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2.5, flexWrap: "wrap" }}>
          <NameAvatar name={team.name} size={64} />
          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.75,
                fontFamily: FONT_MONO,
                fontSize: "0.65rem",
                letterSpacing: 3,
                lineHeight: 1.2,
                textTransform: "uppercase",
              }}
            >
              <Box
                component="span"
                role="link"
                tabIndex={0}
                onClick={() => navigate("/teams")}
                onKeyDown={(e) => { if (e.key === "Enter") navigate("/teams"); }}
                sx={{
                  color: "rgba(255,255,255,0.75)",
                  cursor: "pointer",
                  transition: "color 0.15s ease",
                  "&:hover": {
                    color: "#fff",
                    textDecoration: "underline",
                    textUnderlineOffset: "3px",
                  },
                }}
              >
                Teams
              </Box>
              <Box component="span" sx={{ color: "rgba(255,255,255,0.4)" }}>/</Box>
              <Box component="span" sx={{ color: "rgba(125,211,252,0.95)" }}>
                {String(team.id).padStart(4, "0")}
              </Box>
            </Box>

            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", mt: 0.5 }}>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 700,
                  color: "#fff",
                  letterSpacing: "-0.5px",
                  textShadow: "0 2px 20px rgba(0,0,0,0.2)",
                }}
              >
                {team.name}
                <Box
                  component="span"
                  sx={{
                    display: "inline-block",
                    width: 10,
                    ml: 0.5,
                    animation: `${blink} 1.1s steps(2, start) infinite`,
                    color: "rgba(125,211,252,0.9)",
                  }}
                >_</Box>
              </Typography>
            </Box>

            {team.description && (
              <Typography
                variant="body2"
                sx={{ mt: 1, color: "rgba(255,255,255,0.82)", maxWidth: 720 }}
              >
                {team.description}
              </Typography>
            )}

            <Box sx={{ display: "flex", gap: 1, mt: 2, flexWrap: "wrap", alignItems: "center" }}>
              <Chip icon={<Group />} label={`${counts.users} member${counts.users === 1 ? "" : "s"}`} size="small" sx={pillSx} />
              <Chip icon={<Star />} label={`${counts.admins} admin${counts.admins === 1 ? "" : "s"}`} size="small" sx={pillSx} />
              <Chip icon={<Workspaces />} label={`${counts.projects} project${counts.projects === 1 ? "" : "s"}`} size="small" sx={pillSx} />
              {(counts.llms + counts.embeddings) > 0 && (
                <Chip icon={<Psychology />} label={`${counts.llms + counts.embeddings} model${(counts.llms + counts.embeddings) === 1 ? "" : "s"}`} size="small" sx={pillSx} />
              )}
              {hasBudget ? (
                <Chip
                  icon={<AccountBalanceWallet />}
                  label={`$${spent.toFixed(2)} / $${budget.toFixed(2)} (${pct.toFixed(0)}%)`}
                  size="small"
                  sx={pct > 90 ? pillDangerSx : pct > 70 ? pillWarnSx : pillGoodSx}
                />
              ) : (
                <Chip icon={<AllInclusive />} label={t("teams.view.unlimited")} size="small" sx={pillSx} />
              )}
            </Box>
          </Box>
        </Box>

        <ActionBar>
          {isTeamAdmin && (
            <Tooltip title={t("teams.view.edit")}>
              <IconButton
                size="small"
                sx={heroIconBtnSx}
                onClick={() => navigate(`/team/${id}/edit`)}
              >
                <Settings fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Box sx={{ flex: 1 }} />
        </ActionBar>
      </HeroCard>

      {/* ── BUDGET BAR (only when capped) ────────────────────── */}
      {hasBudget && (
        <Card variant="outlined" sx={{ ...sectionCardSx, mb: 2.5 }}>
          <Box sx={{ p: 2.5 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                <AccountBalanceWallet sx={{ fontSize: 16, color: barColor }} />
                <Box
                  component="span"
                  sx={{
                    fontFamily: FONT_MONO,
                    fontSize: "0.74rem",
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    color: barColor,
                  }}
                >
                  {pct.toFixed(0)}% of monthly budget used
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
        </Card>
      )}

      {/* ── PEOPLE — Members + Admins side by side ──────────── */}
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={sectionCardSx}>
            <SectionHeader
              icon={Group}
              title={t("teams.edit.members")}
              count={counts.users}
            />
            <Box sx={{ p: 1, maxHeight: 360, overflowY: "auto" }}>
              {(team.users || []).length === 0
                ? <EmptyState icon={Person} label={t("teams.view.noMembers")} />
                : team.users.map((m) => (
                  <ResourceRow
                    key={m.id}
                    avatar={<UserGravatar username={m.username} />}
                    primary={m.username}
                    secondary={m.id === user.id ? t("teams.view.you") : `USER/${String(m.id).padStart(4, "0")}`}
                    onRemove={isTeamAdmin ? () => removeUser(m.username) : null}
                    removeLabel={t("teams.view.removeUser")}
                  />
                ))}
            </Box>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={sectionCardSx}>
            <SectionHeader
              icon={Star}
              title={t("teams.edit.admins")}
              count={counts.admins}
            />
            <Box sx={{ p: 1, maxHeight: 360, overflowY: "auto" }}>
              {(team.admins || []).length === 0
                ? <EmptyState icon={Star} label={t("teams.view.noAdmins")} />
                : team.admins.map((a) => (
                  <ResourceRow
                    key={a.id}
                    avatar={<UserGravatar username={a.username} isAdmin />}
                    primary={a.username}
                    secondary={a.id === user.id ? t("teams.view.you") : `USER/${String(a.id).padStart(4, "0")}`}
                    onRemove={isTeamAdmin ? () => removeAdmin(a.username) : null}
                    removeLabel={t("teams.view.removeAdmin")}
                  />
                ))}
            </Box>
          </Card>
        </Grid>
      </Grid>

      {/* ── PROJECTS — full width, 3-col grid of items ──────── */}
      <Box sx={{ mb: 2.5 }}>
        <Card variant="outlined" sx={sectionCardSx}>
          <SectionHeader
            icon={Workspaces}
            title={t("teams.edit.projectsHeading")}
            subtitle={t("teams.view.projectsSubtitle") || "Click any project to open"}
            count={counts.projects}
          />
          <Box sx={{ p: 1 }}>
            {(team.projects || []).length === 0
              ? <EmptyState icon={Workspaces} label={t("teams.view.noProjects")} />
              : (
                <Grid container spacing={0.5}>
                  {team.projects.map((p) => {
                    const typeColor = PROJECT_TYPE_COLORS[p.type]?.color || "text.disabled";
                    return (
                      <Grid item xs={12} sm={6} lg={4} key={p.id}>
                        <ResourceRow
                          avatar={<ProjectPixelAvatar project={p} />}
                          primary={p.human_name || p.name}
                          secondary={
                            <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                              <Box
                                component="span"
                                sx={{
                                  color: typeColor,
                                  fontWeight: 700,
                                  letterSpacing: "0.08em",
                                  textTransform: "uppercase",
                                }}
                              >
                                {p.type}
                              </Box>
                              <Box component="span" sx={{ opacity: 0.5 }}>·</Box>
                              <Box component="span">
                                {`PROJECT/${String(p.id).padStart(4, "0")}`}
                              </Box>
                            </Box>
                          }
                          onClick={() => navigate(`/project/${p.id}`)}
                          onRemove={isTeamAdmin ? () => removeProject(p.id) : null}
                          removeLabel={t("teams.view.removeProject")}
                        />
                      </Grid>
                    );
                  })}
                </Grid>
              )}
          </Box>
        </Card>
      </Box>

      {/* ── MODELS — 4 inline panels in a single row ───────── */}
      <Grid container spacing={2.5} sx={{ mb: 2.5 }}>
        <Grid item xs={12} sm={6} lg={3}>
          <Card variant="outlined" sx={sectionCardSx}>
            <SectionHeader icon={Psychology} title={t("teams.edit.llms")} count={counts.llms} />
            <Box sx={{ p: 1, maxHeight: 280, overflowY: "auto" }}>
              {(team.llms || []).length === 0
                ? <EmptyState icon={Psychology} label={t("teams.view.noLlms")} />
                : team.llms.map((l) => (
                  <ResourceRow
                    key={l.id}
                    avatar={<IconWell icon={<Psychology />} />}
                    primary={l.name}
                    onRemove={isTeamAdmin ? () => removeLLM(l) : null}
                    removeLabel={t("teams.view.removeLlm")}
                  />
                ))}
            </Box>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} lg={3}>
          <Card variant="outlined" sx={sectionCardSx}>
            <SectionHeader icon={Psychology} title={t("teams.edit.embeddings")} count={counts.embeddings} />
            <Box sx={{ p: 1, maxHeight: 280, overflowY: "auto" }}>
              {(team.embeddings || []).length === 0
                ? <EmptyState icon={Psychology} label={t("teams.view.noEmbeddings")} />
                : team.embeddings.map((e) => (
                  <ResourceRow
                    key={e.id}
                    avatar={<IconWell icon={<Psychology />} />}
                    primary={e.name}
                    onRemove={isTeamAdmin ? () => removeEmbedding(e) : null}
                    removeLabel={t("teams.view.removeEmbedding")}
                  />
                ))}
            </Box>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} lg={3}>
          <Card variant="outlined" sx={sectionCardSx}>
            <SectionHeader icon={Image} title={t("teams.edit.imageGen")} count={counts.imageGen} />
            <Box sx={{ p: 1, maxHeight: 280, overflowY: "auto" }}>
              {(team.image_generators || []).length === 0
                ? <EmptyState icon={Image} label={t("teams.view.noImageGen")} />
                : team.image_generators.map((g) => (
                  <ResourceRow
                    key={g}
                    avatar={<IconWell icon={<Image />} />}
                    primary={g}
                    onRemove={isTeamAdmin ? () => removeImageGen(g) : null}
                    removeLabel={t("teams.view.removeImageGen")}
                  />
                ))}
            </Box>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} lg={3}>
          <Card variant="outlined" sx={sectionCardSx}>
            <SectionHeader icon={Speaker} title={t("teams.edit.audioGen")} count={counts.audioGen} />
            <Box sx={{ p: 1, maxHeight: 280, overflowY: "auto" }}>
              {(team.audio_generators || []).length === 0
                ? <EmptyState icon={Speaker} label={t("teams.view.noAudioGen")} />
                : team.audio_generators.map((g) => (
                  <ResourceRow
                    key={g}
                    avatar={<IconWell icon={<Speaker />} />}
                    primary={g}
                    onRemove={isTeamAdmin ? () => removeAudioGen(g) : null}
                    removeLabel={t("teams.view.removeAudioGen")}
                  />
                ))}
            </Box>
          </Card>
        </Grid>
      </Grid>

      {/* ── TRANSACTIONS — admin-only collapsible at bottom ─── */}
      {isTeamAdmin && (
        <CollapsiblePanel
          title={t("teams.view.transactions")}
          icon={Receipt}
          open={txOpen}
          onToggle={() => setTxOpen((o) => !o)}
        >
          <Box sx={{ p: 1.5 }}>
            {txOpen && (
              <MUIDataTable
                title=""
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
                          <ReactJson src={txLog} enableClipboard={false} theme="ocean" style={{ backgroundColor: "transparent" }} />
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
                          backgroundColor: "rgba(15,23,42,0.05)",
                          color: "text.secondary",
                          border: "1px solid rgba(15,23,42,0.08)",
                          fontFamily: FONT_MONO,
                          fontSize: "0.7rem",
                          fontWeight: 600,
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
            )}
          </Box>
        </CollapsiblePanel>
      )}

    </Container>
  );
}
