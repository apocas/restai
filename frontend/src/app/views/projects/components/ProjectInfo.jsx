import { useState } from "react";
import {
  Avatar, Box, Button, Card, Chip, Dialog, DialogTitle, DialogContent,
  DialogActions, IconButton, MenuItem, Select, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import ProjectTypeChip from "app/components/ProjectTypeChip";
import {
  Edit, Delete, Code, Article, SportsEsports, ViewInAr, Science, Security,
  ContentCopy, Speed, Shield, Groups, Psychology, BookmarkAdd,
} from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import sha256 from "crypto-js/sha256";
import BAvatar from "boring-avatars";
import api from "app/utils/api";
import { shimmer, sweep, pulse, blink } from "app/components/page/pageStyles";

// Project landing-page hero. Same navy/cyan gradient mesh as the
// dashboard AIHero / PageHero so the entire app reads as one family —
// you land on /project/{id} and instantly feel the same "alive AI
// platform" energy you got on /home.
const HeroCard = styled(Card)(({ theme }) => ({
  position: "relative",
  padding: theme.spacing(4),
  marginBottom: theme.spacing(3),
  borderRadius: 20,
  overflow: "hidden",
  color: "#fff",
  background: `
    radial-gradient(at 20% 20%, rgba(25,118,210,0.95) 0px, transparent 55%),
    radial-gradient(at 85% 15%, rgba(14,165,233,0.90) 0px, transparent 55%),
    radial-gradient(at 75% 85%, rgba(6,182,212,0.80) 0px, transparent 55%),
    radial-gradient(at 10% 90%, rgba(56,189,248,0.70) 0px, transparent 55%),
    linear-gradient(135deg, #0b1d3a 0%, #0f2c5a 100%)
  `,
  backgroundSize: "200% 200%, 200% 200%, 200% 200%, 200% 200%, 100% 100%",
  animation: `${shimmer} 20s ease-in-out infinite`,
  [theme.breakpoints.down("md")]: { padding: theme.spacing(3) },
  // Subtle grain — same trick AIHero uses for texture.
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
    backgroundImage:
      "radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px)",
    backgroundSize: "4px 4px",
    mixBlendMode: "overlay",
    opacity: 0.5,
  },
  // Animated cyan sweep along the top edge — heartbeat signal that the
  // platform is "live and connected".
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background:
      "linear-gradient(90deg, transparent, rgba(125,211,252,0.55), rgba(56,189,248,0.55), transparent)",
    animation: `${sweep} 6s ease-in-out infinite`,
    pointerEvents: "none",
    zIndex: 2,
  },
  "& > *": { position: "relative", zIndex: 1 },
}));

const ActionBar = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(0.5),
  flexWrap: "wrap",
  marginTop: theme.spacing(3),
  paddingTop: theme.spacing(2),
  borderTop: "1px solid rgba(255,255,255,0.12)",
}));

// Translucent pill style for chips inside the navy hero. Same vocabulary
// as the AIHero StatChip — backdrop-blur over a hint of white, white
// text + icon, soft border.
const pillSx = {
  backgroundColor: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.92)",
  backdropFilter: "blur(12px)",
  fontWeight: 500,
  "& .MuiChip-icon": { color: "rgba(255,255,255,0.85)" },
};
const pillWarnSx = {
  ...pillSx,
  backgroundColor: "rgba(245,158,11,0.18)",
  border: "1px solid rgba(245,158,11,0.5)",
  color: "#fde68a",
  "& .MuiChip-icon": { color: "#fde68a" },
};
const pillInfoSx = {
  ...pillSx,
  backgroundColor: "rgba(56,189,248,0.18)",
  border: "1px solid rgba(56,189,248,0.5)",
  color: "#bae6fd",
  "& .MuiChip-icon": { color: "#bae6fd" },
};

// Translucent IconButton for actions on the navy hero. Reads white,
// hover lifts to brighter white-on-blue.
const heroIconBtnSx = {
  color: "rgba(255,255,255,0.85)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 1.5,
  background: "rgba(255,255,255,0.06)",
  backdropFilter: "blur(12px)",
  transition: "all 0.2s ease",
  "&:hover": {
    color: "#fff",
    background: "rgba(255,255,255,0.14)",
    borderColor: "rgba(255,255,255,0.32)",
  },
};
const heroIconBtnDangerSx = {
  ...heroIconBtnSx,
  color: "#fca5a5",
  "&:hover": {
    color: "#fff",
    background: "rgba(239,68,68,0.32)",
    borderColor: "rgba(252,165,165,0.6)",
  },
};

