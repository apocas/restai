import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Dialog, DialogTitle, DialogContent, DialogActions,
  Grid, styled, TextField, Typography,
} from "@mui/material";
import { SportsEsports, ContentCopy } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";
import ProjectTypeChip from "app/components/ProjectTypeChip";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const ProjectCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2.5),
  height: "100%",
  display: "flex",
  flexDirection: "column",
  transition: "all 0.2s ease",
  "&:hover": {
    transform: "translateY(-3px)",
    boxShadow: theme.shadows[8],
  },
}));

const TYPE_FILTERS = ["all", "agent", "rag", "block"];

export default function Library() {
  const [projects, setProjects] = useState([]);
  const [typeFilter, setTypeFilter] = useState("all");
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneTarget, setCloneTarget] = useState(null);
  const [cloneName, setCloneName] = useState("");
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Library";
    api.get("/projects?filter=public", auth.user.token)
      .then((d) => setProjects((d.projects || []).reverse()))
      .catch(() => {});
  }, []);

  const filtered = typeFilter === "all"
    ? projects
    : projects.filter((p) => p.type === typeFilter);

  const handleClone = () => {
    if (!cloneName.trim() || !cloneTarget) return;
    api.post("/projects/" + cloneTarget.id + "/clone", { name: cloneName.trim() }, auth.user.token)
      .then((response) => {
        setCloneOpen(false);
        setCloneName("");
        setCloneTarget(null);
        navigate("/project/" + response.project);
      })
      .catch(() => {});
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: "Library", path: "/projects/library" }]} />
      </Box>

      <ContentBox>
        {/* Header */}
        <Box sx={{ textAlign: "center", mb: 3 }}>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            Project Library
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Browse shared projects. Clone any project to customize it for your needs.
          </Typography>
        </Box>

        {/* Type filter */}
        <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mb: 3, flexWrap: "wrap" }}>
          {TYPE_FILTERS.map((t) => (
            <Chip
              key={t}
              label={t === "all" ? "All" : t.charAt(0).toUpperCase() + t.slice(1)}
              onClick={() => setTypeFilter(t)}
              color={typeFilter === t ? "primary" : "default"}
              variant={typeFilter === t ? "filled" : "outlined"}
            />
          ))}
        </Box>

        {/* Project cards */}
        {filtered.length === 0 ? (
          <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
            <Typography variant="body1">No shared projects found.</Typography>
            <Typography variant="caption">Mark a project as "Shared" in its settings to make it appear here.</Typography>
          </Box>
        ) : (
          <Grid container spacing={3}>
            {filtered.map((project) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={project.id}>
                <ProjectCard elevation={2}>
                  {/* Header */}
                  <Box sx={{ mb: 1 }}>
                    <Typography
                      variant="h6"
                      sx={{ cursor: "pointer", "&:hover": { color: "primary.main" } }}
                      onClick={() => navigate("/project/" + project.id)}
                    >
                      {project.human_name || project.name}
                    </Typography>
                    <Box sx={{ display: "flex", gap: 0.5, mt: 0.5, flexWrap: "wrap" }}>
                      <ProjectTypeChip type={project.type} />
                      {project.llm && (
                        <Chip label={project.llm} size="small" variant="outlined" />
                      )}
                    </Box>
                  </Box>

                  {/* Description */}
                  {project.human_description && (
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{
                        mb: 1,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {project.human_description}
                    </Typography>
                  )}

                  {/* System prompt preview */}
                  {project.system && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        fontStyle: "italic",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        mb: 1,
                        flexGrow: 1,
                      }}
                    >
                      {project.system}
                    </Typography>
                  )}

                  {!project.system && !project.human_description && (
                    <Box sx={{ flexGrow: 1 }} />
                  )}

                  {/* Actions */}
                  <Box sx={{ display: "flex", gap: 1, mt: "auto", pt: 1 }}>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<SportsEsports />}
                      onClick={() => navigate("/project/" + project.id + "/playground")}
                    >
                      Playground
                    </Button>
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<ContentCopy />}
                      onClick={() => {
                        setCloneTarget(project);
                        setCloneName((project.name || "") + "-clone");
                        setCloneOpen(true);
                      }}
                    >
                      Clone
                    </Button>
                  </Box>
                </ProjectCard>
              </Grid>
            ))}
          </Grid>
        )}
      </ContentBox>

      {/* Clone dialog */}
      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Clone: {cloneTarget?.human_name || cloneTarget?.name}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label="New project name"
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            helperText="A copy of this project will be created with all its settings."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloneOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleClone} disabled={!cloneName.trim()}>Clone</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
