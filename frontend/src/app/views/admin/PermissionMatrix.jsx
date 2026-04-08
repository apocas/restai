import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Card, CircularProgress, Grid, IconButton, InputAdornment, MenuItem, styled,
  TextField, Tooltip, Typography,
} from "@mui/material";
import {
  Check, Clear, Lock, Search, Star, AccountTree, People, GroupAdd, Key,
} from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const ROW_HEIGHT = 44;
const USER_COL_WIDTH = 220;
const PROJECT_COL_WIDTH = 56;
const HEADER_HEIGHT = 160;

const StatCard = ({ icon, value, label, color }) => (
  <Card elevation={0} sx={{
    p: 2, display: "flex", alignItems: "center", gap: 2,
    borderRadius: 3, border: "1px solid", borderColor: "divider",
  }}>
    <Box sx={{
      width: 44, height: 44, borderRadius: "50%",
      display: "flex", alignItems: "center", justifyContent: "center",
      background: color, color: "#fff",
    }}>
      {icon}
    </Box>
    <Box>
      <Typography variant="h6" fontWeight={700} lineHeight={1.2}>{value}</Typography>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
    </Box>
  </Card>
);

export default function PermissionMatrix() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedTeamId, setSelectedTeamId] = useState("all");
  const [hoverRow, setHoverRow] = useState(null);
  const [hoverCol, setHoverCol] = useState(null);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Permissions";
    api.get("/permissions/matrix", auth.user.token)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const teams = useMemo(() => {
    if (!data) return [];
    const map = new Map();
    let hasNoTeam = false;
    for (const p of data.projects) {
      if (p.team_id == null) {
        hasNoTeam = true;
      } else if (!map.has(p.team_id)) {
        map.set(p.team_id, p.team_name || `Team #${p.team_id}`);
      }
    }
    const sorted = Array.from(map.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
    if (hasNoTeam) sorted.push({ id: "none", name: "(No team)" });
    return sorted;
  }, [data]);

  const { filteredUsers, filteredProjects, accessSet, stats } = useMemo(() => {
    if (!data) return { filteredUsers: [], filteredProjects: [], accessSet: new Set(), stats: {} };

    // Apply team filter first
    let teamFilteredProjects = data.projects;
    if (selectedTeamId === "none") {
      teamFilteredProjects = data.projects.filter((p) => p.team_id == null);
    } else if (selectedTeamId !== "all") {
      teamFilteredProjects = data.projects.filter((p) => p.team_id === selectedTeamId);
    }

    // Then apply search filter
    const q = search.trim().toLowerCase();
    const userMatch = q && data.users.some((u) => u.username.toLowerCase().includes(q));
    const projectMatch = q && teamFilteredProjects.some((p) => p.name.toLowerCase().includes(q));

    const usersToShow = !q ? data.users : (userMatch ? data.users.filter((u) => u.username.toLowerCase().includes(q)) : data.users);
    const projectsToShow = !q ? teamFilteredProjects : (projectMatch ? teamFilteredProjects.filter((p) => p.name.toLowerCase().includes(q)) : teamFilteredProjects);

    const set = new Set(data.assignments.map((a) => `${a.user_id}:${a.project_id}`));

    return {
      filteredUsers: usersToShow,
      filteredProjects: projectsToShow,
      accessSet: set,
      stats: {
        users: data.users.length,
        projects: teamFilteredProjects.length,
        assignments: data.assignments.length,
        admins: data.users.filter((u) => u.is_admin).length,
      },
    };
  }, [data, search, selectedTeamId]);

  if (loading) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[{ name: "Permissions", path: "/admin/permissions" }]} />
        </Box>
        <ContentBox>
          <Box sx={{ textAlign: "center", py: 8 }}><CircularProgress /></Box>
        </ContentBox>
      </Container>
    );
  }

  if (!data) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[{ name: "Permissions", path: "/admin/permissions" }]} />
        </Box>
        <ContentBox>
          <Card sx={{ p: 4, textAlign: "center" }}>
            <Typography color="text.secondary">Failed to load permission matrix</Typography>
          </Card>
        </ContentBox>
      </Container>
    );
  }

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Permissions", path: "/admin/permissions" }]} />
      </Box>

      <ContentBox>
        {/* Stats */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} md={3}><StatCard icon={<People />} value={stats.users} label="Users" color="linear-gradient(135deg, #42a5f5 0%, #1976d2 100%)" /></Grid>
          <Grid item xs={6} md={3}><StatCard icon={<AccountTree />} value={stats.projects} label="Projects" color="linear-gradient(135deg, #66bb6a 0%, #2e7d32 100%)" /></Grid>
          <Grid item xs={6} md={3}><StatCard icon={<Key />} value={stats.assignments} label="Direct Assignments" color="linear-gradient(135deg, #ffa726 0%, #e65100 100%)" /></Grid>
          <Grid item xs={6} md={3}><StatCard icon={<Star />} value={stats.admins} label="Admins" color="linear-gradient(135deg, #ef5350 0%, #c62828 100%)" /></Grid>
        </Grid>

        {/* Filters */}
        <Card elevation={0} sx={{ p: 2, mb: 3, borderRadius: 3, border: "1px solid", borderColor: "divider" }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4} md={3}>
              <TextField
                fullWidth size="small" select
                label="Team"
                value={selectedTeamId}
                onChange={(e) => setSelectedTeamId(e.target.value)}
              >
                <MenuItem value="all">All teams</MenuItem>
                {teams.map((t) => (
                  <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={8} md={9}>
              <TextField
                fullWidth size="small"
                placeholder="Search users or projects..."
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
        <Card elevation={0} sx={{ borderRadius: 3, border: "1px solid", borderColor: "divider", overflow: "hidden" }}>
          {filteredUsers.length === 0 || filteredProjects.length === 0 ? (
            <Box sx={{ p: 6, textAlign: "center", color: "text.secondary" }}>
              <Typography variant="body2">No matches found</Typography>
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
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  USER \ PROJECT
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
                      display: "flex", alignItems: "center", gap: 1, px: 1.5,
                      cursor: "pointer",
                      "&:hover": { bgcolor: "action.hover" },
                    }}
                  >
                    <Typography variant="body2" fontWeight={u.is_admin ? 600 : 400} noWrap sx={{ flex: 1 }}>
                      {u.username}
                    </Typography>
                    {u.is_admin && (
                      <Tooltip title="Platform admin (universal access)" arrow>
                        <Star sx={{ fontSize: 16, color: "#ffa726" }} />
                      </Tooltip>
                    )}
                    {u.is_restricted && (
                      <Tooltip title="Restricted (read-only)" arrow>
                        <Lock sx={{ fontSize: 14, color: "text.disabled" }} />
                      </Tooltip>
                    )}
                  </Box>

                  {/* Access cells */}
                  {filteredProjects.map((p, colIdx) => {
                    const hasAccess = u.is_admin || accessSet.has(`${u.id}:${p.id}`);
                    const isHover = hoverRow === rowIdx || hoverCol === colIdx;
                    return (
                      <Tooltip
                        key={p.id}
                        title={u.is_admin ? `${u.username} → ${p.name} (admin)` : hasAccess ? `${u.username} → ${p.name}` : ""}
                        arrow
                        placement="top"
                      >
                        <Box
                          onMouseEnter={() => { setHoverRow(rowIdx); setHoverCol(colIdx); }}
                          onMouseLeave={() => { setHoverRow(null); setHoverCol(null); }}
                          sx={{
                            height: ROW_HEIGHT,
                            borderBottom: "1px solid", borderColor: "divider",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            bgcolor: isHover ? "action.hover" : "transparent",
                          }}
                        >
                          {u.is_admin ? (
                            <Star sx={{ fontSize: 16, color: "#ffa72660" }} />
                          ) : hasAccess ? (
                            <Check sx={{ fontSize: 18, color: "#66bb6a" }} />
                          ) : null}
                        </Box>
                      </Tooltip>
                    );
                  })}
                </Box>
              ))}
            </Box>
          )}
        </Card>

        <Box sx={{ mt: 2, display: "flex", gap: 3, flexWrap: "wrap", color: "text.secondary" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Check sx={{ fontSize: 16, color: "#66bb6a" }} />
            <Typography variant="caption">Direct access</Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Star sx={{ fontSize: 16, color: "#ffa726" }} />
            <Typography variant="caption">Admin (universal access)</Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Lock sx={{ fontSize: 14, color: "text.disabled" }} />
            <Typography variant="caption">Restricted user</Typography>
          </Box>
        </Box>
      </ContentBox>
    </Container>
  );
}
