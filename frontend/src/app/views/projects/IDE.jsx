import { useState, useEffect, useRef } from "react";
import {
  Button, Dialog, DialogActions, DialogContent, DialogTitle,
  Grid, TextField, Typography, CircularProgress, Alert, styled,
} from "@mui/material";
import { AutoAwesome, ViewInAr } from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import BlocklyEditor from "./components/BlocklyEditor";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function ProjectIDEView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState({});
  const [systemLlmConfigured, setSystemLlmConfigured] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const loadWorkspaceRef = useRef(null);
  const auth = useAuth();

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects))
      .catch(() => {});
  };

  const fetchProject = (projectID) => {
    return api.get("/projects/" + projectID, auth.user.token)
      .then((d) => {
        setProject(d);
        return d;
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchProject(id);
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("projects.edit.knowledge.ide.title") + " - " + id;
    fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!auth.user) return;
    api.get("/info", auth.user.token)
      .then((d) => setSystemLlmConfigured(!!d?.system_llm_configured))
      .catch(() => {});
  }, [auth.user?.username]);

  const handleSave = (blocklyOpts) => {
    const opts = {
      name: project.name,
      options: {
        ...(project.options || {}),
        ...blocklyOpts,
      },
    };
    api.patch("/projects/" + project.id, opts, auth.user.token)
      .then(() => {
        toast.success(t("projects.edit.knowledge.ide.workspaceSaved"));
        fetchProject(id);
      })
      .catch(() => {});
  };

  const handleGenerate = () => {
    if (!aiPrompt.trim()) return;
    setAiLoading(true);
    api.post("/projects/" + id + "/block/generate", { description: aiPrompt }, auth.user.token)
      .then((data) => {
        if (loadWorkspaceRef.current) {
          loadWorkspaceRef.current(data.workspace);
        }
        toast.success(t("projects.edit.knowledge.ide.workspaceGenerated"));
        setAiOpen(false);
        setAiPrompt("");
      })
      .catch(() => {})
      .finally(() => setAiLoading(false));
  };

  return (
    <Container>
      <PageHero
        icon={<ViewInAr sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="Block IDE"
        subtitle="Visual builder for block projects."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        actions={systemLlmConfigured ? (
          <Button
            variant="contained"
            startIcon={<AutoAwesome />}
            onClick={() => setAiOpen(true)}
            sx={{
              background: "rgba(255,255,255,0.12)",
              color: "#fff",
              border: "1px solid rgba(255,255,255,0.22)",
              "&:hover": { background: "rgba(255,255,255,0.2)" },
            }}
          >
            {t("projects.edit.knowledge.ide.generateAi")}
          </Button>
        ) : null}
        compact
      />

      <Grid container spacing={3}>
        <Grid item lg={12} md={12} sm={12} xs={12}>
          {project.name && (
            <BlocklyEditor
              project={project}
              projects={projects}
              onSave={handleSave}
              onReady={(loader) => { loadWorkspaceRef.current = loader; }}
            />
          )}
        </Grid>
      </Grid>

      <Dialog open={aiOpen} onClose={() => !aiLoading && setAiOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("projects.edit.knowledge.ide.dialogTitle")}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t("projects.edit.knowledge.ide.dialogHelp")}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={4}
            placeholder={t("projects.edit.knowledge.ide.placeholder")}
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            disabled={aiLoading}
          />
          <Alert severity="warning" sx={{ mt: 2 }}>
            {t("projects.edit.knowledge.ide.warning")}
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAiOpen(false)} disabled={aiLoading}>{t("common.cancel")}</Button>
          <Button
            variant="contained"
            onClick={handleGenerate}
            disabled={aiLoading || !aiPrompt.trim()}
            startIcon={aiLoading ? <CircularProgress size={16} /> : <AutoAwesome />}
          >
            {aiLoading ? t("projects.edit.knowledge.ide.generating") : t("projects.edit.knowledge.ide.generate")}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
