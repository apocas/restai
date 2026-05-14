import { useState, useEffect, useMemo } from "react";
import {
  Avatar, Box, Button, Card, Grid, IconButton, Tooltip, styled,
} from "@mui/material";
import {
  Add, Edit, Delete, Visibility, People, Star, Person,
  LockPerson, VpnKey, Cloud, AccountCircle, Workspaces,
  ShieldOutlined,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import sha256 from "crypto-js/sha256";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import DataList from "app/components/DataList";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";

// Users = identity / directory / personnel → indigo-700 reads as
// "directory entry". Distinct from cron-amber, audit-indigo (lighter),
// logs-violet, routines-emerald, proxy-cyan, classifier-violet,
// guards-rose, evals-teal, gpu-orange, tools-cobalt, teams-fuchsia.
const ACCENT = "#4338ca";        // indigo-700
const ACCENT_DARK = "#3730a3";   // indigo-800
const ACCENT_SOFT = "rgba(67,56,202,0.10)";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

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

// Reusable mono pill with icon — same shape as Teams' RolePill.
function StatusPill({ icon: Icon, label, color, soft }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.85, py: 0.35,
        borderRadius: 0.75,
        backgroundColor: soft,
        border: `1px solid ${color}33`,
      }}
    >
      <Icon sx={{ fontSize: 12, color }} />
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.66rem",
          fontWeight: 700,
          letterSpacing: "0.06em",
          color,
          textTransform: "uppercase",
        }}
      >
        {label}
      </Box>
    </Box>
  );
}

