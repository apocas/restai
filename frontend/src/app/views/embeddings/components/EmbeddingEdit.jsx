import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Chip, CircularProgress, Grid, InputAdornment,
  MenuItem, TextField, Typography, styled,
} from "@mui/material";
import {
  Save, Close, Hub, Code, GridView, Public, Lock,
  Storage, Description, Title, AltRoute, RestoreOutlined,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Same teal-600 as the embedding info / TeamView per-section colour so
// view <-> edit feel like one surface.
const ACCENT = "#0d9488";        // teal-600
const ACCENT_DARK = "#0f766e";   // teal-700
const ACCENT_SOFT = "rgba(13,148,136,0.10)";

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
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
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

function TileHeader({ icon, title, subtitle, accent = ACCENT, action }) {
  return (
    <Box
      sx={{
        px: 2.5, pt: 2, pb: 1.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid rgba(15,23,42,0.06)",
        flexWrap: "wrap",
      }}
    >
      <Box
        sx={{
          width: 36, height: 36, flexShrink: 0,
          borderRadius: 1.5,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: accent,
            lineHeight: 1,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.4 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {action}
    </Box>
  );
}

// Field styling — accent focus ring across all inputs.
const fieldSx = {
  "& .MuiOutlinedInput-root": {
    "& fieldset": { borderColor: "rgba(15,23,42,0.12)" },
    "&:hover fieldset": { borderColor: `${ACCENT}55` },
    "&.Mui-focused fieldset": { borderColor: ACCENT, borderWidth: 1.5 },
  },
  "& .MuiInputLabel-root.Mui-focused": { color: ACCENT },
};

// Common known classes — keeps users from having to memorize
// LlamaIndex provider strings. Free-form fallback below.
const CLASS_OPTIONS = [
  "OpenAIEmbedding",
  "HuggingFaceEmbedding",
  "OllamaEmbedding",
  "AzureOpenAIEmbedding",
  "GeminiEmbedding",
  "FastEmbedEmbedding",
  "CohereEmbedding",
  "VoyageEmbedding",
];

// Pretty-printer for the options TextField — accepts JSON, normalises
// indentation, quietly leaves invalid input alone so users can keep
// typing.
const tryFormat = (raw) => {
  if (!raw) return raw;
  try { return JSON.stringify(JSON.parse(raw), null, 2); } catch { return raw; }
};

export default function EmbeddingEdit({ embedding }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({});
  const [saving, setSaving] = useState(false);
  const [classFreeForm, setClassFreeForm] = useState(false);

  useEffect(() => {
    setState(embedding);
    // Switch the class field into free-form mode when the loaded value
    // isn't in our curated list, so we don't force the user back to a
    // dropdown choice.
    if (embedding.class_name && !CLASS_OPTIONS.includes(embedding.class_name)) {
      setClassFreeForm(true);
    }
  }, [embedding]);

  const handleChange = (e) => {
    if (e?.persist) e.persist();
    setState((s) => ({ ...s, [e.target.name]: e.target.value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setSaving(true);
    const update = {};
    ["name", "class_name", "options", "privacy", "description", "dimension"].forEach((k) => {
      if (state[k] !== embedding[k]) update[k] = state[k];
    });
    api.patch("/embeddings/" + embedding.id, update, auth.user.token)
      .then(() => {
        toast.success(t("common.saved") || "Saved");
        window.location.href = "/admin/embedding/" + embedding.id;
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  const isPublic = (state.privacy || "").toLowerCase() === "public";
  const optionsValid = useMemo(() => {
    if (!state.options) return true;
    try { JSON.parse(state.options); return true; } catch { return false; }
  }, [state.options]);

  const dirty = useMemo(() => {
    return ["name", "class_name", "options", "privacy", "description", "dimension"]
      .some((k) => state[k] !== embedding[k]);
  }, [state, embedding]);

  return (
    <form onSubmit={handleSubmit}>
      {/* IDENTITY */}
      <TileCard elevation={0} accent={ACCENT}>
        <TileHeader
          icon={<Hub />}
          title={t("embeddings.edit.title", { name: embedding.name })}
          subtitle="Provider, identity, and visibility"
          accent={ACCENT}
          action={
            dirty && (
              <Chip
                label="UNSAVED"
                size="small"
                sx={{
                  height: 22,
                  fontFamily: FONT_MONO,
                  fontSize: "0.62rem",
                  fontWeight: 800,
                  letterSpacing: "0.08em",
                  backgroundColor: "rgba(245,158,11,0.12)",
                  color: "#d97706",
                  border: "1px solid rgba(245,158,11,0.4)",
                  animation: `${pulse} 2s ease-out infinite`,
                }}
              />
            )
          }
        />
        <Box sx={{ p: 2.5 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                name="name"
                label={t("embeddings.edit.name")}
                value={state.name || ""}
                onChange={handleChange}
                InputLabelProps={{ shrink: true }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Title sx={{ fontSize: 18, color: ACCENT }} />
                    </InputAdornment>
                  ),
                }}
                sx={fieldSx}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              {classFreeForm ? (
                <TextField
                  fullWidth
                  name="class_name"
                  label={t("embeddings.edit.className")}
                  value={state.class_name || ""}
                  onChange={handleChange}
                  helperText={
                    <Box
                      component="span"
                      onClick={() => setClassFreeForm(false)}
                      sx={{
                        cursor: "pointer",
                        color: ACCENT,
                        fontFamily: FONT_MONO,
                        fontSize: "0.66rem",
                        letterSpacing: "0.04em",
                        "&:hover": { textDecoration: "underline" },
                      }}
                    >
                      ↩ pick from list
                    </Box>
                  }
                  InputLabelProps={{ shrink: true }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Code sx={{ fontSize: 18, color: ACCENT }} />
                      </InputAdornment>
                    ),
                  }}
                  sx={fieldSx}
                />
              ) : (
                <TextField
                  select
                  fullWidth
                  name="class_name"
                  label={t("embeddings.edit.className")}
                  value={state.class_name || ""}
                  onChange={handleChange}
                  helperText={
                    <Box
                      component="span"
                      onClick={() => setClassFreeForm(true)}
                      sx={{
                        cursor: "pointer",
                        color: ACCENT,
                        fontFamily: FONT_MONO,
                        fontSize: "0.66rem",
                        letterSpacing: "0.04em",
                        "&:hover": { textDecoration: "underline" },
                      }}
                    >
                      ✎ enter custom class
                    </Box>
                  }
                  InputLabelProps={{ shrink: true }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Code sx={{ fontSize: 18, color: ACCENT }} />
                      </InputAdornment>
                    ),
                  }}
                  sx={fieldSx}
                >
                  {CLASS_OPTIONS.map((opt) => (
                    <MenuItem key={opt} value={opt} sx={{ fontFamily: FONT_MONO, fontSize: "0.85rem" }}>
                      {opt}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            </Grid>

            <Grid item xs={12} sm={6}>
              <TextField
                select
                fullWidth
                name="privacy"
                label={t("embeddings.edit.privacy")}
                value={state.privacy || ""}
                onChange={handleChange}
                InputLabelProps={{ shrink: true }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      {isPublic
                        ? <Public sx={{ fontSize: 18, color: "#10b981" }} />
                        : <Lock sx={{ fontSize: 18, color: "#f59e0b" }} />}
                    </InputAdornment>
                  ),
                }}
                sx={fieldSx}
              >
                <MenuItem value="public">
                  <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                    <Public sx={{ fontSize: 14, color: "#10b981" }} />
                    <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.85rem" }}>public</Box>
                  </Box>
                </MenuItem>
                <MenuItem value="private">
                  <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                    <Lock sx={{ fontSize: 14, color: "#f59e0b" }} />
                    <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.85rem" }}>private</Box>
                  </Box>
                </MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                name="dimension"
                type="number"
                label={t("embeddings.edit.dimension")}
                value={state.dimension || ""}
                onChange={handleChange}
                InputLabelProps={{ shrink: true }}
                helperText="Leave blank to auto-detect from the provider"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <GridView sx={{ fontSize: 18, color: "#0891b2" }} />
                    </InputAdornment>
                  ),
                  endAdornment: state.dimension && (
                    <InputAdornment position="end">
                      <Box
                        component="span"
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.7rem",
                          color: "#0891b2",
                          letterSpacing: "0.04em",
                          fontWeight: 700,
                        }}
                      >
                        dims
                      </Box>
                    </InputAdornment>
                  ),
                }}
                sx={fieldSx}
              />
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                name="description"
                label={t("embeddings.edit.description")}
                value={state.description || ""}
                onChange={handleChange}
                multiline
                rows={2}
                InputLabelProps={{ shrink: true }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start" sx={{ alignSelf: "flex-start", mt: 1 }}>
                      <Description sx={{ fontSize: 18, color: ACCENT }} />
                    </InputAdornment>
                  ),
                }}
                sx={fieldSx}
              />
            </Grid>
          </Grid>
        </Box>
      </TileCard>

      {/* OPTIONS — terminal-style mono editor */}
      <Box sx={{ mt: 2.5 }}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<Storage />}
            title={t("embeddings.edit.options")}
            subtitle="Provider-specific JSON. API keys, endpoints, model identifiers."
            accent={ACCENT}
            action={
              state.options && (
                <>
                  <Chip
                    label={optionsValid ? "VALID JSON" : "INVALID JSON"}
                    size="small"
                    sx={{
                      height: 22,
                      mr: 1,
                      fontFamily: FONT_MONO,
                      fontSize: "0.62rem",
                      fontWeight: 800,
                      letterSpacing: "0.08em",
                      backgroundColor: optionsValid ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
                      color: optionsValid ? "#059669" : "#dc2626",
                      border: `1px solid ${optionsValid ? "rgba(16,185,129,0.4)" : "rgba(239,68,68,0.4)"}`,
                    }}
                  />
                  <Button
                    size="small"
                    startIcon={<RestoreOutlined fontSize="small" />}
                    onClick={() => setState((s) => ({ ...s, options: tryFormat(s.options) }))}
                    sx={{
                      textTransform: "none",
                      fontSize: "0.74rem",
                      color: ACCENT,
                      "&:hover": { backgroundColor: ACCENT_SOFT },
                    }}
                  >
                    Format
                  </Button>
                </>
              )
            }
          />
          <Box sx={{ p: 2 }}>
            <Box
              sx={{
                position: "relative",
                borderRadius: 1.5,
                backgroundColor: "#0b1220",
                border: optionsValid ? "1px solid rgba(255,255,255,0.06)" : "1px solid rgba(239,68,68,0.5)",
                overflow: "hidden",
                "&::before": {
                  content: '""',
                  position: "absolute",
                  top: 8, left: 10,
                  width: 10, height: 10,
                  borderRadius: "50%",
                  background: "#fb7185",
                  boxShadow: "16px 0 #fbbf24, 32px 0 #34d399",
                  zIndex: 1,
                },
              }}
            >
              <TextField
                fullWidth
                name="options"
                value={state.options || ""}
                onChange={handleChange}
                multiline
                minRows={4}
                maxRows={16}
                placeholder='{ "model": "text-embedding-3-large", "api_key": "..." }'
                InputProps={{
                  sx: {
                    fontFamily: FONT_MONO,
                    fontSize: "0.82rem",
                    color: "#cbd5e1",
                    pt: 4.5, pl: 1, pr: 1, pb: 1,
                    "& fieldset": { border: "none" },
                    "& textarea": {
                      caretColor: ACCENT,
                    },
                    "& textarea::placeholder": {
                      color: "rgba(148,163,184,0.5)",
                    },
                  },
                }}
              />
            </Box>
            {!optionsValid && (
              <Box
                sx={{
                  mt: 1,
                  px: 1.25, py: 0.75,
                  borderRadius: 1,
                  backgroundColor: "rgba(239,68,68,0.06)",
                  border: "1px solid rgba(239,68,68,0.25)",
                  fontFamily: FONT_MONO,
                  fontSize: "0.72rem",
                  color: "#9f3a38",
                }}
              >
                Options is not valid JSON — save will still work but the runtime may reject it.
              </Box>
            )}
          </Box>
        </TileCard>
      </Box>

      {/* SAVE BAR */}
      <Box
        sx={{
          mt: 2.5,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 1,
          flexWrap: "wrap",
        }}
      >
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.75,
            color: "text.secondary",
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            letterSpacing: "0.04em",
          }}
        >
          <AltRoute sx={{ fontSize: 14, color: ACCENT }} />
          {dirty
            ? `${Object.keys(state).filter((k) => state[k] !== embedding[k] && ["name","class_name","options","privacy","description","dimension"].includes(k)).length} field(s) changed`
            : "no changes"}
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Close />}
            onClick={() => navigate("/embeddings")}
            sx={{
              textTransform: "none",
              color: "text.secondary",
              borderColor: "rgba(15,23,42,0.15)",
              "&:hover": { borderColor: "rgba(15,23,42,0.4)", backgroundColor: "rgba(15,23,42,0.03)" },
            }}
          >
            {t("common.cancel")}
          </Button>
          <Button
            type="submit"
            variant="contained"
            startIcon={saving ? <CircularProgress size={14} color="inherit" /> : <Save />}
            disabled={saving || !dirty}
            sx={{
              textTransform: "none",
              fontWeight: 700,
              background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
              boxShadow: `0 4px 14px ${ACCENT}55`,
              "&:hover": {
                background: `linear-gradient(135deg, ${ACCENT} 0%, #134e4a 100%)`,
                boxShadow: `0 6px 18px ${ACCENT}77`,
              },
              "&.Mui-disabled": {
                background: "rgba(15,23,42,0.06)",
                color: "rgba(15,23,42,0.3)",
                boxShadow: "none",
              },
            }}
          >
            {saving ? "Saving…" : t("embeddings.edit.saveChanges")}
          </Button>
        </Box>
      </Box>
    </form>
  );
}
