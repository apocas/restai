import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Dialog, DialogTitle, DialogContent, DialogActions,
  Divider, Grid, MenuItem, Select, styled, TextField, Typography,
} from "@mui/material";
import { SportsEsports, Code, ContentCopy, Bookmark, AddCircle } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const [projects, setProjects] = useState([]);
  const [typeFilter, setTypeFilter] = useState("all");
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneTarget, setCloneTarget] = useState(null);
  const [cloneName, setCloneName] = useState("");
  const [templates, setTemplates] = useState([]);
  const [teams, setTeams] = useState([]);
  const [llms, setLlms] = useState([]);
  const [instOpen, setInstOpen] = useState(false);
  const [instTarget, setInstTarget] = useState(null);
  const [instName, setInstName] = useState("");
  const [instTeam, setInstTeam] = useState("");
  const [instLlm, setInstLlm] = useState("");
  const [instSubmitting, setInstSubmitting] = useState(false);
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Library";
    api.get("/projects?filter=public", auth.user.token)
      .then((d) => setProjects((d.projects || []).reverse()))
      .catch(() => {});
    api.get("/templates", auth.user.token)
      .then((d) => setTemplates(d || []))
      .catch(() => {});
    api.get("/teams", auth.user.token)
      .then((d) => setTeams(d.teams || []))
      .catch(() => {});
    api.get("/info", auth.user.token)
      .then((d) => setLlms(d.llms || []))
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

  const openInstantiate = (template) => {
    setInstTarget(template);
    setInstName(template.name.toLowerCase().replace(/[^a-z0-9._:-]+/g, "-"));
    // Default team = first team the user belongs to
    setInstTeam(teams[0] ? teams[0].id : "");
    setInstLlm(template.suggested_llm || "");
    setInstOpen(true);
  };

  const handleInstantiate = () => {
    if (!instName.trim() || !instTarget || !instTeam || instSubmitting) return;
    setInstSubmitting(true);
    api.post(
      `/templates/${instTarget.id}/instantiate`,
      { name: instName.trim(), team_id: parseInt(instTeam), llm: instLlm || undefined },
      auth.user.token,
    )
      .then((response) => {
        setInstOpen(false);
        setInstTarget(null);
        navigate("/project/" + response.id);
      })
      .catch(() => {})
      .finally(() => setInstSubmitting(false));
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.projects"), path: "/projects" }, { name: t("nav.library"), path: "/projects/library" }]} />
      </Box>

      <ContentBox>
        {/* Header */}
        <Box sx={{ textAlign: "center", mb: 3 }}>
          <Typography variant="h4" fontWeight="bold" gutterBottom>
            {t("projects.library.title")}
          </Typography>
          <Typography variant="body1" color="text.secondary">
            {t("projects.library.subtitle")}
          </Typography>
        </Box>

        {/* Type filter */}
        <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mb: 3, flexWrap: "wrap" }}>
          {TYPE_FILTERS.map((tf) => (
            <Chip
              key={tf}
              label={tf === "all" ? t("common.all") : tf.charAt(0).toUpperCase() + tf.slice(1)}
              onClick={() => setTypeFilter(tf)}
              color={typeFilter === tf ? "primary" : "default"}
              variant={typeFilter === tf ? "filled" : "outlined"}
            />
          ))}
        </Box>

        {/* Project cards */}
        {filtered.length === 0 ? (
          <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
            <Typography variant="body1">{t("projects.library.noSharedProjects")}</Typography>
            <Typography variant="caption">{t("projects.library.markPublicHint")}</Typography>
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
                    {project.type !== "app" && (
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<SportsEsports />}
                        onClick={() => navigate("/project/" + project.id + "/playground")}
                      >
                        {t("projects.actions.playground")}
                      </Button>
                    )}
                    {project.type === "app" && (
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<Code />}
                        onClick={() => navigate("/project/" + project.id + "/builder")}
                      >
                        {t("projects.app.title", "App Builder")}
                      </Button>
                    )}
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
                      {t("projects.actions.clone")}
                    </Button>
                  </Box>
                </ProjectCard>
              </Grid>
            ))}
          </Grid>
        )}
        {/* Templates section */}
        <Box sx={{ mt: 6 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <Bookmark fontSize="small" color="primary" />
            <Typography variant="h6" fontWeight="bold">{t("projects.library.communityTemplates")}</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t("projects.library.communityTemplatesDesc")}
          </Typography>
          <Divider sx={{ mb: 2 }} />
          {templates.length === 0 ? (
            <Box sx={{ textAlign: "center", py: 4, color: "text.secondary" }}>
              <Typography variant="body2">{t("projects.library.noTemplates")}</Typography>
            </Box>
          ) : (
            <Grid container spacing={2}>
              {templates
                .filter((tpl2) => typeFilter === "all" || tpl2.project_type === typeFilter)
                .map((tpl) => (
                <Grid item xs={12} sm={6} md={4} key={tpl.id}>
                  <ProjectCard elevation={1}>
                    <Box sx={{ mb: 1 }}>
                      <Typography variant="subtitle1" fontWeight={600}>{tpl.name}</Typography>
                      <Box sx={{ display: "flex", gap: 0.5, mt: 0.5, flexWrap: "wrap" }}>
                        <ProjectTypeChip type={tpl.project_type} />
                        <Chip label={tpl.visibility} size="small" variant="outlined" />
                        {tpl.use_count > 0 && (
                          <Chip label={t("projects.library.uses", { count: tpl.use_count })} size="small" variant="outlined" />
                        )}
                      </Box>
                    </Box>
                    {tpl.description && (
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{
                          mb: 1, flexGrow: 1,
                          display: "-webkit-box",
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {tpl.description}
                      </Typography>
                    )}
                    {!tpl.description && <Box sx={{ flexGrow: 1 }} />}
                    {tpl.creator_username && (
                      <Typography variant="caption" color="text.secondary" sx={{ mb: 1 }}>
                        {t("projects.library.by", { author: tpl.creator_username })}
                      </Typography>
                    )}
                    <Box sx={{ display: "flex", gap: 1, mt: "auto", pt: 1 }}>
                      <Button
                        size="small" variant="contained" startIcon={<AddCircle />}
                        onClick={() => openInstantiate(tpl)}
                        disabled={teams.length === 0}
                      >
                        {t("projects.actions.useTemplate")}
                      </Button>
                    </Box>
                  </ProjectCard>
                </Grid>
              ))}
            </Grid>
          )}
        </Box>
      </ContentBox>

      {/* Instantiate dialog */}
      <Dialog open={instOpen} onClose={() => setInstOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("projects.template.instantiateTitle", { name: instTarget?.name || "" })}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label={t("projects.template.instantiateNewName")}
            value={instName}
            onChange={(e) => setInstName(e.target.value)}
            helperText={t("projects.template.instantiateNameHelp")}
          />
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">{t("projects.template.instantiateTeam")}</Typography>
            <Select
              fullWidth size="small" value={instTeam}
              onChange={(e) => setInstTeam(e.target.value)}
            >
              {teams.map((tm) => (
                <MenuItem key={tm.id} value={tm.id}>{tm.name}</MenuItem>
              ))}
            </Select>
          </Box>
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">
              {t("projects.template.instantiateLlm")} {instTarget?.suggested_llm && t("projects.template.instantiateSuggested", { name: instTarget.suggested_llm })}
            </Typography>
            <Select
              fullWidth size="small" value={instLlm}
              onChange={(e) => setInstLlm(e.target.value)}
            >
              <MenuItem value=""><em>{t("projects.template.instantiateUseSuggested")}</em></MenuItem>
              {llms.map((l) => (
                <MenuItem key={l.id} value={l.name}>{l.name}</MenuItem>
              ))}
            </Select>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInstOpen(false)}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleInstantiate} disabled={!instName.trim() || !instTeam || instSubmitting}>
            {instSubmitting ? t("projects.template.creating") : t("projects.template.create")}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Clone dialog */}
      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("projects.clone.title")}: {cloneTarget?.human_name || cloneTarget?.name}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label={t("projects.clone.newName")}
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            helperText={t("projects.clone.helper")}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloneOpen(false)}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleClone} disabled={!cloneName.trim()}>{t("projects.actions.clone")}</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
