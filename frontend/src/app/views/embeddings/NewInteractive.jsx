import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Grid, IconButton, InputAdornment,
  MenuItem, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { ArrowBack, Search, CheckCircle } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import ReactJson from "@microlink/react-json-view";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { EMBEDDING_PROVIDER_CONFIG } from "./embeddingProviderConfig";
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
    background: theme.palette.primary.main,
    opacity: 0,
    transition: "opacity 0.25s",
  },
  "&:hover": {
    borderColor: theme.palette.primary.main,
    transform: "translateY(-3px)",
    boxShadow: `0 12px 24px -12px ${theme.palette.primary.main}59`,
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
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();

  const [selectedProvider, setSelectedProvider] = useState(null);
  const [search, setSearch] = useState("");
  const [formState, setFormState] = useState({
    name: "",
    privacy: "private",
    description: "",
    dimension: 1536,
  });
  const [optionsState, setOptionsState] = useState({});

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("embeddings.newBreadcrumb");
  }, [t]);

  const handleSelectProvider = (providerKey) => {
    const provider = EMBEDDING_PROVIDER_CONFIG[providerKey];
    setSelectedProvider(providerKey);
    const defaults = {};
    provider.fields.forEach((field) => {
      if (field.default !== undefined && field.default !== "") {
        defaults[field.name] = field.default;
      }
    });
    setOptionsState(defaults);
    setFormState((prev) => ({ ...prev, dimension: provider.defaultDimension }));
  };

  const handleBack = () => {
    setSelectedProvider(null);
    setOptionsState({});
    setFormState({ name: "", privacy: "private", description: "", dimension: 1536 });
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
      toast.error(t("embeddings.interactive.nameRequired"));
      return;
    }
    const options = {};
    Object.entries(optionsState).forEach(([key, value]) => {
      if (value !== "" && value !== undefined) options[key] = value;
    });
    try {
      const data = await api.post("/embeddings", {
        name: formState.name,
        class_name: selectedProvider,
        options: JSON.stringify(options),
        privacy: formState.privacy,
        description: formState.description,
        dimension: Number(formState.dimension),
      }, auth.user.token);
      navigate("/embedding/" + data.id);
    } catch (err) {
      // toasted
    }
  };

  const renderField = (field) => {
    const value = optionsState[field.name] ?? field.default ?? "";
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
    const providers = Object.entries(EMBEDDING_PROVIDER_CONFIG).filter(([key, p]) => {
      const q = search.toLowerCase();
      return !q || p.label.toLowerCase().includes(q) || key.toLowerCase().includes(q) || (p.description || "").toLowerCase().includes(q);
    });

    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb
            routeSegments={[
              { name: t("nav.embeddings"), path: "/embeddings" },
              { name: t("embeddings.newBreadcrumb"), path: "/embeddings/new" },
              { name: t("embeddings.manualCrumb") },
            ]}
          />
        </Box>

        <Hero>
          <Box sx={{ position: "relative", zIndex: 1 }}>
            <HeroTitle variant="h4" color="primary" sx={{ mb: 1 }}>
              {t("embeddings.interactive.title")}
            </HeroTitle>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 520, mx: "auto" }}>
              {t("embeddings.interactive.subtitle")}
            </Typography>
          </Box>
        </Hero>

        <Box sx={{ display: "flex", justifyContent: "center", mb: 4 }}>
          <TextField
            size="small"
            placeholder={t("embeddings.interactive.searchPlaceholder")}
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
            {t("embeddings.interactive.noProviders")}
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
  const provider = EMBEDDING_PROVIDER_CONFIG[selectedProvider];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: t("nav.embeddings"), path: "/embeddings" },
            { name: t("embeddings.newBreadcrumb"), path: "/embeddings/new" },
            { name: t("embeddings.manualCrumb"), path: "/embeddings/new/manual" },
            { name: provider.label },
          ]}
        />
      </Box>

      <Box sx={{ maxWidth: 960, mx: "auto" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
          <Tooltip title={t("embeddings.interactive.back")}>
            <IconButton onClick={handleBack} sx={{ border: "1px solid", borderColor: "divider" }}>
              <ArrowBack />
            </IconButton>
          </Tooltip>
          <Box sx={{ flex: 1 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
              <Typography variant="h5" fontWeight={700}>
                {t("embeddings.interactive.newX", { provider: provider.label })}
              </Typography>
              <Chip
                label={selectedProvider}
                size="small"
                sx={{
                  fontFamily: "monospace",
                  fontSize: "0.72rem",
                  height: 22,
                }}
                color="primary"
                variant="outlined"
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
              {t("embeddings.interactive.general")}
            </SectionLabel>
            <Grid container spacing={2.5}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  size="small"
                  name="name"
                  label={t("embeddings.interactive.name")}
                  value={formState.name}
                  onChange={handleFormChange}
                  placeholder={t("embeddings.interactive.namePlaceholder")}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  select
                  size="small"
                  name="privacy"
                  label={t("embeddings.edit.privacy")}
                  value={formState.privacy}
                  onChange={handleFormChange}
                >
                  <MenuItem value="private">{t("common.private")}</MenuItem>
                  <MenuItem value="public">{t("common.public")}</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} sm={8}>
                <TextField
                  fullWidth
                  size="small"
                  name="description"
                  label={t("embeddings.interactive.description")}
                  value={formState.description}
                  onChange={handleFormChange}
                  placeholder={t("embeddings.interactive.descPlaceholder")}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  size="small"
                  name="dimension"
                  label={t("embeddings.interactive.dimension")}
                  type="number"
                  value={formState.dimension}
                  onChange={(e) =>
                    setFormState((prev) => ({
                      ...prev,
                      dimension: e.target.value === "" ? "" : Number(e.target.value),
                    }))
                  }
                  helperText={t("embeddings.interactive.vectorSize")}
                />
              </Grid>
            </Grid>
          </FormCard>

          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#10b981" />
              {t("embeddings.interactive.providerOptions", { provider: provider.label })}
            </SectionLabel>
            <Grid container spacing={2.5}>
              {provider.fields.map(renderField)}
            </Grid>
          </FormCard>

          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#f59e0b" />
              {t("embeddings.interactive.rawOptions")}
            </SectionLabel>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1.5, display: "block" }}>
              {t("embeddings.interactive.rawHelp")}
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
              {t("common.cancel")}
            </Button>
            <Button type="submit" variant="contained" startIcon={<CheckCircle />}>
              {t("embeddings.interactive.createEmbedding")}
            </Button>
          </Box>
        </form>
      </Box>
    </Container>
  );
}
