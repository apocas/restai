import { useState, useEffect, useRef } from "react";
import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogTitle,
  Grid, TextField, Typography, CircularProgress, Alert, styled,
} from "@mui/material";
import { AutoAwesome } from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import BlocklyEditor from "./components/BlocklyEditor";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function ProjectIDEView() {
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
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - IDE - " + id;
    fetchProjects();
    api.get("/info", auth.user.token)
      .then((d) => setSystemLlmConfigured(!!d?.system_llm_configured))
      .catch(() => {});
  }, []);

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
        toast.success("Workspace saved");
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
        toast.success("Workspace generated — review and save when ready");
        setAiOpen(false);
        setAiPrompt("");
      })
      .catch(() => {})
      .finally(() => setAiLoading(false));
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: "Projects", path: "/projects" },
            { name: id, path: "/project/" + id },
            { name: "IDE" },
          ]}
        />
      </Box>

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2, gap: 2, flexWrap: "wrap" }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Block IDE</Typography>
          <Typography variant="body2" color="text.secondary">
            Visually compose your block project{systemLlmConfigured ? '. Use "Generate with AI" to get a starting workspace.' : "."}
          </Typography>
        </Box>
        {systemLlmConfigured && (
          <Button
            variant="contained"
            startIcon={<AutoAwesome />}
            onClick={() => setAiOpen(true)}
          >
            Generate with AI
          </Button>
        )}
      </Box>

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
        <DialogTitle>Generate workspace with AI</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Describe in plain English what this block project should do. The system LLM will generate a starter workspace you can then edit.
          </Typography>
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={4}
            placeholder={'e.g. "Classify user messages as billing, technical, or sales, then forward each to the right sub-project"'}
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            disabled={aiLoading}
          />
          <Alert severity="warning" sx={{ mt: 2 }}>
            This replaces the current workspace. Save your existing blocks first if you need them.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAiOpen(false)} disabled={aiLoading}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleGenerate}
            disabled={aiLoading || !aiPrompt.trim()}
            startIcon={aiLoading ? <CircularProgress size={16} /> : <AutoAwesome />}
          >
            {aiLoading ? "Generating..." : "Generate"}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
