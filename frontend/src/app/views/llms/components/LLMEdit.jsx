import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Chip, CircularProgress, Grid, InputAdornment,
  MenuItem, TextField, Typography, styled,
} from "@mui/material";
import {
  Save, Close, Psychology, Code, Public, Lock, Title,
  Description, MemoryRounded, AttachMoney, AltRoute,
  Storage, Bolt, CheckCircle, Refresh,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { JsonEditor } from "json-edit-react";
import { PROVIDER_CONFIG } from "../providerConfig";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const ACCENT = "#0284c7";        // sky-700
const ACCENT_DARK = "#0369a1";   // sky-800
const ACCENT_SOFT = "rgba(2,132,199,0.10)";

// Per-provider palette mirrors the LLM list/info pages — the Class
// field's adornment hue tracks the picked provider.
const PROVIDER_COLORS = [
  { match: /openai|o1|gpt/i,         color: "#0891b2", short: "OpenAI" },
  { match: /azureopenai/i,           color: "#1d4ed8", short: "Azure" },
  { match: /anthropic|claude/i,      color: "#c2410c", short: "Anthropic" },
  { match: /huggingface/i,           color: "#eab308", short: "HF" },
  { match: /ollama/i,                color: "#7c3aed", short: "Ollama" },
  { match: /gemini|google|vertex/i,  color: "#dc2626", short: "Gemini" },
  { match: /mistral/i,               color: "#f97316", short: "Mistral" },
  { match: /cohere/i,                color: "#ec4899", short: "Cohere" },
  { match: /groq/i,                  color: "#10b981", short: "Groq" },
  { match: /perplex/i,               color: "#06b6d4", short: "Perplexity" },
  { match: /bedrock|aws/i,           color: "#fb923c", short: "Bedrock" },
  { match: /llamacpp|llama_cpp/i,    color: "#a16207", short: "LlamaCpp" },
  { match: /openrouter/i,            color: "#be185d", short: "OpenRouter" },
  { match: /xai|grok/i,              color: "#374151", short: "xAI" },
];
const providerMeta = (className) => {
  if (!className) return { color: "#64748b", short: "—" };
  return PROVIDER_COLORS.find((p) => p.match.test(className)) || { color: "#64748b", short: className };
};

// OpenAI-compatible classes — gate the "List Models" button. These can
// be probed remotely.
const OPENAI_COMPAT_CLASSES = new Set([
  "OpenAI", "OpenAILike", "LiteLLM", "vLLM", "Grok", "Gemini", "GeminiMultiModal",
]);

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

const fieldSx = {
  "& .MuiOutlinedInput-root": {
    "& fieldset": { borderColor: "rgba(15,23,42,0.12)" },
    "&:hover fieldset": { borderColor: `${ACCENT}55` },
    "&.Mui-focused fieldset": { borderColor: ACCENT, borderWidth: 1.5 },
  },
  "& .MuiInputLabel-root.Mui-focused": { color: ACCENT },
};

// Live cost calculator — quick 100K-in / 50K-out sanity reading so
// admins can sense-check the per-1M rates without doing math.
function CostCalculator({ inputCost, outputCost }) {
  const inNum = Number(inputCost) || 0;
  const outNum = Number(outputCost) || 0;
  // Per-million rates: scale token counts to fractions of 1M.
  const sample100k = inNum * 0.1 + outNum * 0.05;   // 100K in + 50K out
  const million = inNum * 1 + outNum * 0.5;          //  1M in + 500K out
  if (sample100k === 0) {
    return (
      <Box
        sx={{
          mt: 1.5,
          px: 1.5, py: 1,
          backgroundColor: "rgba(15,23,42,0.025)",
          border: "1px dashed rgba(15,23,42,0.10)",
          fontFamily: FONT_MONO,
          fontSize: "0.74rem",
          color: "text.disabled",
          letterSpacing: "0.04em",
        }}
      >
        ▸ no cost set — calls will record as $0
      </Box>
    );
  }
  return (
    <Box
      sx={{
        mt: 1.5,
        px: 1.5, py: 1,
        backgroundColor: ACCENT_SOFT,
        borderLeft: `3px solid ${ACCENT}`,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        flexWrap: "wrap",
      }}
    >
      <Bolt sx={{ fontSize: 16, color: ACCENT }} />
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.74rem",
          fontWeight: 700,
          color: ACCENT_DARK,
          letterSpacing: "0.02em",
        }}
      >
        100K in + 50K out ≈ <Box component="span" sx={{ color: ACCENT, fontSize: "0.85rem" }}>${sample100k.toFixed(4)}</Box>
        <Box
          component="span"
          sx={{
            ml: 1.5,
            color: "rgba(2,132,199,0.6)",
            fontSize: "0.68rem",
            fontWeight: 600,
          }}
        >
          {`// 1M in + 500K out ≈ $${million.toFixed(2)}`}
        </Box>
      </Box>
    </Box>
  );
}

