import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, Avatar, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, People } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import sha256 from "crypto-js/sha256";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import DataList from "app/components/DataList";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { colors } from "app/utils/themeColors";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function Users() {
  const { t } = useTranslation();
  const [users, setUsers] = useState([]);
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;

  const fetchUsers = () => {
    api.get("/users", auth.user.token)
      .then((d) => setUsers(d.users || []))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Users";
    fetchUsers();
  }, []);

  const handleDelete = (e, user) => {
    e.stopPropagation();
    if (!window.confirm(`Delete user "${user.username}"?`)) return;
    api.delete("/users/" + user.username, auth.user.token)
      .then(() => {
        toast.success(`Deleted ${user.username}`);
        fetchUsers();
      })
      .catch(() => {});
  };

  const bulkDelete = async (rows) => {
    const names = rows.map((r) => r.username);
    if (!window.confirm(`Delete ${rows.length} user${rows.length === 1 ? "" : "s"}?\n\n${names.join(", ")}`)) return;
    // Fire deletes sequentially to avoid rate-limit pile-ups and keep
    // per-row toast counts readable.
    let ok = 0, failed = 0;
    for (const name of names) {
      try {
        await api.delete("/users/" + name, auth.user.token, { silent: true });
        ok++;
      } catch {
        failed++;
      }
    }
    if (ok) toast.success(`Deleted ${ok} user${ok === 1 ? "" : "s"}`);
    if (failed) toast.error(`Failed to delete ${failed} user${failed === 1 ? "" : "s"}`);
    fetchUsers();
  };

  const columns = [
    {
      key: "username",
      label: "User",
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Avatar
            src={`https://www.gravatar.com/avatar/${sha256(row.username)}`}
            sx={{ width: 32, height: 32 }}
          />
          <Box sx={{ fontWeight: 500 }}>{row.username}</Box>
        </Box>
      ),
    },
    {
      key: "is_admin",
      label: "Role",
      sortable: true,
      sortValue: (row) => (row.is_admin ? 0 : 1),
      render: (row) => (
        <Chip
          label={row.is_admin ? "Admin" : "User"}
          size="small"
          sx={{
            backgroundColor: row.is_admin ? "rgba(239,68,68,0.12)" : "rgba(107,114,128,0.15)",
            color: row.is_admin ? colors.status.error : colors.status.muted,
            fontWeight: 600,
            fontSize: "0.72rem",
            height: 22,
          }}
        />
      ),
    },
    {
      key: "sso",
      label: "Auth",
      sortable: true,
      sortValue: (row) => (row.sso ? "sso" : "local"),
      render: (row) => (
        <Chip
          label={row.sso ? "SSO" : "Local"}
          size="small"
          variant="outlined"
          sx={{ fontSize: "0.72rem", height: 22 }}
        />
      ),
    },
    {
      key: "is_restricted",
      label: "Access",
      sortable: true,
      sortValue: (row) => (row.is_restricted ? 1 : 0),
      render: (row) => (
        <Chip
          label={row.is_restricted ? "Read-only" : "Read/Write"}
          size="small"
          sx={{
            backgroundColor: row.is_restricted ? "rgba(245,158,11,0.12)" : "rgba(16,185,129,0.12)",
            color: row.is_restricted ? colors.status.warning : colors.status.success,
            fontWeight: 600,
            fontSize: "0.72rem",
            height: 22,
          }}
        />
      ),
    },
    {
      key: "projects",
      label: "Projects",
      sortable: true,
      sortValue: (row) => (row.projects || []).length,
      render: (row) => (row.projects || []).length,
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.users"), path: "/users" }]} />
      </Box>

      <DataList
        title={t("users.title")}
        subtitle={t("users.subtitle")}
        data={users}
        columns={columns}
        searchKeys={["username"]}
        filters={[
          {
            key: "is_admin",
            label: "Role",
            options: [
              { value: "true", label: "Admin" },
              { value: "false", label: "User" },
            ],
            getValue: (row) => (row.is_admin ? "true" : "false"),
          },
          {
            key: "is_restricted",
            label: "Access",
            options: [
              { value: "true", label: "Read-only" },
              { value: "false", label: "Read/Write" },
            ],
            getValue: (row) => (row.is_restricted ? "true" : "false"),
          },
        ]}
        onRowClick={(row) => navigate(`/user/${row.username}`)}
        rowKey={(row) => row.username}
        defaultSort={{ key: "username", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => navigate("/users/new")}
            >
              New User
            </Button>
          )
        }
        actions={(row) => (
          <>
            <Tooltip title="View">
              <IconButton size="small" onClick={() => navigate(`/user/${row.username}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title="Edit">
                  <IconButton size="small" onClick={() => navigate(`/user/${row.username}`)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Delete">
                  <IconButton size="small" color="error" onClick={(e) => handleDelete(e, row)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </>
        )}
        bulkActions={isAdmin ? [
          { label: "Delete", icon: <Delete fontSize="small" />, color: "error", onClick: bulkDelete },
        ] : []}
        emptyState={{
          icon: People,
          title: "No users yet",
          message: "Platform users show up here. Add a first admin or teammate to get started.",
          actionLabel: isAdmin ? "New User" : undefined,
          actionIcon: <Add fontSize="small" />,
          onAction: isAdmin ? () => navigate("/users/new") : undefined,
        }}
        emptyMessage="No users yet."
      />
    </Container>
  );
}