export default function ProjectInfo({ project }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const auth = useAuth();
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [tplOpen, setTplOpen] = useState(false);
  const [tplName, setTplName] = useState("");
  const [tplDesc, setTplDesc] = useState("");
  const [tplVisibility, setTplVisibility] = useState("private");
  const [tplSubmitting, setTplSubmitting] = useState(false);

  const handlePublishTemplate = () => {
    if (!tplName.trim() || tplSubmitting) return;
    setTplSubmitting(true);
    api.post(`/projects/${project.id}/publish-template`, {
      name: tplName.trim(),
      description: tplDesc.trim() || null,
      visibility: tplVisibility,
    }, auth.user.token)
      .then(() => {
        setTplOpen(false);
        setTplName("");
        setTplDesc("");
        setTplVisibility("private");
        toast.success(`Template "${tplName.trim()}" published.`, { position: "top-right" });
      })
      .catch(() => {})
      .finally(() => setTplSubmitting(false));
  };

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
      <HeroCard elevation={0}>
        {/* Header Row: Avatar + Name + Type */}
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, flexWrap: "wrap" }}>
          <BAvatar name={project.name} size={64} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]} />

          <Box sx={{ flex: 1, minWidth: 200 }}>
            {/* Inline path trail — replaces the standalone breadcrumb.
                "PROJECTS" navigates back to the listing; the project id
                is the current segment so it sits unlinked. */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.75,
                fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                fontSize: "0.65rem",
                letterSpacing: 3,
                lineHeight: 1.2,
                textTransform: "uppercase",
              }}
            >
              <Box
                component="span"
                role="link"
                tabIndex={0}
                onClick={() => navigate("/projects")}
                onKeyDown={(e) => { if (e.key === "Enter") navigate("/projects"); }}
                sx={{
                  color: "rgba(255,255,255,0.75)",
                  cursor: "pointer",
                  transition: "color 0.15s ease",
                  "&:hover": {
                    color: "#fff",
                    textDecoration: "underline",
                    textUnderlineOffset: "3px",
                  },
                }}
              >
                Projects
              </Box>
              <Box component="span" sx={{ color: "rgba(255,255,255,0.4)" }}>/</Box>
              <Box component="span" sx={{ color: "rgba(125,211,252,0.95)" }}>
                {String(project.id).padStart(4, "0")}
              </Box>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", mt: 0.5 }}>
              <Typography
                variant="h4"
                sx={{
                  fontWeight: 700,
                  color: "#fff",
                  letterSpacing: "-0.5px",
                  textShadow: "0 2px 20px rgba(0,0,0,0.2)",
                }}
              >
                {project.human_name || project.name}
                <Box
                  component="span"
                  sx={{
                    display: "inline-block",
                    width: 10,
                    ml: 0.5,
                    animation: `${blink} 1.1s steps(2, start) infinite`,
                    color: "rgba(125,211,252,0.9)",
                  }}
                >_</Box>
              </Typography>
              <ProjectTypeChip type={project.type} />
            </Box>

            {project.human_description && (
              <Typography
                variant="body2"
                sx={{ mt: 1, color: "rgba(255,255,255,0.82)", maxWidth: 720 }}
              >
                {project.human_description}
              </Typography>
            )}

            <Box sx={{ display: "flex", gap: 1, mt: 2, flexWrap: "wrap", alignItems: "center" }}>
              {project.llm && (
                <Chip icon={<Psychology />} label={project.llm} size="small" sx={pillSx} />
              )}
              {project.team && (
                <Chip icon={<Groups />} label={project.team.name} size="small" sx={pillSx} />
              )}
              {project.guard && (
                <Chip icon={<Shield />} label={`Guard: ${project.guard}`} size="small" sx={pillWarnSx} />
              )}
              {project.options?.rate_limit && (
                <Chip icon={<Speed />} label={`${project.options.rate_limit} req/min`} size="small" sx={pillSx} />
              )}
              {project.public && (
                <Chip label="Shared" size="small" sx={pillInfoSx} />
              )}
            </Box>
          </Box>
        </Box>

        {/* Action Toolbar */}
        <ActionBar>
          <Tooltip title={t("projects.actions.edit")}>
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/edit")}>
              <Edit fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t("projects.actions.playground")}>
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/playground")}>
              <SportsEsports fontSize="small" />
            </IconButton>
          </Tooltip>
          {project.type === "block" && (
            <Tooltip title="IDE">
              <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/ide")}>
                <ViewInAr fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title={t("projects.edit.tabs.evals")}>
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/evals")}>
              <Science fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t("projects.edit.tabs.guards")}>
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/guards")}>
              <Security fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Logs">
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/logs")}>
              <Article fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="API">
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate("/project/" + project.id + "/api")}>
              <Code fontSize="small" />
            </IconButton>
          </Tooltip>

          <Box sx={{ flex: 1 }} />

          <Tooltip title={t("projects.actions.saveAsTemplate")}>
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => { setTplName(project.human_name || project.name); setTplOpen(true); }}>
              <BookmarkAdd fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t("projects.actions.clone")}>
            <IconButton size="small" sx={heroIconBtnSx} onClick={() => { setCloneName(project.name + "-copy"); setCloneOpen(true); }}>
              <ContentCopy fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title={t("projects.actions.delete")}>
            <IconButton size="small" sx={heroIconBtnDangerSx} onClick={handleDelete}>
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
        </ActionBar>
      </HeroCard>

      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("projects.clone.title")}</DialogTitle>
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

      {/* Publish-as-template dialog */}
      <Dialog open={tplOpen} onClose={() => setTplOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("projects.template.saveTitle")}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t("projects.template.saveIntro")}
          </Typography>
          <TextField
            autoFocus fullWidth margin="dense"
            label={t("projects.template.name")}
            value={tplName}
            onChange={(e) => setTplName(e.target.value)}
          />
          <TextField
            fullWidth multiline minRows={2} margin="dense"
            label={t("projects.template.description")}
            value={tplDesc}
            onChange={(e) => setTplDesc(e.target.value)}
            helperText={t("projects.template.descHelper")}
          />
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">{t("projects.template.visibility")}</Typography>
            <Select
              fullWidth size="small" value={tplVisibility}
              onChange={(e) => setTplVisibility(e.target.value)}
            >
              <MenuItem value="private">{t("projects.template.private")}</MenuItem>
              <MenuItem value="team">{t("projects.template.team")}</MenuItem>
              <MenuItem value="public">{t("projects.template.public")}</MenuItem>
            </Select>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTplOpen(false)}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handlePublishTemplate} disabled={!tplName.trim() || tplSubmitting}>
            {tplSubmitting ? t("projects.template.publishing") : t("projects.template.publish")}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