// User row avatar with role-coloured ring (admin red, restricted amber,
// regular indigo). The Gravatar identicon stays as the avatar image.
function UserRowAvatar({ username, isAdmin, isRestricted }) {
  const ring = isAdmin
    ? "#dc2626"
    : isRestricted
      ? "#f59e0b"
      : ACCENT;
  return (
    <Box sx={{ position: "relative", display: "inline-block" }}>
      <Avatar
        src={`https://www.gravatar.com/avatar/${sha256(username)}?d=identicon`}
        sx={{
          width: 36, height: 36,
          border: `2px solid ${ring}`,
          boxShadow: `0 0 0 1px #fff, 0 4px 10px ${ring}33`,
        }}
      />
      {isAdmin && (
        <Box
          sx={{
            position: "absolute",
            bottom: -2, right: -2,
            width: 14, height: 14,
            borderRadius: "50%",
            background: "#dc2626",
            border: "2px solid #fff",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            "& svg": { fontSize: 8, color: "#fff" },
          }}
        >
          <Star />
        </Box>
      )}
    </Box>
  );
}

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDelete = (e, user) => {
    e.stopPropagation();
    if (!window.confirm(`Delete user "${user.username}"?`)) return;
    api.delete("/users/" + user.username, auth.user.token)
      .then(() => { toast.success(`Deleted ${user.username}`); fetchUsers(); })
      .catch(() => {});
  };

  const bulkDelete = async (rows) => {
    const names = rows.map((r) => r.username);
    if (!window.confirm(`Delete ${rows.length} user${rows.length === 1 ? "" : "s"}?\n\n${names.join(", ")}`)) return;
    let ok = 0, failed = 0;
    for (const name of names) {
      try { await api.delete("/users/" + name, auth.user.token, { silent: true }); ok++; }
      catch { failed++; }
    }
    if (ok) toast.success(`Deleted ${ok} user${ok === 1 ? "" : "s"}`);
    if (failed) toast.error(`Failed to delete ${failed} user${failed === 1 ? "" : "s"}`);
    fetchUsers();
  };

  const aggregates = useMemo(() => {
    const total = users.length;
    const admins = users.filter((u) => u.is_admin).length;
    const restricted = users.filter((u) => u.is_restricted).length;
    const sso = users.filter((u) => u.sso).length;
    const totalProjects = users.reduce((acc, u) => acc + (u.projects || []).length, 0);
    return { total, admins, restricted, sso, totalProjects };
  }, [users]);

  const columns = [
    {
      key: "username",
      label: "User",
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <UserRowAvatar
            username={row.username}
            isAdmin={row.is_admin}
            isRestricted={row.is_restricted}
          />
          <Box sx={{ minWidth: 0 }}>
            <Box
              sx={{
                fontWeight: 700,
                fontSize: "0.92rem",
                color: "text.primary",
                lineHeight: 1.15,
              }}
            >
              {row.username}
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
              USER/{String(row.id).padStart(4, "0")}
            </Box>
          </Box>
        </Box>
      ),
    },
    {
      key: "is_admin",
      label: "Role",
      sortable: true,
      sortValue: (row) => (row.is_admin ? 0 : 1),
      render: (row) =>
        row.is_admin
          ? <StatusPill icon={Star}    label="Admin" color="#dc2626" soft="rgba(220,38,38,0.10)" />
          : <StatusPill icon={Person}  label="User"  color="#64748b" soft="rgba(100,116,139,0.10)" />,
    },
    {
      key: "sso",
      label: "Auth",
      sortable: true,
      sortValue: (row) => (row.sso ? "sso" : "local"),
      render: (row) =>
        row.sso
          ? <StatusPill icon={Cloud}        label="SSO"   color="#0891b2" soft="rgba(8,145,178,0.10)" />
          : <StatusPill icon={AccountCircle} label="Local" color="#475569" soft="rgba(71,85,105,0.10)" />,
    },
    {
      key: "is_restricted",
      label: "Access",
      sortable: true,
      sortValue: (row) => (row.is_restricted ? 1 : 0),
      render: (row) =>
        row.is_restricted
          ? <StatusPill icon={LockPerson} label="Read-only"  color="#f59e0b" soft="rgba(245,158,11,0.10)" />
          : <StatusPill icon={VpnKey}     label="Read/Write" color="#10b981" soft="rgba(16,185,129,0.10)" />,
    },
    {
      key: "projects",
      label: "Projects",
      sortable: true,
      sortValue: (row) => (row.projects || []).length,
      render: (row) => <CountChip value={(row.projects || []).length} icon={Workspaces} color={ACCENT} />,
    },
  ];

  return (
    <Container>
      <PageHero
        icon={<People sx={{ color: "#fff" }} />}
        eyebrow="DIRECTORY/USERS"
        title={t("users.title") || "Users"}
        subtitle={t("users.subtitle")}
        stats={[
          { glyph: "◆", color: "#a5b4fc", label: `${aggregates.total} total` },
          { glyph: "★", color: "#fca5a5", label: `${aggregates.admins} admin${aggregates.admins === 1 ? "" : "s"}` },
          { glyph: "⌬", color: "#fcd34d", label: `${aggregates.restricted} restricted` },
          ...(aggregates.sso > 0 ? [{ glyph: "☁", color: "#7dd3fc", label: `${aggregates.sso} SSO` }] : []),
        ]}
        actions={
          isAdmin && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => navigate("/users/new")}
              sx={{
                textTransform: "none",
                fontWeight: 700,
                background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                boxShadow: `0 4px 14px ${ACCENT}66`,
                "&:hover": {
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #312e81 100%)`,
                  boxShadow: `0 6px 18px ${ACCENT}88`,
                },
              }}
            >
              New User
            </Button>
          )
        }
      />

      <Grid container spacing={2} sx={{ mt: 1, mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<People />}
            label="Total accounts"
            value={aggregates.total}
            accent={ACCENT}
            sub={`${aggregates.totalProjects} project link${aggregates.totalProjects === 1 ? "" : "s"}`}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<ShieldOutlined />}
            label="Platform admins"
            value={aggregates.admins}
            accent="#dc2626"
            sub={aggregates.total ? `${((aggregates.admins / aggregates.total) * 100).toFixed(0)}% of accounts` : "—"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<LockPerson />}
            label="Restricted"
            value={aggregates.restricted}
            accent="#f59e0b"
            sub={aggregates.restricted ? "read-only access" : "all read+write"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Cloud />}
            label="SSO accounts"
            value={aggregates.sso}
            accent="#0891b2"
            sub={`${aggregates.total - aggregates.sso} local`}
          />
        </Grid>
      </Grid>

      <DataList
        data={users}
        columns={columns}
        searchKeys={["username"]}
        filters={[
          {
            key: "is_admin",
            label: "Role",
            options: [
              { value: "true",  label: "Admin" },
              { value: "false", label: "User" },
            ],
            getValue: (row) => (row.is_admin ? "true" : "false"),
          },
          {
            key: "is_restricted",
            label: "Access",
            options: [
              { value: "true",  label: "Read-only" },
              { value: "false", label: "Read/Write" },
            ],
            getValue: (row) => (row.is_restricted ? "true" : "false"),
          },
          {
            key: "sso",
            label: "Auth",
            options: [
              { value: "sso",   label: "SSO" },
              { value: "local", label: "Local" },
            ],
            getValue: (row) => (row.sso ? "sso" : "local"),
          },
        ]}
        onRowClick={(row) => navigate(`/user/${row.username}`)}
        rowKey={(row) => row.username}
        defaultSort={{ key: "id", direction: "desc" }}
        actions={(row) => (
          <>
            <Tooltip title="View" arrow>
              <IconButton
                size="small"
                onClick={() => navigate(`/user/${row.username}`)}
                sx={{ color: ACCENT, "&:hover": { backgroundColor: ACCENT_SOFT } }}
              >
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title="Edit" arrow>
                  <IconButton
                    size="small"
                    onClick={() => navigate(`/user/${row.username}`)}
                    sx={{ color: "#7c3aed", "&:hover": { backgroundColor: "rgba(124,58,237,0.10)" } }}
                  >
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Delete" arrow>
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
