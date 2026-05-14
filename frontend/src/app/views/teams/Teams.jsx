import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Grid, IconButton, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Add, Edit, Delete, Visibility, Groups, Group, Person,
  WorkspacesOutlined, Star,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import { useTranslation } from "react-i18next";
import DataList from "app/components/DataList";
import api from "app/utils/api";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";

// Teams = collaboration / org / membership → fuchsia reads as
// "social". Distinct from cron-amber, audit-indigo, logs-violet,
// routines-emerald, proxy-cyan, classifier-violet, guards-rose,
// evals-teal, gpu-orange, tools-cobalt.
const ACCENT = "#c026d3";        // fuchsia-600
const ACCENT_DARK = "#a21caf";   // fuchsia-700
const ACCENT_SOFT = "rgba(192,38,211,0.10)";

// Role palette — fuchsia family with one warm contrast for platform admin.
const ROLE_META = {
  platform_admin: { c: "#dc2626", soft: "rgba(220,38,38,0.10)", icon: Star },
  team_admin:     { c: "#c026d3", soft: ACCENT_SOFT,            icon: Star },
  member:         { c: "#64748b", soft: "rgba(100,116,139,0.10)", icon: Person },
};

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Stat tile (metric strip above the main list).
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

function StatTile({ icon, label, value, accent = ACCENT, sub }) {
  return (
    <StatCard accent={accent} elevation={0}>
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5 }}>
        <Box
          sx={{
            width: 42, height: 42, flexShrink: 0,
            borderRadius: 1.5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${accent}25, ${accent}12)`,
            border: `1px solid ${accent}33`,
            color: accent,
            "& svg": { fontSize: 22 },
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
              fontSize: "0.62rem",
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
              fontSize: "1.55rem",
              fontWeight: 800,
              color: accent,
              lineHeight: 1.1,
              mt: 0.5,
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
                fontSize: "0.66rem",
                color: "text.disabled",
                mt: 0.4,
                letterSpacing: "0.04em",
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

// Initial-letter avatar with a deterministic per-team hue spread.
// Same team gets the same hue across reloads.
const hueFor = (s) => {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

function TeamAvatar({ name }) {
  const initial = (name || "?").trim().charAt(0).toUpperCase();
  const h = hueFor(name || "?");
  // Bias toward the fuchsia neighbourhood (260°-330°) so avatars stay
  // tonally related to the page accent without being identical.
  const hueBiased = 260 + (h % 70);
  return (
    <Box
      sx={{
        width: 36, height: 36,
        flexShrink: 0,
        borderRadius: 1.25,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#fff",
        fontFamily: FONT_MONO,
        fontWeight: 800,
        fontSize: "0.95rem",
        background: `linear-gradient(135deg, hsl(${hueBiased}, 75%, 52%) 0%, hsl(${(hueBiased + 30) % 360}, 75%, 42%) 100%)`,
        boxShadow: `0 4px 10px hsla(${hueBiased}, 75%, 50%, 0.35)`,
        textShadow: "0 1px 2px rgba(0,0,0,0.18)",
      }}
    >
      {initial}
    </Box>
  );
}

function RolePill({ role, t }) {
  const meta = ROLE_META[role];
  const Icon = meta.icon;
  const labels = {
    platform_admin: t("teams.role.platformAdmin"),
    team_admin:     t("teams.role.teamAdmin"),
    member:         t("teams.role.member"),
  };
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.85, py: 0.35,
        borderRadius: 0.75,
        backgroundColor: meta.soft,
        border: `1px solid ${meta.c}33`,
      }}
    >
      <Icon sx={{ fontSize: 12, color: meta.c }} />
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.66rem",
          fontWeight: 700,
          letterSpacing: "0.06em",
          color: meta.c,
          textTransform: "uppercase",
        }}
      >
        {labels[role]}
      </Box>
    </Box>
  );
}

// Compact mono count chip used in the table density columns.
function CountChip({ value, icon: Icon, color = ACCENT }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.7, py: 0.25,
        borderRadius: 0.75,
        backgroundColor: `${color}10`,
        border: `1px solid ${color}33`,
        minWidth: 38,
      }}
    >
      {Icon && <Icon sx={{ fontSize: 12, color }} />}
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.78rem",
          fontWeight: 700,
          color,
        }}
      >
        {value}
      </Box>
    </Box>
  );
}

export default function Teams() {
  const { t } = useTranslation();
  const [teams, setTeams] = useState([]);
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.is_admin;

  const fetchTeams = async () => {
    try {
      const data = await api.get("/teams", user.token);
      setTeams(data.teams || []);
    } catch (e) { /* toasted */ }
  };

  useEffect(() => {
    document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - Teams`;
    fetchTeams();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const userRole = (team) => {
    if (isAdmin) return "platform_admin";
    if ((team.admins || []).some((a) => a.username === user.username)) return "team_admin";
    return "member";
  };

  const handleDelete = (e, team) => {
    e.stopPropagation();
    if (!window.confirm(t("teams.deleteConfirm", { name: team.name }))) return;
    api.delete(`/teams/${team.id}`, user.token)
      .then(() => {
        toast.success(t("teams.deleted"));
        fetchTeams();
      })
      .catch(() => {});
  };

  // Aggregates for the stat strip + role-distribution pill row.
  const aggregates = useMemo(() => {
    const memberSet = new Set();
    let totalProjects = 0;
    const myMemberships = [];
    teams.forEach((tm) => {
      (tm.users || []).forEach((u) => memberSet.add(u.username));
      totalProjects += (tm.projects || []).length;
      const r = userRole(tm);
      myMemberships.push(r);
    });
    const myAdmin = myMemberships.filter((r) => r === "team_admin" || r === "platform_admin").length;
    const myMember = myMemberships.filter((r) => r === "member").length;
    return {
      teams: teams.length,
      members: memberSet.size,
      projects: totalProjects,
      myAdmin,
      myMember,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teams, isAdmin, user.username]);

  const columns = [
    {
      key: "name",
      label: t("teams.columns.name"),
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <TeamAvatar name={row.name} />
          <Box sx={{ minWidth: 0 }}>
            <Box
              sx={{
                fontWeight: 700,
                fontSize: "0.92rem",
                color: "text.primary",
                lineHeight: 1.15,
              }}
            >
              {row.name}
            </Box>
            <Box
              component="span"
              sx={{
                fontFamily: FONT_MONO,
                fontSize: "0.64rem",
                color: "text.disabled",
                letterSpacing: "0.04em",
              }}
            >
              TEAM/{String(row.id).padStart(4, "0")}
            </Box>
          </Box>
        </Box>
      ),
    },
    {
      key: "description",
      label: t("teams.columns.description"),
      render: (row) => (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{
            maxWidth: 320,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontSize: "0.82rem",
          }}
        >
          {row.description || (
            <Box component="span" sx={{ color: "text.disabled", fontStyle: "italic" }}>—</Box>
          )}
        </Typography>
      ),
    },
    {
      key: "users",
      label: t("teams.columns.users"),
      sortable: true,
      sortValue: (row) => (row.users || []).length,
      render: (row) => <CountChip value={(row.users || []).length} icon={Person} color="#7c3aed" />,
    },
    {
      key: "projects",
      label: t("teams.columns.projects"),
      sortable: true,
      sortValue: (row) => (row.projects || []).length,
      render: (row) => <CountChip value={(row.projects || []).length} icon={WorkspacesOutlined} color={ACCENT} />,
    },
    {
      key: "role",
      label: t("teams.role.label"),
      sortable: true,
      sortValue: (row) => userRole(row),
      render: (row) => <RolePill role={userRole(row)} t={t} />,
    },
  ];

  return (
    <Container>
      <PageHero
        icon={<Groups sx={{ color: "#fff" }} />}
        eyebrow="WORKSPACE/TEAMS"
        title={t("teams.title") || "Teams"}
        subtitle={t("teams.subtitle")}
        stats={[
          { glyph: "◆", color: "#f0abfc", label: `${aggregates.teams} team${aggregates.teams === 1 ? "" : "s"}` },
          { glyph: "★", color: "#e9d5ff", label: `${aggregates.members} member${aggregates.members === 1 ? "" : "s"}` },
          { glyph: "⌬", color: "#fcd34d", label: `${aggregates.projects} project${aggregates.projects === 1 ? "" : "s"}` },
        ]}
        actions={
          isAdmin && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => navigate("/teams/new")}
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
              {t("teams.new")}
            </Button>
          )
        }
      />

      <Grid container spacing={2} sx={{ mt: 1, mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Groups />}
            label="Teams"
            value={aggregates.teams}
            accent={ACCENT}
            sub={isAdmin ? "platform-wide" : "your access"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Group />}
            label="Unique members"
            value={aggregates.members}
            accent="#7c3aed"
            sub={`${aggregates.teams ? (aggregates.members / aggregates.teams).toFixed(1) : "0"} avg / team`}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<WorkspacesOutlined />}
            label="Projects"
            value={aggregates.projects}
            accent="#0891b2"
            sub={`${aggregates.teams ? (aggregates.projects / aggregates.teams).toFixed(1) : "0"} avg / team`}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Star />}
            label="Your role"
            value={
              isAdmin
                ? "ADMIN"
                : aggregates.myAdmin > 0
                  ? `${aggregates.myAdmin}× admin`
                  : `${aggregates.myMember}× member`
            }
            accent={isAdmin ? "#dc2626" : aggregates.myAdmin > 0 ? ACCENT : "#64748b"}
            sub={
              isAdmin
                ? "platform-level"
                : aggregates.myAdmin > 0
                  ? `+ ${aggregates.myMember}× member`
                  : "no admin teams"
            }
          />
        </Grid>
      </Grid>

      <DataList
        data={teams}
        columns={columns}
        searchKeys={["name", "description"]}
        onRowClick={(row) => navigate(`/team/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "id", direction: "desc" }}
        actions={(row) => {
          const role = userRole(row);
          const canEdit = role !== "member";
          return (
            <>
              <Tooltip title={t("teams.actions.view")} arrow>
                <IconButton
                  size="small"
                  onClick={() => navigate(`/team/${row.id}`)}
                  sx={{ color: ACCENT, "&:hover": { backgroundColor: ACCENT_SOFT } }}
                >
                  <Visibility fontSize="small" />
                </IconButton>
              </Tooltip>
              {canEdit && (
                <Tooltip title={t("teams.actions.edit")} arrow>
                  <IconButton
                    size="small"
                    onClick={() => navigate(`/team/${row.id}/edit`)}
                    sx={{ color: "#7c3aed", "&:hover": { backgroundColor: "rgba(124,58,237,0.10)" } }}
                  >
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              {isAdmin && (
                <Tooltip title={t("teams.actions.delete")} arrow>
                  <IconButton
                    size="small"
                    onClick={(e) => handleDelete(e, row)}
                    sx={{
                      color: "text.disabled",
                      "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.08)" },
                    }}
                  >
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </>
          );
        }}
        emptyState={{
          icon: Groups,
          title: t("teams.emptyTitle"),
          message: t("teams.emptyMessage"),
          actionLabel: isAdmin ? t("teams.new") : undefined,
          actionIcon: <Add fontSize="small" />,
          onAction: isAdmin ? () => navigate("/teams/new") : undefined,
        }}
        emptyMessage={t("teams.noTeams")}
      />
    </Container>
  );
}

