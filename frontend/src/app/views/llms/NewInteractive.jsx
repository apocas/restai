import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Divider, FormControlLabel, Grid, IconButton,
  InputAdornment, MenuItem, Switch, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { ArrowBack, Search, CheckCircle, Code } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import ReactJson from "@microlink/react-json-view";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { PROVIDER_CONFIG } from "./providerConfig";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

const Hero = styled(Box)(() => ({
  padding: "32px 0 24px",
  textAlign: "center",
}));

const HeroTitle = styled(Typography)(() => ({
  fontWeight: 700,
  letterSpacing: "-0.3px",
}));

const ProviderTile = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2.5),
  cursor: "pointer",
  transition: "all 0.25s ease",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  gap: 4,
  border: "1px solid",
  borderColor: theme.palette.divider,
  borderRadius: 12,
  position: "relative",
  overflow: "hidden",
  background: theme.palette.mode === "dark" ? "#1a1a24" : "#ffffff",
  "&::before": {
    content: '""',
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 2,
    background: "linear-gradient(90deg, #6366f1, #a855f7)",
    opacity: 0,
    transition: "opacity 0.25s",
  },
  "&:hover": {
    borderColor: theme.palette.primary.main,
    transform: "translateY(-3px)",
    boxShadow: "0 12px 24px -12px rgba(99,102,241,0.35)",
    "&::before": { opacity: 1 },
  },
}));

const FormCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(4),
  borderRadius: 16,
  border: "1px solid",
  borderColor: theme.palette.divider,
  background: theme.palette.mode === "dark" ? "#1a1a24" : "#ffffff",
}));

const SectionLabel = styled(Typography)(({ theme }) => ({
  fontSize: "0.72rem",
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.8px",
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1.5),
  display: "flex",
  alignItems: "center",
  gap: 6,
}));

const Dot = styled("span")(({ theme, color }) => ({
  width: 8,
  height: 8,
  borderRadius: "50%",
  background: color || theme.palette.primary.main,
  display: "inline-block",
}));

