import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, Typography, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, Groups } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useTranslation } from "react-i18next";
import DataList from "app/components/DataList";
import api from "app/utils/api";
import { colors, rgba } from "app/utils/themeColors";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

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

  const columns = [
    {
      key: "name",
      label: t("teams.columns.name"),
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 32, height: 32, borderRadius: "8px",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: (theme) => theme.palette.mode === "dark" ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.08)",
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
      label: t("teams.columns.description"),
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
      label: t("teams.columns.users"),
      sortable: true,
      sortValue: (row) => (row.users || []).length,
      render: (row) => (row.users || []).length,
    },
    {
      key: "projects",
      label: t("teams.columns.projects"),
      sortable: true,
      sortValue: (row) => (row.projects || []).length,
      render: (row) => (row.projects || []).length,
    },
    {
      key: "role",
      label: t("teams.role.label"),
      sortable: true,
      sortValue: (row) => userRole(row),
      render: (row) => {
        const role = userRole(row);
        const styles = {
          platform_admin: { label: t("teams.role.platformAdmin"), color: colors.role.platformAdmin, bg: rgba.platformAdmin },
          team_admin: { label: t("teams.role.teamAdmin"), color: colors.role.teamAdmin, bg: rgba.teamAdmin },
          member: { label: t("teams.role.member"), color: colors.role.member, bg: rgba.member },
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
        <Breadcrumb routeSegments={[{ name: t("nav.teams"), path: "/teams" }]} />
      </Box>

      <DataList
        title={t("teams.title")}
        subtitle={t("teams.subtitle")}
        data={teams}
        columns={columns}
        searchKeys={["name", "description"]}
        onRowClick={(row) => navigate(`/team/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => navigate("/teams/new")}>
              {t("teams.new")}
            </Button>
          )
        }
        actions={(row) => {
          const role = userRole(row);
          const canEdit = role !== "member";
          return (
            <>
              <Tooltip title={t("teams.actions.view")}>
                <IconButton size="small" onClick={() => navigate(`/team/${row.id}`)}>
                  <Visibility fontSize="small" />
                </IconButton>
              </Tooltip>
              {canEdit && (
                <Tooltip title={t("teams.actions.edit")}>
                  <IconButton size="small" onClick={() => navigate(`/team/${row.id}/edit`)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
              {isAdmin && (
                <Tooltip title={t("teams.actions.delete")}>
                  <IconButton size="small" color="error" onClick={(e) => handleDelete(e, row)}>
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
