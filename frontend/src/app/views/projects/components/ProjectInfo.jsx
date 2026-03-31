import { useState, useEffect } from "react";
import {
  Avatar, Box, Button, Card, Chip, Divider, Dialog, DialogTitle, DialogContent,
  DialogActions, Grid, IconButton, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Edit, Delete, Code, Article, SportsEsports, ViewInAr, Science, Security,
  ContentCopy, ClearAll, Speed, Shield, Cached, Groups, Psychology,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import sha256 from "crypto-js/sha256";
import BAvatar from "boring-avatars";
import api from "app/utils/api";

const HeroCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(3),
  marginBottom: theme.spacing(2),
}));

const ActionBar = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(0.5),
  flexWrap: "wrap",
  marginTop: theme.spacing(2),
}));

const MetaItem = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: 4,
  color: theme.palette.text.secondary,
  fontSize: "0.85rem",
}));

const TYPE_COLORS = {
  inference: "primary",
  rag: "success",
  agent: "warning",
  block: "default",
};

export default function ProjectInfo({ project, projects, info }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [health, setHealth] = useState(null);

  useEffect(() => {
    if (project.id) {
      api.get("/projects/health", auth.user.token, { silent: true })
        .then((data) => {
          const h = (data || []).find((x) => x.project_id === project.id);
          if (h) setHealth(h);
        })
        .catch(() => {});
    }
  }, [project.id]);

  const handleClone = () => {
    if (!cloneName.trim()) return;
    api.post("/projects/" + project.id + "/clone", { name: cloneName.trim() }, auth.user.token)
      .then((response) => {
        setCloneOpen(false);
        setCloneName("");
        navigate("/project/" + response.project);
      })
      .catch(() => {});
  };

  const handleDelete = () => {
    if (window.confirm("Are you sure you want to delete " + project.name + "?")) {
      api.delete("/projects/" + project.id, auth.user.token)
        .then(() => navigate("/projects"))
        .catch(() => {});
    }
  };

  return (
    <>
      <HeroCard elevation={3}>
        {/* Header Row: Avatar + Name + Type + Health */}
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, flexWrap: "wrap" }}>
          <BAvatar name={project.name} size={64} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]} />

          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography variant="h5" fontWeight="bold">{project.human_name || project.name}</Typography>
              <Chip label={project.type} size="small" color={TYPE_COLORS[project.type] || "default"} />
              {health && (
                <Tooltip
                  title={
                    <Box>
                      <div><strong>Health: {health.health}/100</strong></div>
                      <div>Requests (7d): {health.requests_7d || 0}</div>
                      <div>Avg Latency: {health.avg_latency ? health.avg_latency + "ms" : "N/A"}</div>
                      <div>Guard Block Rate: {health.guard_block_rate !== null ? (health.guard_block_rate * 100).toFixed(1) + "%" : "N/A"}</div>
                      <div>Eval Score: {health.eval_score !== null ? (health.eval_score * 100).toFixed(0) + "%" : "N/A"}</div>
                    </Box>
                  }
                >
                  <Chip
                    label={`Health: ${health.health}`}
                    size="small"
                    color={health.health >= 70 ? "success" : health.health >= 40 ? "warning" : "error"}
                    variant="outlined"
                    sx={{ fontWeight: "bold" }}
                  />
                </Tooltip>
              )}
            </Box>

            {project.human_description && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {project.human_description}
              </Typography>
            )}

            {/* Metadata pills */}
            <Box sx={{ display: "flex", gap: 1, mt: 1.5, flexWrap: "wrap", alignItems: "center" }}>
              {project.llm && (
                <Chip icon={<Psychology />} label={project.llm} size="small" variant="outlined" />
              )}
              {project.options?.fallback_llm && (
                <Chip label={`Fallback: ${project.options.fallback_llm}`} size="small" variant="outlined" />
              )}
              {project.team && (
                <Chip icon={<Groups />} label={project.team.name} size="small" variant="outlined" />
              )}
              {project.guard && (
                <Chip icon={<Shield />} label={`Guard: ${project.guard}`} size="small" variant="outlined" color="warning" />
              )}
              {project.options?.guard_output && (
                <Chip icon={<Shield />} label={`Output Guard: ${project.options.guard_output}`} size="small" variant="outlined" color="warning" />
              )}
              {project.options?.cache && (
                <Chip icon={<Cached />} label="Cache" size="small" variant="outlined" color="info" />
              )}
              {project.options?.rate_limit && (
                <Chip icon={<Speed />} label={`${project.options.rate_limit} req/min`} size="small" variant="outlined" />
              )}
              {project.public && (
                <Chip label="Shared" size="small" color="info" />
              )}
            </Box>

            {/* System prompt preview */}
            {project.system && project.type !== "block" && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  mt: 1,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  fontStyle: "italic",
                }}
              >
                {project.system}
              </Typography>
            )}

            {/* Users */}
            {project.users && project.users.length > 0 && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>Users:</Typography>
                {project.users.slice(0, 5).map((u, i) => (
                  <Tooltip key={u.username || i} title={u.username}>
                    <Avatar src={"https://www.gravatar.com/avatar/" + sha256(u.username || "")} sx={{ width: 24, height: 24 }} />
                  </Tooltip>
                ))}
                {project.users.length > 5 && (
                  <Chip label={`+${project.users.length - 5}`} size="small" />
                )}
              </Box>
            )}
          </Box>
        </Box>

        {/* Action Toolbar */}
        <ActionBar>
          <Tooltip title="Edit">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/edit")}>
              <Edit fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Playground">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/playground")}>
              <SportsEsports fontSize="small" />
            </IconButton>
          </Tooltip>
          {project.type === "block" && (
            <Tooltip title="IDE">
              <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/ide")}>
                <ViewInAr fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Evals">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/evals")}>
              <Science fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Guards">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/guards")}>
              <Security fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Logs">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/logs")}>
              <Article fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="API">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/api")}>
              <Code fontSize="small" />
            </IconButton>
          </Tooltip>

          <Box sx={{ flex: 1 }} />

          {project.options?.cache && (
            <Tooltip title="Clear Cache">
              <IconButton
                size="small"
                color="warning"
                onClick={() => {
                  api.delete("/projects/" + project.id + "/cache", auth.user.token).catch(() => {});
                }}
              >
                <ClearAll fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Clone">
            <IconButton size="small" onClick={() => { setCloneName(project.name + "-copy"); setCloneOpen(true); }}>
              <ContentCopy fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete">
            <IconButton size="small" color="error" onClick={handleDelete}>
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
        </ActionBar>
      </HeroCard>

      {/* Clone dialog */}
      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Clone Project</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label="New project name"
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            helperText="Settings, eval datasets, and prompt versions will be cloned."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloneOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleClone} disabled={!cloneName.trim()}>Clone</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