export default function NewInteractive() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [selectedProvider, setSelectedProvider] = useState(null);
  const [search, setSearch] = useState("");
  const [formState, setFormState] = useState({
    name: "",
    privacy: "private",
    description: "",
    context_window: 4096,
  });
  const [optionsState, setOptionsState] = useState({});

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - New LLM";
  }, []);

  const handleSelectProvider = (providerKey) => {
    setSelectedProvider(providerKey);
    const provider = PROVIDER_CONFIG[providerKey];
    const defaults = {};
    provider.fields.forEach((field) => {
      if (field.default !== undefined && field.default !== "") {
        defaults[field.name] = field.default;
      }
    });
    setOptionsState(defaults);
  };

  const handleBack = () => {
    setSelectedProvider(null);
    setOptionsState({});
    setFormState({ name: "", privacy: "private", description: "", context_window: 4096 });
  };

  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
  };

  const handleOptionChange = (fieldName, value) => {
    setOptionsState((prev) => ({ ...prev, [fieldName]: value }));
  };

  const handleJsonUpdate = (update) => {
    setOptionsState(update.updated_src);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formState.name.trim()) {
      toast.error("Name is required");
      return;
    }
    const options = {};
    Object.entries(optionsState).forEach(([key, value]) => {
      if (value !== "" && value !== undefined) options[key] = value;
    });
    try {
      const data = await api.post("/llms", {
        name: formState.name,
        class_name: selectedProvider,
        options: JSON.stringify(options),
        privacy: formState.privacy,
        description: formState.description,
        context_window: parseInt(formState.context_window) || 4096,
      }, auth.user.token);
      navigate("/llm/" + data.id);
    } catch (err) {
      // toasted
    }
  };

  const renderField = (field) => {
    const value = optionsState[field.name] ?? field.default ?? "";
    if (field.type === "boolean") {
      return (
        <Grid item xs={12} key={field.name}>
          <FormControlLabel
            control={
              <Switch
                checked={!!optionsState[field.name]}
                onChange={(e) => handleOptionChange(field.name, e.target.checked)}
              />
            }
            label={field.label}
          />
        </Grid>
      );
    }
    return (
      <Grid item xs={12} sm={6} key={field.name}>
        <TextField
          fullWidth
          size="small"
          label={field.label}
          type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
          required={field.required}
          value={value}
          placeholder={field.placeholder || ""}
          inputProps={field.type === "number" ? { step: field.step || 1 } : {}}
          onChange={(e) => {
            const val = field.type === "number"
              ? (e.target.value === "" ? "" : Number(e.target.value))
              : e.target.value;
            handleOptionChange(field.name, val);
          }}
        />
      </Grid>
    );
  };

  // ─── Phase 1: Provider selection ───────────────────────────────
  if (!selectedProvider) {
    const providers = Object.entries(PROVIDER_CONFIG).filter(([key, p]) => {
      const q = search.toLowerCase();
      return !q || p.label.toLowerCase().includes(q) || key.toLowerCase().includes(q) || (p.description || "").toLowerCase().includes(q);
    });

    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb
            routeSegments={[
              { name: "LLMs", path: "/llms" },
              { name: "New LLM", path: "/llms/new" },
              { name: "Manual" },
            ]}
          />
        </Box>

        <Hero>
          <Box sx={{ position: "relative", zIndex: 1 }}>
            <HeroTitle variant="h4" color="primary" sx={{ mb: 1 }}>
              Choose a provider
            </HeroTitle>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 520, mx: "auto" }}>
              Pick the provider that hosts your model. We'll configure the right fields automatically.
            </Typography>
          </Box>
        </Hero>

        <Box sx={{ display: "flex", justifyContent: "center", mb: 4 }}>
          <TextField
            size="small"
            placeholder="Search providers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ width: 360 }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search fontSize="small" color="action" />
                </InputAdornment>
              ),
            }}
          />
        </Box>

        {providers.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 4 }}>
            No providers match your search.
          </Typography>
        ) : (
          <Grid container spacing={2.5}>
            {providers.map(([key, provider]) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={key}>
                <ProviderTile onClick={() => handleSelectProvider(key)}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    {provider.label}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ flex: 1, lineHeight: 1.5 }}>
                    {provider.description}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ fontFamily: "monospace", color: "text.disabled", mt: 1, fontSize: "0.7rem" }}
                  >
                    {key}
                  </Typography>
                </ProviderTile>
              </Grid>
            ))}
          </Grid>
        )}
      </Container>
    );
  }

  // ─── Phase 2: Configuration form ───────────────────────────────
  const provider = PROVIDER_CONFIG[selectedProvider];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: "LLMs", path: "/llms" },
            { name: "New LLM", path: "/llms/new" },
            { name: "Manual", path: "/llms/new/manual" },
            { name: provider.label },
          ]}
        />
      </Box>

      <Box sx={{ maxWidth: 960, mx: "auto" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
          <Tooltip title="Back to providers">
            <IconButton onClick={handleBack} sx={{ border: "1px solid", borderColor: "divider" }}>
              <ArrowBack />
            </IconButton>
          </Tooltip>
          <Box sx={{ flex: 1 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
              <Typography variant="h5" fontWeight={700}>
                New {provider.label} LLM
              </Typography>
              <Chip
                label={selectedProvider}
                size="small"
                sx={{
                  fontFamily: "monospace",
                  fontSize: "0.72rem",
                  height: 22,
                  background: "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(168,85,247,0.12))",
                  border: "1px solid rgba(99,102,241,0.3)",
                  color: "primary.main",
                }}
              />
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {provider.description}
            </Typography>
          </Box>
        </Box>

        <form onSubmit={handleSubmit}>
          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#6366f1" />
              General
            </SectionLabel>
            <Grid container spacing={2.5}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  size="small"
                  name="name"
                  label="Name"
                  value={formState.name}
                  onChange={handleFormChange}
                  placeholder="Unique name for this LLM"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  select
                  size="small"
                  name="privacy"
                  label="Privacy"
                  value={formState.privacy}
                  onChange={handleFormChange}
                >
                  <MenuItem value="private">Private</MenuItem>
                  <MenuItem value="public">Public</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} sm={8}>
                <TextField
                  fullWidth
                  size="small"
                  name="description"
                  label="Description"
                  value={formState.description}
                  onChange={handleFormChange}
                  placeholder="Optional short description"
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  size="small"
                  name="context_window"
                  label="Context Window"
                  type="number"
                  value={formState.context_window}
                  onChange={handleFormChange}
                  helperText="Maximum tokens"
                />
              </Grid>
            </Grid>
          </FormCard>

          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#10b981" />
              {provider.label} Options
            </SectionLabel>
            <Grid container spacing={2.5}>
              {provider.fields.map(renderField)}
            </Grid>
          </FormCard>

          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#f59e0b" />
              Raw Options (JSON)
            </SectionLabel>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: "block" }}>
              Auto-updated from the fields above. Click values to edit, or use +/- to add/remove custom options.
            </Typography>
            <Box
              sx={{
                borderRadius: 2,
                border: "1px solid",
                borderColor: "divider",
                p: 2,
                fontSize: "0.85rem",
                background: (t) => t.palette.mode === "dark" ? "#0f0f17" : "#fafafa",
              }}
            >
              <ReactJson
                src={optionsState}
                name={false}
                enableClipboard={true}
                onEdit={handleJsonUpdate}
                onAdd={handleJsonUpdate}
                onDelete={handleJsonUpdate}
                displayDataTypes={false}
                displayObjectSize={false}
                theme="rjv-default"
              />
            </Box>
          </FormCard>

          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1.5 }}>
            <Button variant="outlined" onClick={handleBack}>
              Cancel
            </Button>
            <Button type="submit" variant="contained" startIcon={<CheckCircle />}>
              Create LLM
            </Button>
          </Box>
        </form>
      </Box>
    </Container>
  );
}
