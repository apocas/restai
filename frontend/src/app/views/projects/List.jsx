import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, Avatar, styled } from "@mui/material";
import { Add, SportsEsports, Visibility } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import sha256 from "crypto-js/sha256";
import BAvatar from "boring-avatars";
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

const TypeChip = ({ type }) => {
  const colors = {
    rag: { bg: "rgba(99,102,241,0.12)", color: "#6366f1" },
    agent: { bg: "rgba(16,185,129,0.12)", color: "#10b981" },
    block: { bg: "rgba(107,114,128,0.15)", color: "#6b7280" },
  };
  const style = colors[type] || { bg: "rgba(239,68,68,0.12)", color: "#ef4444" };
  return (
    <Chip
      label={type}
      size="small"
      sx={{
        backgroundColor: style.bg,
        color: style.color,
        fontWeight: 600,
        fontSize: "0.72rem",
        textTransform: "uppercase",
        height: 22,
      }}
    />
  );
};

export default function Projects() {
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
      label: "Name",
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
      label: "Type",
      sortable: true,
      render: (row) => <TypeChip type={row.type} />,
    },
    { key: "llm", label: "LLM", sortable: true },
    {
      key: "team",
      label: "Team",
      sortable: true,
      sortValue: (row) => row.team?.name || "",
      render: (row) => row.team?.name || "—",
    },
    {
      key: "users",
      label: "Users",
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
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }]} />
      </Box>

      <DataList
        title="Projects"
        subtitle="Your AI projects — RAG, agents, and visual blocks"
        data={projects}
        columns={columns}
        searchKeys={["name", "llm", "team.name", "type"]}
        filters={[
          {
            key: "type",
            label: "Type",
            options: [
              { value: "rag", label: "RAG" },
              { value: "agent", label: "Agent" },
              { value: "block", label: "Block" },
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
            New Project
          </Button>
        }
        actions={(row) => (
          <>
            <Tooltip title="View">
              <IconButton size="small" onClick={() => navigate(`/project/${row.id}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Playground">
              <IconButton size="small" onClick={() => navigate(`/project/${row.id}/playground`)}>
                <SportsEsports fontSize="small" color="primary" />
              </IconButton>
            </Tooltip>
          </>
        )}
        emptyMessage="No projects yet. Create one to get started."
      />
    </Container>
  );
}
