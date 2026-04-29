import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, Avatar, styled } from "@mui/material";
import { Add, Code, SportsEsports, Visibility, Assignment } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import sha256 from "crypto-js/sha256";
import BAvatar from "boring-avatars";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import DataList from "app/components/DataList";
import api from "app/utils/api";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";
import ProjectTypeChip from "app/components/ProjectTypeChip";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function Projects() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState([]);
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Projects";
    api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects || []))
      .catch(() => {});
  }, []);

  const columns = [
    {
      key: "name",
      label: t("common.name"),
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <BAvatar
            name={row.name}
            size={32}
            variant="pixel"
            colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]}
          />
          <Box component="span" sx={{ fontWeight: 500 }}>{row.name}</Box>
        </Box>
      ),
    },
    {
      key: "type",
      label: t("common.type"),
      sortable: true,
      render: (row) => <ProjectTypeChip type={row.type} />,
    },
    { key: "llm", label: "LLM", sortable: true },
    {
      key: "team",
      label: t("common.team"),
      sortable: true,
      sortValue: (row) => row.team?.name || "",
      render: (row) => row.team?.name || "—",
    },
    {
      key: "users",
      label: t("nav.users"),
      render: (row) => {
        const users = row.users || [];
        return (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            {users.slice(0, 3).map((u) => (
              <Tooltip key={u.username} title={u.username}>
                <Avatar
                  src={`https://www.gravatar.com/avatar/${sha256(u.username)}`}
                  sx={{ width: 26, height: 26, border: "2px solid white", ml: -0.5 }}
                />
              </Tooltip>
            ))}
            {users.length > 3 && (
              <Tooltip title={users.slice(3).map((u) => u.username).join(", ")}>
                <Avatar sx={{ width: 26, height: 26, fontSize: "0.7rem", bgcolor: "grey.300" }}>
                  +{users.length - 3}
                </Avatar>
              </Tooltip>
            )}
          </Box>
        );
      },
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.projects"), path: "/projects" }]} />
      </Box>

      <DataList
        title={t("projects.title")}
        subtitle={t("projects.subtitle")}
        data={projects}
        columns={columns}
        searchKeys={["name", "llm", "team.name", "type"]}
        filters={[
          {
            key: "type",
            label: t("common.type"),
            options: [
              { value: "rag", label: t("projects.type.rag") },
              { value: "agent", label: t("projects.type.agent") },
              { value: "block", label: t("projects.type.block") },
            ],
          },
        ]}
        onRowClick={(row) => navigate(`/project/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => navigate("/projects/new")}
          >
            {t("projects.newProject")}
          </Button>
        }
        actions={(row) => (
          <>
            <Tooltip title={t("projects.actions.open")}>
              <IconButton size="small" onClick={() => navigate(`/project/${row.id}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {row.type !== "app" && (
              <Tooltip title={t("projects.actions.playground")}>
                <IconButton size="small" onClick={() => navigate(`/project/${row.id}/playground`)}>
                  <SportsEsports fontSize="small" color="primary" />
                </IconButton>
              </Tooltip>
            )}
            {row.type === "app" && (
              <Tooltip title={t("projects.app.title", "App Builder")}>
                <IconButton size="small" onClick={() => navigate(`/project/${row.id}/builder`)}>
                  <Code fontSize="small" color="primary" />
                </IconButton>
              </Tooltip>
            )}
          </>
        )}
        emptyState={{
          icon: Assignment,
          title: t("projects.emptyTitle"),
          message: t("projects.emptyMessage"),
          actionLabel: t("projects.newProject"),
          actionIcon: <Add fontSize="small" />,
          onAction: () => navigate("/projects/new"),
        }}
        emptyMessage={t("projects.emptyMessage")}
      />
    </Container>
  );
}