// Discovered-models chip cloud — flowing chips with sky-glow ring on
// the currently-selected model. The marquee element of the page.
function DiscoveredModels({ models, selected, onPick, onRefresh, loading }) {
  if (!models) return null;
  if (models.length === 0 && !loading) {
    return (
      <Box
        sx={{
          mt: 1.5,
          p: 1.5,
          backgroundColor: "rgba(239,68,68,0.05)",
          borderLeft: "3px solid #dc2626",
          display: "flex",
          alignItems: "center",
          gap: 1,
        }}
      >
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.74rem",
            color: "#9f3a38",
            fontWeight: 600,
          }}
        >
          ▸ provider returned no models — check API key + base URL
        </Box>
        <Button
          size="small"
          startIcon={<Refresh fontSize="small" />}
          onClick={onRefresh}
          sx={{ textTransform: "none", color: "#dc2626", fontSize: "0.74rem" }}
        >
          retry
        </Button>
      </Box>
    );
  }
  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        background: `linear-gradient(180deg, ${ACCENT_SOFT}, transparent 70%)`,
        border: `1px solid ${ACCENT}25`,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 1,
        }}
      >
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.62rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: ACCENT,
          }}
        >
          ▸ {models.length} model{models.length === 1 ? "" : "s"} available · click to select
        </Box>
        <Button
          size="small"
          startIcon={<Refresh fontSize="small" />}
          onClick={onRefresh}
          sx={{
            textTransform: "none",
            fontSize: "0.7rem",
            color: ACCENT,
            "&:hover": { backgroundColor: `${ACCENT}10` },
          }}
        >
          refresh
        </Button>
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6, maxHeight: 180, overflowY: "auto" }}>
        {models.map((m) => {
          const isSel = selected === m.id;
          return (
            <Box
              key={m.id}
              onClick={() => onPick(m.id)}
              sx={{
                display: "inline-flex",
                alignItems: "center",
                gap: 0.4,
                px: 0.85, py: 0.4,
                cursor: "pointer",
                fontFamily: FONT_MONO,
                fontSize: "0.7rem",
                fontWeight: 700,
                letterSpacing: "0.02em",
                color: isSel ? "#fff" : ACCENT_DARK,
                backgroundColor: isSel ? ACCENT : "#fff",
                border: `1px solid ${isSel ? ACCENT_DARK : `${ACCENT}33`}`,
                boxShadow: isSel ? `0 0 0 3px ${ACCENT}33, 0 4px 10px ${ACCENT}55` : "none",
                transition: "all 0.15s ease",
                "&:hover": {
                  backgroundColor: isSel ? ACCENT_DARK : `${ACCENT}10`,
                  borderColor: ACCENT,
                  transform: "translateY(-1px)",
                },
              }}
            >
              {isSel && <CheckCircle sx={{ fontSize: 12 }} />}
              {m.id}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

export default function LLMEdit({ llm }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({});
  const [saving, setSaving] = useState(false);
  const [remoteModels, setRemoteModels] = useState(null);
  const [loadingModels, setLoadingModels] = useState(false);

  useEffect(() => {
    setState(llm);
  }, [llm]);

  const meta = providerMeta(state.class_name);
  const isPublic = (state.privacy || "").toLowerCase() === "public";
  const canListModels = OPENAI_COMPAT_CLASSES.has(state.class_name);

  const handleChange = (e) => {
    if (e?.persist) e.persist();
    setState((s) => ({ ...s, [e.target.name]: e.target.value }));
  };

  const handleListModels = async () => {
    setLoadingModels(true);
    setRemoteModels(null);
    try {
      const result = await api.get("/tools/openai-compat/models/" + llm.id, auth.user.token);
      setRemoteModels(result.models || []);
    } catch {
      setRemoteModels([]);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSelectModel = (modelId) => {
    setState((s) => ({ ...s, options: { ...(s.options || {}), model: modelId } }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    setSaving(true);
    const update = {};
    ["name", "class_name", "options", "privacy", "description", "input_cost", "output_cost"].forEach((k) => {
      if (state[k] !== llm[k]) update[k] = state[k];
    });
    if (state.context_window !== llm.context_window) {
      update.context_window = parseInt(state.context_window) || 0;
    }
    api.patch("/llms/" + llm.id, update, auth.user.token)
      .then(() => {
        toast.success(t("common.saved") || "Saved");
        window.location.href = "/admin/llm/" + llm.id;
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  const dirtyKeys = useMemo(() => {
    const keys = ["name", "class_name", "options", "privacy", "description", "input_cost", "output_cost", "context_window"];
    return keys.filter((k) => state[k] !== llm[k]);
  }, [state, llm]);
  const dirty = dirtyKeys.length > 0;

  // JSON-validity proxy (JsonEditor manages structure, but flag if
  // someone has wedged invalid types — best-effort).
  const optionsKeyCount = state.options && typeof state.options === "object"
    ? Object.keys(state.options).length
    : 0;

  return (
    <form onSubmit={handleSubmit}>
      {/* IDENTITY */}
      <TileCard elevation={0} accent={ACCENT}>
        <TileHeader
          icon={<Psychology />}
          title={t("llms.edit.title", { name: llm.name })}
          subtitle="Provider, identity, and visibility"
          accent={ACCENT}
          action={
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
              {/* Live provider chip — same colour as the icon adornment */}
              <Chip
                icon={<Code sx={{ color: `${meta.color} !important`, fontSize: 14 }} />}
                label={meta.short}
                size="small"
                sx={{
                  height: 24,
                  fontFamily: FONT_MONO,
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  backgroundColor: `${meta.color}10`,
                  color: meta.color,
                  border: `1px solid ${meta.color}33`,
                  "& .MuiChip-icon": { ml: 0.5 },
                }}
              />
              {dirty && (
                <Chip
                  label={`UNSAVED · ${dirtyKeys.length}`}
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
              )}
            </Box>
          }
        />
        <Box sx={{ p: 2.5 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                name="name"
                label={t("llms.edit.name")}
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
              <TextField
                select
                fullWidth
                name="class_name"
                label={t("llms.edit.className")}
                value={state.class_name || ""}
                onChange={handleChange}
                InputLabelProps={{ shrink: true }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Code sx={{ fontSize: 18, color: meta.color, transition: "color 0.25s ease" }} />
                    </InputAdornment>
                  ),
                }}
                sx={fieldSx}
              >
                {Object.entries(PROVIDER_CONFIG).map(([key, cfg]) => {
                  const m = providerMeta(key);
                  return (
                    <MenuItem key={key} value={key} sx={{ fontFamily: FONT_MONO, fontSize: "0.85rem" }}>
                      <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, width: "100%" }}>
                        <Box sx={{ width: 8, height: 8, background: m.color, flexShrink: 0 }} />
                        <Box component="span" sx={{ fontWeight: 700 }}>{cfg.label}</Box>
                        <Box
                          component="span"
                          sx={{
                            ml: "auto",
                            fontSize: "0.62rem",
                            color: "text.disabled",
                            fontFamily: FONT_MONO,
                            letterSpacing: "0.04em",
                          }}
                        >
                          {key}
                        </Box>
                      </Box>
                    </MenuItem>
                  );
                })}
              </TextField>
            </Grid>

            <Grid item xs={12} sm={6}>
              <TextField
                select
                fullWidth
                name="privacy"
                label={t("llms.edit.privacy")}
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
                name="description"
                label={t("llms.edit.description")}
                value={state.description || ""}
                onChange={handleChange}
                InputLabelProps={{ shrink: true }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
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

      {/* GEOMETRY · PRICING */}
      <Box sx={{ mt: 2.5 }}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<MemoryRounded />}
            title="Geometry · Pricing"
            subtitle="Context window and per-1M-token rates"
            accent={ACCENT}
          />
          <Box sx={{ p: 2.5 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  name="context_window"
                  type="number"
                  label={t("llms.edit.contextWindow")}
                  value={state.context_window ?? ""}
                  onChange={handleChange}
                  helperText={t("llms.edit.contextHelp")}
                  InputLabelProps={{ shrink: true }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <MemoryRounded sx={{ fontSize: 18, color: "#7c3aed" }} />
                      </InputAdornment>
                    ),
                    endAdornment: state.context_window > 0 && (
                      <InputAdornment position="end">
                        <Box
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.7rem",
                            color: "#7c3aed",
                            letterSpacing: "0.04em",
                            fontWeight: 700,
                          }}
                        >
                          tok
                        </Box>
                      </InputAdornment>
                    ),
                  }}
                  sx={fieldSx}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  name="input_cost"
                  type="number"
                  inputProps={{ step: "0.0001" }}
                  label={t("llms.edit.inputCost")}
                  value={state.input_cost ?? ""}
                  onChange={handleChange}
                  helperText="$ per 1M input tokens"
                  InputLabelProps={{ shrink: true }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <AttachMoney sx={{ fontSize: 18, color: "#0891b2" }} />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <Box
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.66rem",
                            color: "#0891b2",
                            letterSpacing: "0.04em",
                            fontWeight: 700,
                          }}
                        >
                          /1M
                        </Box>
                      </InputAdornment>
                    ),
                  }}
                  sx={fieldSx}
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  name="output_cost"
                  type="number"
                  inputProps={{ step: "0.0001" }}
                  label={t("llms.edit.outputCost")}
                  value={state.output_cost ?? ""}
                  onChange={handleChange}
                  helperText="$ per 1M output tokens"
                  InputLabelProps={{ shrink: true }}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <AttachMoney sx={{ fontSize: 18, color: "#0d9488" }} />
                      </InputAdornment>
                    ),
                    endAdornment: (
                      <InputAdornment position="end">
                        <Box
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.66rem",
                            color: "#0d9488",
                            letterSpacing: "0.04em",
                            fontWeight: 700,
                          }}
                        >
                          /1M
                        </Box>
                      </InputAdornment>
                    ),
                  }}
                  sx={fieldSx}
                />
              </Grid>
            </Grid>
            <CostCalculator inputCost={state.input_cost} outputCost={state.output_cost} />
          </Box>
        </TileCard>
      </Box>

      {/* PROVIDER OPTIONS */}
      <Box sx={{ mt: 2.5 }}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<Storage />}
            title={t("llms.edit.options")}
            subtitle="Tree-edit the provider-specific JSON config"
            accent={ACCENT}
            action={
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                <Chip
                  icon={<Storage sx={{ color: `${ACCENT} !important`, fontSize: 14 }} />}
                  label={`${optionsKeyCount} key${optionsKeyCount === 1 ? "" : "s"}`}
                  size="small"
                  sx={{
                    height: 22,
                    fontFamily: FONT_MONO,
                    fontSize: "0.66rem",
                    fontWeight: 700,
                    backgroundColor: ACCENT_SOFT,
                    color: ACCENT,
                    border: `1px solid ${ACCENT}33`,
                  }}
                />
                {canListModels && (
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={
                      loadingModels
                        ? <CircularProgress size={12} sx={{ color: ACCENT }} />
                        : <Refresh fontSize="small" />
                    }
                    onClick={handleListModels}
                    disabled={loadingModels}
                    sx={{
                      textTransform: "none",
                      fontWeight: 700,
                      fontSize: "0.74rem",
                      color: ACCENT,
                      borderColor: `${ACCENT}66`,
                      "&:hover": { borderColor: ACCENT, backgroundColor: ACCENT_SOFT },
                    }}
                  >
                    {loadingModels
                      ? (t("llms.edit.loading") || "Probing…")
                      : (t("llms.edit.listModels") || "Discover models")}
                  </Button>
                )}
              </Box>
            }
          />
          <Box sx={{ p: 2 }}>
            {/* Discovered models cloud — appears above editor */}
            <DiscoveredModels
              models={remoteModels}
              selected={state.options?.model}
              onPick={handleSelectModel}
              onRefresh={handleListModels}
              loading={loadingModels}
            />

            {/* JSON tree editor — soft sky panel */}
            <Box
              sx={{
                mt: remoteModels ? 1.5 : 0,
                p: 1.5,
                backgroundColor: "#f8fafc",
                border: `1px solid ${ACCENT}25`,
                "& .json-editor-container": {
                  fontFamily: FONT_MONO,
                  fontSize: "0.82rem",
                },
              }}
            >
              <JsonEditor
                data={state.options || {}}
                setData={(updated) => setState((s) => ({ ...s, options: updated }))}
                restrictDelete={false}
                rootName={t("llms.edit.options")}
                numberType="float"
              />
            </Box>
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
            color: dirty ? ACCENT_DARK : "text.disabled",
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            letterSpacing: "0.04em",
            fontWeight: 700,
          }}
        >
          <AltRoute sx={{ fontSize: 14, color: dirty ? ACCENT : "text.disabled" }} />
          {dirty
            ? `${dirtyKeys.length} field${dirtyKeys.length === 1 ? "" : "s"} changed · ${dirtyKeys.join(", ")}`
            : "no changes"}
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<Close />}
            onClick={() => navigate("/llms")}
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
                background: `linear-gradient(135deg, ${ACCENT} 0%, #075985 100%)`,
                boxShadow: `0 6px 18px ${ACCENT}77`,
              },
              "&.Mui-disabled": {
                background: "rgba(15,23,42,0.06)",
                color: "rgba(15,23,42,0.3)",
                boxShadow: "none",
              },
            }}
          >
            {saving ? "Saving…" : t("llms.edit.saveChanges")}
          </Button>
        </Box>
      </Box>
    </form>
  );
}
