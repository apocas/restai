import { useState, useEffect } from "react";
import {
  Box,
  Button,
  Card,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  MenuItem,
  Select,
  TextField,
  Typography,
  styled,
} from "@mui/material";
import {
  SmartToy, Description, ImageSearch, Summarize, Code,
  SupportAgent, DataObject, Translate, TravelExplore, AccountTree,
  Shield, AddCircleOutline, Bookmark, AddCircle,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { PROJECT_TEMPLATES, TEMPLATE_CATEGORIES } from "./projectTemplates";
import ProjectTypeChip from "app/components/ProjectTypeChip";

const ICONS = {
  SmartToy, Description, ImageSearch, Summarize, Code,
  SupportAgent, DataObject, Translate, TravelExplore, AccountTree,
  Shield,
};

const TemplateCard = styled(Card)(({ theme }) => ({
  cursor: "pointer",
  padding: theme.spacing(3),
  height: "100%",
  display: "flex",
  flexDirection: "column",
  transition: "all 0.2s ease",
  "&:hover": {
    transform: "translateY(-4px)",
    boxShadow: theme.shadows[8],
  },
}));

const ScratchCard = styled(Card)(({ theme }) => ({
  cursor: "pointer",
  padding: theme.spacing(3),
  height: "100%",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  border: "2px dashed",
  borderColor: theme.palette.divider,
  backgroundColor: "transparent",
  transition: "all 0.2s ease",
  "&:hover": {
    transform: "translateY(-4px)",
    borderColor: theme.palette.primary.main,
    boxShadow: theme.shadows[4],
  },
}));

const IconCircle = styled(Box)({
  width: 48,
  height: 48,
  borderRadius: "50%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  marginBottom: 12,
});

export default function TemplateGallery({ onSelect }) {
  const auth = useAuth();
  const navigate = useNavigate();

  const [category, setCategory] = useState("all");

  // Published templates (DB-backed, from the Save-as-template button on
  // a project's detail page). Distinct from the PROJECT_TEMPLATES starter
  // set baked into the frontend — those seed the create-project form,
  // these clone a real project snapshot server-side via POST
  // /templates/{id}/instantiate.
  const [pubTemplates, setPubTemplates] = useState([]);
  const [teams, setTeams] = useState([]);
  const [llms, setLlms] = useState([]);

  // Instantiate dialog state. Same shape as Library.jsx so the UX is
  // consistent across the two places users can browse templates.
  const [instTarget, setInstTarget] = useState(null);
  const [instName, setInstName] = useState("");
  const [instTeam, setInstTeam] = useState("");
  const [instLlm, setInstLlm] = useState("");
  const [instSubmitting, setInstSubmitting] = useState(false);

  useEffect(() => {
    api.get("/templates", auth.user.token, { silent: true })
      .then((d) => setPubTemplates(d || []))
      .catch(() => {});
    api.get("/teams", auth.user.token, { silent: true })
      .then((d) => setTeams(d.teams || []))
      .catch(() => {});
    api.get("/info", auth.user.token, { silent: true })
      .then((d) => setLlms(d.llms || []))
      .catch(() => {});
  }, [auth.user.token]);

  const filteredStarters = category === "all"
    ? PROJECT_TEMPLATES
    : PROJECT_TEMPLATES.filter((t) => t.category === category);

  const filteredPub = category === "all"
    ? pubTemplates
    : pubTemplates.filter((t) => {
        // Best-effort mapping: "agent" category includes agent projects,
        // "rag" includes rag, etc. The starter templates use topical
        // categories (support, translation) that published templates
        // don't carry, so filter loosely on project_type.
        if (["agent", "rag", "block"].includes(category)) {
          return t.project_type === category;
        }
        return false;
      });

  const openInstantiate = (tpl) => {
    setInstTarget(tpl);
    setInstName(tpl.name.toLowerCase().replace(/[^a-z0-9._:-]+/g, "-"));
    setInstTeam(teams[0] ? teams[0].id : "");
    setInstLlm(tpl.suggested_llm || "");
  };

  const closeInstantiate = () => {
    setInstTarget(null);
    setInstName("");
    setInstTeam("");
    setInstLlm("");
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
        closeInstantiate();
        navigate("/project/" + response.id);
      })
      .catch(() => {})
      .finally(() => setInstSubmitting(false));
  };

  return (
    <Box>
      <Box sx={{ textAlign: "center", mb: 4 }}>
        <Typography variant="h4" fontWeight="bold" gutterBottom>
          Choose a Template
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Start with a pre-configured project or build from scratch
        </Typography>
      </Box>

      <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mb: 4, flexWrap: "wrap" }}>
        {TEMPLATE_CATEGORIES.map((cat) => (
          <Chip
            key={cat.id}
            label={cat.label}
            onClick={() => setCategory(cat.id)}
            color={category === cat.id ? "primary" : "default"}
            variant={category === cat.id ? "filled" : "outlined"}
          />
        ))}
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={4} lg={3}>
          <ScratchCard elevation={0} onClick={() => onSelect(null)}>
            <AddCircleOutline sx={{ fontSize: 48, color: "text.secondary", mb: 1 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Start from Scratch
            </Typography>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              Create a blank project and configure everything manually
            </Typography>
          </ScratchCard>
        </Grid>

        {filteredStarters.map((template) => {
          const IconComponent = ICONS[template.icon];
          return (
            <Grid item xs={12} sm={6} md={4} lg={3} key={template.id}>
              <TemplateCard elevation={2} onClick={() => onSelect(template)}>
                <IconCircle sx={{ backgroundColor: template.color }}>
                  {IconComponent && <IconComponent sx={{ color: "#fff", fontSize: 24 }} />}
                </IconCircle>
                <Typography variant="h6" gutterBottom>
                  {template.name}
                </Typography>
                <ProjectTypeChip type={template.type} sx={{ mb: 1, alignSelf: "flex-start" }} />
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{
                    flexGrow: 1,
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {template.description}
                </Typography>
              </TemplateCard>
            </Grid>
          );
        })}
      </Grid>

      {/* Published Templates — DB-backed, from the Save-as-template
          button on any project detail page. Rendered only when the
          user actually has at least one visible template. */}
      {filteredPub.length > 0 && (
        <Box sx={{ mt: 6 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <Bookmark fontSize="small" color="primary" />
            <Typography variant="h6" fontWeight="bold">Your Published Templates</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Saved from existing projects. Clicking one creates a fresh project seeded from the snapshot.
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Grid container spacing={3}>
            {filteredPub.map((tpl) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={`pub-${tpl.id}`}>
                <TemplateCard elevation={2} onClick={() => openInstantiate(tpl)}>
                  <IconCircle sx={{ backgroundColor: "#6366f1" }}>
                    <Bookmark sx={{ color: "#fff", fontSize: 24 }} />
                  </IconCircle>
                  <Typography variant="h6" gutterBottom>
                    {tpl.name}
                  </Typography>
                  <Box sx={{ display: "flex", gap: 0.5, mb: 1, flexWrap: "wrap" }}>
                    <ProjectTypeChip type={tpl.project_type} />
                    <Chip label={tpl.visibility} size="small" variant="outlined" />
                  </Box>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{
                      flexGrow: 1,
                      display: "-webkit-box",
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      mb: 1,
                    }}
                  >
                    {tpl.description || <em>No description</em>}
                  </Typography>
                  {tpl.creator_username && (
                    <Typography variant="caption" color="text.secondary">
                      by {tpl.creator_username}
                    </Typography>
                  )}
                </TemplateCard>
              </Grid>
            ))}
          </Grid>
        </Box>
      )}

      {/* Instantiate dialog — identical to the one on /projects/library
          so the "pick team + LLM + name" UX is shared. Submit POSTs to
          /templates/{id}/instantiate, which creates the project
          server-side and returns its id; we navigate straight to the
          project edit page. */}
      <Dialog open={!!instTarget} onClose={closeInstantiate} maxWidth="sm" fullWidth>
        <DialogTitle>Use Template: {instTarget?.name}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label="New project name"
            value={instName}
            onChange={(e) => setInstName(e.target.value)}
            helperText="URL-safe identifier (letters, numbers, . _ : -)"
          />
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">Target team</Typography>
            <Select
              fullWidth size="small" value={instTeam}
              onChange={(e) => setInstTeam(e.target.value)}
            >
              {teams.map((t) => (
                <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>
              ))}
            </Select>
          </Box>
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">
              LLM {instTarget?.suggested_llm && `(suggested: ${instTarget.suggested_llm})`}
            </Typography>
            <Select
              fullWidth size="small" value={instLlm}
              onChange={(e) => setInstLlm(e.target.value)}
            >
              <MenuItem value=""><em>(use suggested)</em></MenuItem>
              {llms.map((l) => (
                <MenuItem key={l.id} value={l.name}>{l.name}</MenuItem>
              ))}
            </Select>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeInstantiate}>Cancel</Button>
          <Button
            variant="contained" startIcon={<AddCircle />}
            onClick={handleInstantiate}
            disabled={!instName.trim() || !instTeam || instSubmitting}
          >
            {instSubmitting ? "Creating…" : "Create Project"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
