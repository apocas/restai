import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, CircularProgress, Grid, IconButton, InputAdornment, MenuItem, styled,
  TextField, Tooltip, Typography,
} from "@mui/material";
import {
  Check, Clear, Lock, Search, Star, AccountTree, People, Shield, Key,
  Security,
} from "@mui/icons-material";
import PageHero from "app/components/page/PageHero";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, cleanCardSx } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

const ROW_HEIGHT = 44;
const USER_COL_WIDTH = 240;
const PROJECT_COL_WIDTH = 56;
const HEADER_HEIGHT = 160;

const ROLE_COLORS = {
  platformAdmin: "#e65100",
  teamAdmin:     "#1565c0",
  direct:        "#2e7d32",
  restricted:    "#9e9e9e",
};

function RoleBadges({ user }) {
  const badges = [];
  if (user.is_admin) {
    badges.push(
      <Tooltip key="admin" title="Platform Admin" arrow>
        <Star sx={{ fontSize: 15, color: ROLE_COLORS.platformAdmin }} />
      </Tooltip>
    );
  }
  if (user.admin_team_ids?.length > 0 && !user.is_admin) {
    badges.push(
      <Tooltip key="team-admin" title={`Team Admin (${user.admin_team_ids.length} team${user.admin_team_ids.length > 1 ? "s" : ""})`} arrow>
        <Shield sx={{ fontSize: 15, color: ROLE_COLORS.teamAdmin }} />
      </Tooltip>
    );
  }
  if (user.is_restricted) {
    badges.push(
      <Tooltip key="restricted" title="Restricted (read-only)" arrow>
        <Lock sx={{ fontSize: 13, color: ROLE_COLORS.restricted }} />
      </Tooltip>
    );
  }
  return <>{badges}</>;
}

function AccessCell({ user, project, hasDirectAccess, isHover, onHover, onLeave }) {
  const isAdmin = user.is_admin;
  const isTeamAdmin = !isAdmin && user.admin_team_ids?.includes(project.team_id);
  const hasAccess = isAdmin || isTeamAdmin || hasDirectAccess;

  let icon = null;
  let tip = "";

  if (isAdmin) {
    icon = <Star sx={{ fontSize: 14, color: ROLE_COLORS.platformAdmin, opacity: 0.5 }} />;
    tip = `${user.username} — platform admin`;
  } else if (isTeamAdmin) {
    icon = <Shield sx={{ fontSize: 14, color: ROLE_COLORS.teamAdmin, opacity: 0.7 }} />;
    tip = `${user.username} — team admin of ${project.team_name || "this team"}`;
  } else if (hasDirectAccess) {
    icon = <Check sx={{ fontSize: 16, color: ROLE_COLORS.direct }} />;
    tip = `${user.username} — direct assignment`;
  }

  return (
    <Tooltip title={tip} arrow placement="top" disableHoverListener={!hasAccess}>
      <Box
        onMouseEnter={onHover}
        onMouseLeave={onLeave}
        sx={{
          height: ROW_HEIGHT,
          borderBottom: "1px solid", borderColor: "divider",
          display: "flex", alignItems: "center", justifyContent: "center",
          bgcolor: isHover ? "action.hover" : "transparent",
        }}
      >
        {icon}
      </Box>
    </Tooltip>
  );
}

