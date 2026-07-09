import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Dialog, DialogTitle, DialogContent, DialogActions,
  Divider, Grid, MenuItem, Select, styled, TextField, Tooltip, Typography,
} from "@mui/material";
import { SportsEsports, ContentCopy, Bookmark, AddCircle } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import BAvatar from "boring-avatars";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import api from "app/utils/api";
import ProjectTypeChip from "app/components/ProjectTypeChip";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

// Type-coded card. Each project type owns an accent (rag indigo, agent
// emerald, block grey, app cyan). At rest the card is a plain white
// surface; on hover the border picks up the accent, the rail brightens,
// and a soft type-tinted glow lifts the card -3px. Same vocabulary as
// the AIHero (cyan sweep, restrained motion) — but applied per card so
// the grid reads as a small map of project types.
const ProjectCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  position: "relative",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  borderRadius: 14,
  border: "1px solid",
  borderColor: "rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease",
  // Top accent rail — 4px coloured stripe with a faint cyan sweep that
  // becomes visible on hover. Positioned so it sits flush at the top
  // edge.
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
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    transform: "translateY(-3px)",
    borderColor: `${accent}66`,
    boxShadow: `0 18px 36px ${accent}1f, 0 4px 10px rgba(15,23,42,0.06)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

const TYPE_FILTERS = ["all", "agent", "rag", "block"];

// Boring-avatars colour palettes per type — same hue family as the
// rail / glow so the avatar reads as part of the type identity.
const AVATAR_PALETTES = {
  rag:   ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#1e1b4b"],
  agent: ["#10b981", "#34d399", "#6ee7b7", "#a7f3d0", "#064e3b"],
  block: ["#6b7280", "#9ca3af", "#d1d5db", "#e5e7eb", "#1f2937"],
  app:   ["#0891b2", "#22d3ee", "#67e8f9", "#a5f3fc", "#164e63"],
};

function getAccent(type) {
  return PROJECT_TYPE_COLORS[type]?.color || "#475569";
}

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
      <PageHero
        icon={<Bookmark sx={{ color: "#fff" }} />}
        eyebrow="LIBRARY"
        title="Templates Library"
        subtitle="Community templates you can clone into a new project."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${projects.length} shared` },
          { glyph: "⚡", color: "#7dd3fc", label: `${templates.length} templates` },
        ]}
        compact
      />

      <ContentBox>
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
                <ProjectCard elevation={0} accent={getAccent(project.type)}>
                  {/* Body — title row with avatar + chip strip + descrip */}
                  <Box sx={{ p: 2.25, pt: 2.5, pb: 1.5, flex: 1, display: "flex", flexDirection: "column", gap: 1.25 }}>
                    <Box sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                      <Box sx={{ flexShrink: 0, mt: 0.25 }}>
                        <BAvatar
                          name={project.name || String(project.id)}
                          size={42}
                          variant="pixel"
                          colors={AVATAR_PALETTES[project.type] || AVATAR_PALETTES.block}
                          square
                        />
                      </Box>
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Tooltip title={project.human_name || project.name} placement="top-start">
                          <Typography
                            variant="subtitle1"
                            sx={{
                              fontWeight: 700,
                              lineHeight: 1.25,
                              color: "text.primary",
                              cursor: "pointer",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              "&:hover": { color: getAccent(project.type) },
                              transition: "color 0.15s ease",
                            }}
                            onClick={() => navigate("/project/" + project.id)}
                          >
                            {project.human_name || project.name}
                          </Typography>
                        </Tooltip>
                        <Typography
                          variant="caption"
                          sx={{
                            color: "text.disabled",
                            fontFamily: FONT_MONO,
                            fontSize: "0.65rem",
                            letterSpacing: "0.05em",
                          }}
                        >
                          PROJECT/{String(project.id).padStart(4, "0")}
                        </Typography>
                      </Box>
                    </Box>

                    {/* Type + LLM strip */}
                    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center" }}>
                      <ProjectTypeChip type={project.type} />
                      {project.llm && (
                        <Chip
                          label={project.llm}
                          size="small"
                          variant="outlined"
                          sx={{
                            height: 22,
                            fontSize: "0.7rem",
                            fontFamily: FONT_MONO,
                            fontWeight: 500,
                            borderColor: "rgba(15,23,42,0.12)",
                            color: "text.secondary",
                            "& .MuiChip-label": { px: 1 },
                          }}
                        />
                      )}
                    </Box>

                    {/* Description (or muted placeholder so cards line up) */}
                    <Typography
                      variant="body2"
                      sx={{
                        color: project.human_description ? "text.secondary" : "text.disabled",
                        fontStyle: project.human_description ? "normal" : "italic",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        minHeight: "2.6em",
                        lineHeight: 1.45,
                      }}
                    >
                      {project.human_description || "No description provided."}
                    </Typography>

                    {/* System prompt — terminal-style mini-block */}
                    {project.system ? (
                      <Box
                        sx={{
                          mt: 0.5,
                          flex: 1,
                          minHeight: 64,
                          background: `linear-gradient(180deg, ${getAccent(project.type)}0a, rgba(15,23,42,0.025))`,
                          border: `1px solid ${getAccent(project.type)}22`,
                          borderRadius: 1.5,
                          p: 1.25,
                          position: "relative",
                          overflow: "hidden",
                        }}
                      >
                        <Typography
                          sx={{
                            position: "absolute",
                            top: 4,
                            right: 6,
                            fontFamily: FONT_MONO,
                            fontSize: "0.55rem",
                            letterSpacing: "0.18em",
                            color: getAccent(project.type),
                            opacity: 0.7,
                            fontWeight: 600,
                          }}
                        >
                          PROMPT
                        </Typography>
                        <Box
                          sx={{
                            display: "-webkit-box",
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                            fontFamily: FONT_MONO,
                            fontSize: "0.72rem",
                            lineHeight: 1.55,
                            color: "text.secondary",
                            mt: 1.5,
                            "&::before": {
                              content: '"> "',
                              color: getAccent(project.type),
                              fontWeight: 700,
                            },
                          }}
                        >
                          {project.system.replace(/\s+/g, " ").trim()}
                        </Box>
                      </Box>
                    ) : (
                      <Box sx={{ flex: 1, minHeight: 0 }} />
                    )}
                  </Box>

                  {/* Footer — actions strip */}
                  <Box
                    sx={{
                      px: 2.25,
                      py: 1.25,
                      borderTop: "1px solid rgba(15,23,42,0.06)",
                      backgroundColor: "rgba(15,23,42,0.015)",
                      display: "flex",
                      gap: 1,
                      alignItems: "center",
                    }}
                  >
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={<SportsEsports />}
                      onClick={() => navigate("/project/" + project.id + "/playground")}
                      sx={{
                        textTransform: "none",
                        fontWeight: 600,
                        color: getAccent(project.type),
                        borderColor: `${getAccent(project.type)}55`,
                        "&:hover": {
                          borderColor: getAccent(project.type),
                          backgroundColor: `${getAccent(project.type)}0c`,
                        },
                      }}
                    >
                      {t("projects.actions.playground")}
                    </Button>
                    <Box sx={{ flex: 1 }} />
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<ContentCopy />}
                      onClick={() => {
                        setCloneTarget(project);
                        setCloneName((project.name || "") + "-clone");
                        setCloneOpen(true);
                      }}
                      sx={{
                        textTransform: "none",
                        fontWeight: 600,
                        backgroundColor: getAccent(project.type),
                        boxShadow: "none",
                        "&:hover": {
                          backgroundColor: getAccent(project.type),
                          opacity: 0.9,
                          boxShadow: `0 4px 12px ${getAccent(project.type)}55`,
                        },
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
                  <ProjectCard elevation={0} accent={getAccent(tpl.project_type)}>
                    <Box sx={{ p: 2.25, pt: 2.5, pb: 1.5, flex: 1, display: "flex", flexDirection: "column", gap: 1.25 }}>
                      <Box sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                        <Box sx={{ flexShrink: 0, mt: 0.25 }}>
                          <BAvatar
                            name={tpl.name || String(tpl.id)}
                            size={42}
                            variant="pixel"
                            colors={AVATAR_PALETTES[tpl.project_type] || AVATAR_PALETTES.block}
                            square
                          />
                        </Box>
                        <Box sx={{ minWidth: 0, flex: 1 }}>
                          <Tooltip title={tpl.name} placement="top-start">
                            <Typography
                              variant="subtitle1"
                              sx={{
                                fontWeight: 700,
                                lineHeight: 1.25,
                                color: "text.primary",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {tpl.name}
                            </Typography>
                          </Tooltip>
                          <Typography
                            variant="caption"
                            sx={{
                              color: "text.disabled",
                              fontFamily: FONT_MONO,
                              fontSize: "0.65rem",
                              letterSpacing: "0.05em",
                            }}
                          >
                            TEMPLATE/{String(tpl.id).padStart(4, "0")}
                          </Typography>
                        </Box>
                      </Box>

                      {/* Type + visibility + uses */}
                      <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center" }}>
                        <ProjectTypeChip type={tpl.project_type} />
                        <Chip
                          label={tpl.visibility}
                          size="small"
                          variant="outlined"
                          sx={{
                            height: 22, fontSize: "0.7rem", fontWeight: 500,
                            textTransform: "uppercase",
                            letterSpacing: "0.05em",
                            borderColor: "rgba(15,23,42,0.12)",
                            color: "text.secondary",
                            "& .MuiChip-label": { px: 1 },
                          }}
                        />
                        {tpl.use_count > 0 && (
                          <Chip
                            label={t("projects.library.uses", { count: tpl.use_count })}
                            size="small"
                            variant="outlined"
                            sx={{
                              height: 22, fontSize: "0.7rem", fontWeight: 500,
                              fontFamily: FONT_MONO,
                              borderColor: `${getAccent(tpl.project_type)}55`,
                              color: getAccent(tpl.project_type),
                              "& .MuiChip-label": { px: 1 },
                            }}
                          />
                        )}
                      </Box>

                      <Typography
                        variant="body2"
                        sx={{
                          color: tpl.description ? "text.secondary" : "text.disabled",
                          fontStyle: tpl.description ? "normal" : "italic",
                          display: "-webkit-box",
                          WebkitLineClamp: 3,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                          flex: 1,
                          lineHeight: 1.45,
                          minHeight: "3.9em",
                        }}
                      >
                        {tpl.description || "No description provided."}
                      </Typography>

                      {/* Author byline */}
                      {tpl.creator_username && (
                        <Typography
                          variant="caption"
                          sx={{
                            color: "text.disabled",
                            fontFamily: FONT_MONO,
                            fontSize: "0.65rem",
                            letterSpacing: "0.05em",
                          }}
                        >
                          {t("projects.library.by", { author: tpl.creator_username })}
                        </Typography>
                      )}
                    </Box>

                    <Box
                      sx={{
                        px: 2.25, py: 1.25,
                        borderTop: "1px solid rgba(15,23,42,0.06)",
                        backgroundColor: "rgba(15,23,42,0.015)",
                        display: "flex",
                        gap: 1,
                        alignItems: "center",
                        justifyContent: "flex-end",
                      }}
                    >
                      <Button
                        size="small"
                        variant="contained"
                        startIcon={<AddCircle />}
                        onClick={() => openInstantiate(tpl)}
                        disabled={teams.length === 0}
                        sx={{
                          textTransform: "none",
                          fontWeight: 600,
                          backgroundColor: getAccent(tpl.project_type),
                          boxShadow: "none",
                          "&:hover": {
                            backgroundColor: getAccent(tpl.project_type),
                            opacity: 0.9,
                            boxShadow: `0 4px 12px ${getAccent(tpl.project_type)}55`,
                          },
                        }}
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
