import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, Typography, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, Groups } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import DataList from "app/components/DataList";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function Teams() {
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
  }, []);

  const userRole = (team) => {
    if (isAdmin) return "platform_admin";
    if ((team.admins || []).some((a) => a.username === user.username)) return "team_admin";
    return "member";
  };

  const handleDelete = (e, team) => {
    e.stopPropagation();
    if (!window.confirm(`Delete team "${team.name}"?`)) return;
    api.delete(`/teams/${team.id}`, user.token)
      .then(() => {
        toast.success("Team deleted");
        fetchTeams();
      })
      .catch(() => {});
  };

  const columns = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 32, height: 32, borderRadius: "8px",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: (t) => t.palette.mode === "dark" ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.08)",
            }}
          >
            <Groups sx={{ fontSize: 18, color: "primary.main" }} />
          </Box>
          <Box sx={{ fontWeight: 500 }}>{row.name}</Box>
        </Box>
      ),
    },
    {
      key: "description",
      label: "Description",
      render: (row) => (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {row.description || "—"}
        </Typography>
      ),
    },
    {
      key: "users",
      label: "Users",
      sortable: true,
      sortValue: (row) => (row.users || []).length,
      render: (row) => (row.users || []).length,
    },
    {
      key: "projects",
      label: "Projects",
      sortable: true,
      sortValue: (row) => (row.projects || []).length,
      render: (row) => (row.projects || []).length,
    },
    {
      key: "role",
      label: "Your Role",
      sortable: true,
      sortValue: (row) => userRole(row),
      render: (row) => {
        const role = userRole(row);
        const styles = {
          platform_admin: { label: "Platform Admin", color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
          team_admin: { label: "Team Admin", color: "#6366f1", bg: "rgba(99,102,241,0.12)" },
          member: { label: "Member", color: "#6b7280", bg: "rgba(107,114,128,0.15)" },
        };
        const s = styles[role];
        return (
          <Chip
            label={s.label}
            size="small"
            sx={{ backgroundColor: s.bg, color: s.color, fontWeight: 600, fontSize: "0.7rem", height: 22 }}
          />
        );
      },
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Teams", path: "/teams" }]} />
      </Box>

      <DataList
        title="Teams"
        subtitle="Organize users, projects, and model access"
        data={teams}
        columns={columns}
        searchKeys={["name", "description"]}
        onRowClick={(row) => navigate(`/team/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => navigate("/teams/new")}>
              New Team
            </Button>
          )
        }
        actions={(row) => {
          const role = userRole(row);
          const canEdit = role !== "member";
          return (
            <>
              <Tooltip title="View">
                <IconButton size="small" onClick={() => navigate(`/team/${row.id}`)}>
                  <Visibility fontSize="small" />
                </IconButton>
              </Tooltip>
              {canEdit && (
                <Tooltip title="Edit">
                  <IconButton size="small" onClick={() => navigate(`/team/${row.id}/edit`)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              {isAdmin && (
                <Tooltip title="Delete">
                  <IconButton size="small" color="error" onClick={(e) => handleDelete(e, row)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </>
          );
        }}
        emptyMessage="No teams yet."
      />
    </Container>
  );
}