export default function PermissionMatrix() {
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedTeamId, setSelectedTeamId] = useState("all");
  const [hoverRow, setHoverRow] = useState(null);
  const [hoverCol, setHoverCol] = useState(null);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("permissions.title");
    api.get("/permissions/matrix", auth.user.token)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const teams = useMemo(() => {
    if (!data) return [];
    const map = new Map();
    let hasNoTeam = false;
    for (const p of data.projects) {
      if (p.team_id == null) {
        hasNoTeam = true;
      } else if (!map.has(p.team_id)) {
        map.set(p.team_id, p.team_name || t("permissions.teamFallback", { id: p.team_id }));
      }
    }
    const sorted = Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
    if (hasNoTeam) sorted.push({ id: "none", name: t("permissions.noTeam") });
    return sorted;
  }, [data, t]);

  const tooManyProjects = (data?.projects?.length || 0) > 50;
  useEffect(() => {
    if (tooManyProjects && selectedTeamId === "all" && teams.length > 0) {
      setSelectedTeamId(teams[0].id);
    }
  }, [tooManyProjects, selectedTeamId, teams]);

  const { filteredUsers, filteredProjects, accessSet, stats } = useMemo(() => {
    if (!data) return { filteredUsers: [], filteredProjects: [], accessSet: new Set(), stats: {} };

    let teamFilteredProjects = data.projects;
    if (selectedTeamId === "none") {
      teamFilteredProjects = data.projects.filter((p) => p.team_id == null);
    } else if (selectedTeamId !== "all") {
      teamFilteredProjects = data.projects.filter((p) => p.team_id === selectedTeamId);
    }

    const q = search.trim().toLowerCase();
    const userMatch = q && data.users.some((u) => u.username.toLowerCase().includes(q));
    const projectMatch = q && teamFilteredProjects.some((p) => p.name.toLowerCase().includes(q));

    const usersToShow = !q ? data.users : (userMatch ? data.users.filter((u) => u.username.toLowerCase().includes(q)) : data.users);
    const projectsToShow = !q ? teamFilteredProjects : (projectMatch ? teamFilteredProjects.filter((p) => p.name.toLowerCase().includes(q)) : teamFilteredProjects);

    const set = new Set(data.assignments.map((a) => `${a.user_id}:${a.project_id}`));
    const teamAdminCount = data.users.filter((u) => !u.is_admin && u.admin_team_ids?.length > 0).length;

    return {
      filteredUsers: usersToShow,
      filteredProjects: projectsToShow,
      accessSet: set,
      stats: {
        users: data.users.length,
        projects: teamFilteredProjects.length,
        assignments: data.assignments.length,
        admins: data.users.filter((u) => u.is_admin).length,
        teamAdmins: teamAdminCount,
      },
    };
  }, [data, search, selectedTeamId]);

  if (loading) {
    return (
      <Container>
        <Box sx={{ textAlign: "center", py: 12 }}><CircularProgress /></Box>
      </Container>
    );
  }

  if (!data) {
    return (
      <Container>
        <PageHero
          icon={<Security sx={{ color: "#fff" }} />}
          eyebrow="ADMIN"
          title={t("permissions.title")}
          subtitle="User-project access matrix."
          compact
        />
        <Card variant="outlined" sx={{ ...cleanCardSx, p: 4, textAlign: "center" }}>
          <Typography color="text.secondary">{t("permissions.failed")}</Typography>
        </Card>
      </Container>
    );
  }

  return (
    <Container>
      <PageHero
        icon={<Security sx={{ color: "#fff" }} />}
        eyebrow="ADMIN"
        title={t("permissions.title")}
        subtitle="User-project access matrix across all teams."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${stats.users} users` },
          { glyph: "▣", color: "#86efac", label: `${stats.projects} projects` },
          { glyph: "⚡", color: "#fcd34d", label: `${stats.assignments} assignments` },
          { glyph: "★", color: "#fca5a5", label: `${stats.admins} admins` },
          ...(stats.teamAdmins > 0 ? [{ glyph: "⛨", color: "#93c5fd", label: `${stats.teamAdmins} team admins` }] : []),
        ]}
        compact
      />

      {/* Filters */}
      <Card variant="outlined" sx={{ ...cleanCardSx, p: 2, mb: 2, "&:hover": { transform: "none", borderColor: "divider", boxShadow: "none" } }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={4} md={3}>
            <TextField
              fullWidth size="small" select
              label={t("permissions.team")}
              value={selectedTeamId}
              onChange={(e) => setSelectedTeamId(e.target.value)}
            >
              <MenuItem value="all" disabled={tooManyProjects}>
                {tooManyProjects ? (
                  <Tooltip title={t("permissions.allTeamsDisabledTip")} placement="right" arrow>
                    <span>{t("permissions.allTeams")}</span>
                  </Tooltip>
                ) : (
                  t("permissions.allTeams")
                )}
              </MenuItem>
              {teams.map((tm) => (
                <MenuItem key={tm.id} value={tm.id}>{tm.name}</MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid item xs={12} sm={8} md={9}>
            <TextField
              fullWidth size="small"
              placeholder={t("permissions.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{
                startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment>,
                endAdornment: search && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setSearch("")}><Clear fontSize="small" /></IconButton>
                  </InputAdornment>
                ),
              }}
            />
          </Grid>
        </Grid>
      </Card>

      {/* Matrix */}
      <Card variant="outlined" sx={{ ...cleanCardSx, "&:hover": { transform: "none", borderColor: "divider", boxShadow: "none" } }}>
        {filteredUsers.length === 0 || filteredProjects.length === 0 ? (
          <Box sx={{ p: 6, textAlign: "center", color: "text.secondary" }}>
            <Typography variant="body2">{t("permissions.noMatches")}</Typography>
          </Box>
        ) : (
          <Box sx={{
            display: "grid",
            gridTemplateColumns: `${USER_COL_WIDTH}px repeat(${filteredProjects.length}, ${PROJECT_COL_WIDTH}px)`,
            maxHeight: "70vh",
            overflow: "auto",
            position: "relative",
          }}>
            {/* Top-left corner */}
            <Box sx={{
              position: "sticky", top: 0, left: 0, zIndex: 3,
              height: HEADER_HEIGHT, bgcolor: "background.paper",
              borderBottom: "1px solid", borderRight: "1px solid", borderColor: "divider",
              display: "flex", alignItems: "flex-end", p: 1.5,
            }}>
              <Typography sx={{
                fontFamily: FONT_MONO, fontSize: "0.62rem",
                letterSpacing: "0.14em", fontWeight: 700,
                color: "rgba(15,23,42,0.5)", textTransform: "uppercase",
              }}>
                {t("permissions.header")}
              </Typography>
            </Box>

            {/* Project headers (rotated) */}
            {filteredProjects.map((p, colIdx) => (
              <Tooltip key={p.id} title={`${p.name}${p.team_name ? ` (${p.team_name})` : ""}`} placement="top" arrow>
                <Box
                  onClick={() => navigate(`/project/${p.id}`)}
                  onMouseEnter={() => setHoverCol(colIdx)}
                  onMouseLeave={() => setHoverCol(null)}
                  sx={{
                    position: "sticky", top: 0, zIndex: 2,
                    height: HEADER_HEIGHT,
                    bgcolor: hoverCol === colIdx ? "action.hover" : "background.paper",
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    display: "flex", alignItems: "flex-end", justifyContent: "center",
                    cursor: "pointer", overflow: "hidden",
                    "&:hover": { bgcolor: "action.hover" },
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      writingMode: "vertical-rl",
                      transform: "rotate(180deg)",
                      whiteSpace: "nowrap",
                      textOverflow: "ellipsis",
                      overflow: "hidden",
                      maxHeight: HEADER_HEIGHT - 16,
                      py: 1,
                      fontWeight: 500,
                    }}
                  >
                    {p.name}
                  </Typography>
                </Box>
              </Tooltip>
            ))}

            {/* User rows */}
            {filteredUsers.map((u, rowIdx) => (
              <Box key={u.id} sx={{ display: "contents" }}>
                {/* Username cell (sticky left) */}
                <Box
                  onClick={() => navigate(`/user/${u.username}`)}
                  onMouseEnter={() => setHoverRow(rowIdx)}
                  onMouseLeave={() => setHoverRow(null)}
                  sx={{
                    position: "sticky", left: 0, zIndex: 1,
                    height: ROW_HEIGHT,
                    bgcolor: hoverRow === rowIdx ? "action.hover" : "background.paper",
                    borderBottom: "1px solid", borderRight: "1px solid", borderColor: "divider",
                    display: "flex", alignItems: "center", gap: 0.75, px: 1.5,
                    cursor: "pointer",
                    "&:hover": { bgcolor: "action.hover" },
                  }}
                >
                  <Typography variant="body2" fontWeight={u.is_admin ? 600 : 400} noWrap sx={{ flex: 1 }}>
                    {u.username}
                  </Typography>
                  <RoleBadges user={u} />
                </Box>

                {/* Access cells */}
                {filteredProjects.map((p, colIdx) => (
                  <AccessCell
                    key={p.id}
                    user={u}
                    project={p}
                    hasDirectAccess={accessSet.has(`${u.id}:${p.id}`)}
                    isHover={hoverRow === rowIdx || hoverCol === colIdx}
                    onHover={() => { setHoverRow(rowIdx); setHoverCol(colIdx); }}
                    onLeave={() => { setHoverRow(null); setHoverCol(null); }}
                  />
                ))}
              </Box>
            ))}
          </Box>
        )}
      </Card>

      {/* Legend */}
      <Box sx={{
        mt: 2, display: "flex", gap: 3, flexWrap: "wrap",
        color: "text.secondary", alignItems: "center",
      }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Check sx={{ fontSize: 16, color: ROLE_COLORS.direct }} />
          <Typography variant="caption">{t("permissions.legendDirect")}</Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Shield sx={{ fontSize: 16, color: ROLE_COLORS.teamAdmin }} />
          <Typography variant="caption">Team Admin</Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Star sx={{ fontSize: 16, color: ROLE_COLORS.platformAdmin }} />
          <Typography variant="caption">{t("permissions.legendAdmin")}</Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Lock sx={{ fontSize: 14, color: ROLE_COLORS.restricted }} />
          <Typography variant="caption">{t("permissions.legendRestricted")}</Typography>
        </Box>
      </Box>
    </Container>
  );
}
