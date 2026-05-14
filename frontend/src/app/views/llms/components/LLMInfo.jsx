import { useState, useMemo } from "react";
import {
  Box, Button, Card, Grid, IconButton, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Edit, Delete, Psychology, Storage, Public, Lock, ContentCopy,
  OpenInNew, Code, MemoryRounded, AttachMoney, Workspaces,
  QrCode2, AltRoute, Description,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import QRCode from "react-qr-code";
import ReactJson from "@microlink/react-json-view";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Sky-700 — same family as the LLMs list page.
const ACCENT = "#0284c7";        // sky-700
const ACCENT_DARK = "#0369a1";   // sky-800

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

const formatContext = (n) => {
  if (!n) return null;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return `${n}`;
};

const formatCost = (v) => {
  if (v == null || v === 0) return null;
  const num = Number(v);
  if (num < 0.001) return num.toFixed(5);
  if (num < 1) return num.toFixed(4);
  return num.toFixed(2);
};

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

const StatCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  padding: 16,
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    zIndex: 2,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
}));

function StatTile({ icon, label, value, accent = ACCENT, sub }) {
  return (
    <StatCard accent={accent} elevation={0}>
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25 }}>
        <Box
          sx={{
            width: 38, height: 38, flexShrink: 0,
            borderRadius: 1.5,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${accent}25, ${accent}12)`,
            border: `1px solid ${accent}33`,
            color: accent,
            "& svg": { fontSize: 20 },
          }}
        >
          {icon}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.6rem",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              fontWeight: 700,
              color: "text.secondary",
              lineHeight: 1,
            }}
          >
            {label}
          </Box>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "1.4rem",
              fontWeight: 800,
              color: accent,
              lineHeight: 1.1,
              mt: 0.4,
              wordBreak: "break-word",
            }}
          >
            {value}
          </Box>
          {sub && (
            <Box
              component="span"
              sx={{
                display: "block",
                fontFamily: FONT_MONO,
                fontSize: "0.62rem",
                color: "text.disabled",
                mt: 0.3,
              }}
            >
              {sub}
            </Box>
          )}
        </Box>
      </Box>
    </StatCard>
  );
}

function AttrRow({ icon: Icon, label, children, accent = ACCENT, last = false }) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 2,
        px: 2.5, py: 1.5,
        borderBottom: last ? "none" : "1px solid rgba(15,23,42,0.06)",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.75,
          minWidth: 160,
          flexShrink: 0,
        }}
      >
        {Icon && (
          <Icon sx={{ fontSize: 14, color: accent, opacity: 0.7 }} />
        )}
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.66rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            fontWeight: 700,
            color: "text.secondary",
          }}
        >
          {label}
        </Box>
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}

function MonoPill({ value, color = ACCENT, icon: Icon }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.85, py: 0.35,
        borderRadius: 0.75,
        backgroundColor: `${color}10`,
        border: `1px solid ${color}33`,
      }}
    >
      {Icon && <Icon sx={{ fontSize: 12, color }} />}
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.74rem",
          fontWeight: 700,
          letterSpacing: "0.04em",
          color,
        }}
      >
        {value}
      </Box>
    </Box>
  );
}

// Visualise context window as a sharp horizontal bar so users can
// compare at a glance against a 1M reference. Logarithmic-ish scale
// because contexts span 4K → 2M+.
function ContextScale({ tokens }) {
  if (!tokens) return null;
  // Log scale anchored at 4K-1M (most providers); fits visually for
  // models on either end without distorting the small-context cluster.
  const min = Math.log(4_000);
  const max = Math.log(2_000_000);
  const lt = Math.log(tokens);
  const pct = Math.max(2, Math.min(100, ((lt - min) / (max - min)) * 100));
  // Hue ramp: amber (small) → sky (mid) → fuchsia (huge).
  const ramp = tokens < 16_000
    ? "#f59e0b"
    : tokens < 128_000
      ? ACCENT
      : tokens < 500_000
        ? "#7c3aed"
        : "#c026d3";
  return (
    <Box sx={{ width: "100%", maxWidth: 320 }}>
      <Box
        sx={{
          height: 6,
          backgroundColor: "rgba(15,23,42,0.06)",
          overflow: "hidden",
          position: "relative",
          "&::before": {
            content: '""',
            position: "absolute",
            left: "20%", top: 0, bottom: 0,
            width: 1, background: "rgba(15,23,42,0.12)",
          },
          "&::after": {
            content: '""',
            position: "absolute",
            left: "60%", top: 0, bottom: 0,
            width: 1, background: "rgba(15,23,42,0.12)",
          },
        }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${ramp}66, ${ramp})`,
            transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
          }}
        />
      </Box>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          mt: 0.4,
          fontFamily: FONT_MONO,
          fontSize: "0.6rem",
          color: "text.disabled",
          letterSpacing: "0.04em",
        }}
      >
        <Box component="span">4K</Box>
        <Box component="span">128K</Box>
        <Box component="span">2M</Box>
      </Box>
    </Box>
  );
}

export default function LLMInfo({ llm, projects, usedBy = 0 }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const auth = useAuth();
  const [showQR, setShowQR] = useState(false);

  const handleDelete = () => {
    if (!window.confirm(t("llms.info.confirmDelete", { name: llm.name }))) return;
    api.delete("/llms/" + llm.id, auth.user.token)
      .then(() => navigate("/llms"))
      .catch(() => {});
  };

  const copyName = () => {
    navigator.clipboard.writeText(llm.name).then(() => {
      toast.success(t("common.copied") || "Copied");
    });
  };

  const meta = providerMeta(llm.class_name);
  const isPublic = (llm.privacy || "").toLowerCase() === "public";
  const ctxFmt = formatContext(llm.context_window);
  const inCost = formatCost(llm.input_cost);
  const outCost = formatCost(llm.output_cost);
  const projectsUsing = (projects || []).filter((p) => p.llm === llm.name);

  // Options can come back as object or stringified JSON depending on
  // the route — handle both without crashing.
  const optionsObj = useMemo(() => {
    if (!llm.options) return null;
    if (typeof llm.options === "object") return llm.options;
    try { return JSON.parse(llm.options); } catch { return null; }
  }, [llm.options]);
  const optionsCount = optionsObj ? Object.keys(optionsObj).length : 0;

  return (
    <Box>
      <Grid container spacing={2} sx={{ mb: 2.5 }}>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Code />}
            label="Provider"
            value={meta.short}
            accent={meta.color}
            sub={llm.class_name || "—"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<MemoryRounded />}
            label="Context"
            value={ctxFmt || "—"}
            accent="#7c3aed"
            sub={ctxFmt ? "tokens" : "default 4K"}
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<AttachMoney />}
            label="Cost / 1K"
            value={
              inCost || outCost
                ? `$${inCost || "0"}/$${outCost || "0"}`
                : "free"
            }
            accent="#10b981"
            sub="in / out"
          />
        </Grid>
        <Grid item xs={6} md={3}>
          <StatTile
            icon={<Workspaces />}
            label="Used by"
            value={usedBy}
            accent="#0891b2"
            sub={usedBy === 1 ? "project" : "projects"}
          />
        </Grid>
      </Grid>

      <Grid container spacing={2.5}>
        <Grid item xs={12} md={4}>
          <TileCard elevation={0} accent={meta.color}>
            <Box sx={{ p: 3, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
              <Box
                sx={{
                  width: 88, height: 88,
                  borderRadius: "50%",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background: `radial-gradient(circle at 30% 30%, ${meta.color}33, ${meta.color}11 60%, transparent 70%)`,
                  position: "relative",
                  mb: 1.5,
                  "&::before": {
                    content: '""',
                    position: "absolute",
                    inset: -6,
                    borderRadius: "50%",
                    border: `1px dashed ${meta.color}55`,
                    animation: `${pulse} 4s ease-in-out infinite`,
                  },
                }}
              >
                <Psychology sx={{ fontSize: 40, color: meta.color }} />
              </Box>
              <Box
                component="span"
                sx={{
                  display: "block",
                  fontFamily: FONT_MONO,
                  fontSize: "1.1rem",
                  fontWeight: 800,
                  color: "text.primary",
                  letterSpacing: "0.02em",
                  mb: 0.5,
                  wordBreak: "break-word",
                }}
              >
                {llm.name}
              </Box>
              <Box
                component="span"
                sx={{
                  display: "block",
                  fontFamily: FONT_MONO,
                  fontSize: "0.66rem",
                  color: "text.disabled",
                  letterSpacing: "0.06em",
                  mb: 1,
                }}
              >
                LLM/{String(llm.id || 0).padStart(4, "0")}
              </Box>
              <Box sx={{ mb: 1.5 }}>
                <MonoPill value={meta.short} color={meta.color} icon={Code} />
              </Box>
              <Box sx={{ display: "flex", gap: 1, justifyContent: "center", flexWrap: "wrap" }}>
                <Tooltip title={t("common.copy") || "Copy name"} arrow>
                  <IconButton
                    size="small"
                    onClick={copyName}
                    sx={{ color: meta.color, "&:hover": { backgroundColor: `${meta.color}15` } }}
                  >
                    <ContentCopy fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={showQR ? "Hide QR" : "Share via QR"} arrow>
                  <IconButton
                    size="small"
                    onClick={() => setShowQR((v) => !v)}
                    sx={{ color: meta.color, "&:hover": { backgroundColor: `${meta.color}15` } }}
                  >
                    <QrCode2 fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
              {showQR && (
                <Box
                  sx={{
                    mt: 2,
                    p: 1.5,
                    background: "#fff",
                    border: `1px solid ${meta.color}33`,
                    display: "inline-block",
                  }}
                >
                  <QRCode
                    size={120}
                    style={{ width: 120, height: 120 }}
                    value={window.location.href || "RESTai"}
                    viewBox="0 0 256 256"
                  />
                </Box>
              )}
            </Box>

            {auth.user.is_admin && (
              <Box
                sx={{
                  px: 2, py: 1.5,
                  borderTop: "1px solid rgba(15,23,42,0.06)",
                  display: "flex",
                  gap: 1,
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                }}
              >
                <Button
                  variant="contained"
                  startIcon={<Edit fontSize="small" />}
                  onClick={() => navigate("/llm/" + llm.id + "/edit")}
                  sx={{
                    textTransform: "none",
                    fontWeight: 700,
                    background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                    boxShadow: `0 4px 14px ${ACCENT}55`,
                    "&:hover": {
                      background: `linear-gradient(135deg, ${ACCENT} 0%, #075985 100%)`,
                      boxShadow: `0 6px 18px ${ACCENT}77`,
                    },
                  }}
                >
                  {t("common.edit")}
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Delete fontSize="small" />}
                  onClick={handleDelete}
                  sx={{
                    textTransform: "none",
                    color: "#ef4444",
                    borderColor: "rgba(239,68,68,0.4)",
                    "&:hover": { borderColor: "#ef4444", backgroundColor: "rgba(239,68,68,0.06)" },
                  }}
                >
                  {t("common.delete")}
                </Button>
              </Box>
            )}
          </TileCard>
        </Grid>

        {/* Configuration + Options + Projects */}
        <Grid item xs={12} md={8}>
          <TileCard elevation={0} accent={ACCENT}>
            <TileHeader
              icon={<AltRoute />}
              title={t("llms.info.title") || "Configuration"}
              subtitle="Provider class, privacy, geometry, pricing"
              accent={ACCENT}
            />
            <Box>
              <AttrRow icon={Code} label={t("llms.info.class")} accent={ACCENT}>
                <MonoPill value={meta.short} color={meta.color} icon={Code} />
                <Box
                  component="span"
                  sx={{
                    display: "block",
                    fontFamily: FONT_MONO,
                    fontSize: "0.66rem",
                    color: "text.disabled",
                    letterSpacing: "0.02em",
                    mt: 0.4,
                  }}
                >
                  {llm.class_name}
                </Box>
              </AttrRow>
              <AttrRow icon={isPublic ? Public : Lock} label={t("llms.info.privacy")} accent={ACCENT}>
                <MonoPill
                  value={(llm.privacy || "—").toUpperCase()}
                  color={isPublic ? "#10b981" : "#f59e0b"}
                  icon={isPublic ? Public : Lock}
                />
              </AttrRow>
              <AttrRow icon={MemoryRounded} label={t("llms.info.contextWindow")} accent={ACCENT}>
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  <MonoPill
                    value={`${(llm.context_window || 4096).toLocaleString()} ${t("llms.info.tokens")}`}
                    color="#7c3aed"
                    icon={MemoryRounded}
                  />
                  {llm.context_window > 0 && <ContextScale tokens={llm.context_window} />}
                </Box>
              </AttrRow>
              <AttrRow icon={AttachMoney} label="Input cost / 1K" accent={ACCENT}>
                {inCost
                  ? <MonoPill value={`$${inCost}`} color="#0891b2" icon={AttachMoney} />
                  : <Box component="span" sx={{ color: "text.disabled", fontFamily: FONT_MONO, fontSize: "0.78rem" }}>free</Box>}
              </AttrRow>
              <AttrRow icon={AttachMoney} label="Output cost / 1K" accent={ACCENT}>
                {outCost
                  ? <MonoPill value={`$${outCost}`} color="#0d9488" icon={AttachMoney} />
                  : <Box component="span" sx={{ color: "text.disabled", fontFamily: FONT_MONO, fontSize: "0.78rem" }}>free</Box>}
              </AttrRow>
              <AttrRow icon={Description} label={t("llms.info.description")} accent={ACCENT} last>
                {llm.description ? (
                  <Typography variant="body2" sx={{ color: "text.primary", whiteSpace: "pre-wrap" }}>
                    {llm.description}
                  </Typography>
                ) : (
                  <Box component="span" sx={{ color: "text.disabled", fontStyle: "italic", fontSize: "0.85rem" }}>—</Box>
                )}
              </AttrRow>
            </Box>
          </TileCard>

          {optionsObj && (
            <Box sx={{ mt: 2.5 }}>
              <TileCard elevation={0} accent={ACCENT}>
                <TileHeader
                  icon={<Storage />}
                  title={t("llms.info.options")}
                  subtitle={`${optionsCount} key${optionsCount === 1 ? "" : "s"}`}
                  accent={ACCENT}
                />
                <Box sx={{ p: 2 }}>
                  <Box
                    sx={{
                      borderRadius: 1.5,
                      backgroundColor: "#0b1220",
                      border: "1px solid rgba(255,255,255,0.06)",
                      p: 1.5,
                      position: "relative",
                      overflow: "auto",
                      "& .react-json-view": {
                        backgroundColor: "transparent !important",
                        fontFamily: FONT_MONO,
                        fontSize: "0.78rem",
                      },
                      "&::before": {
                        content: '""',
                        position: "absolute",
                        top: 8, left: 10,
                        width: 10, height: 10,
                        borderRadius: "50%",
                        background: "#fb7185",
                        boxShadow: "16px 0 #fbbf24, 32px 0 #34d399",
                      },
                    }}
                  >
                    <Box sx={{ pl: 6, pt: 0.5 }}>
                      <ReactJson
                        src={optionsObj}
                        enableClipboard
                        name={false}
                        theme="ocean"
                        style={{ backgroundColor: "transparent" }}
                        displayDataTypes={false}
                        collapsed={1}
                      />
                    </Box>
                  </Box>
                </Box>
              </TileCard>
            </Box>
          )}

          {/* Projects using this LLM */}
          {projectsUsing.length > 0 && (
            <Box sx={{ mt: 2.5 }}>
              <TileCard elevation={0} accent="#7c3aed">
                <TileHeader
                  icon={<Workspaces />}
                  title={t("llms.info.usedBy") || "Projects using this model"}
                  subtitle={`${projectsUsing.length} attached`}
                  accent="#7c3aed"
                />
                <Box sx={{ p: 1.25, display: "flex", flexWrap: "wrap", gap: 1 }}>
                  {projectsUsing.map((p) => (
                    <Box
                      key={p.id}
                      onClick={() => navigate(`/project/${p.id}`)}
                      sx={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 0.75,
                        px: 1.25, py: 0.75,
                        borderRadius: 1,
                        cursor: "pointer",
                        backgroundColor: "rgba(124,58,237,0.06)",
                        border: "1px solid rgba(124,58,237,0.25)",
                        transition: "all 0.15s ease",
                        "&:hover": {
                          backgroundColor: "rgba(124,58,237,0.12)",
                          borderColor: "#7c3aed",
                          transform: "translateY(-1px)",
                        },
                      }}
                    >
                      <Box
                        component="span"
                        sx={{
                          fontWeight: 600,
                          fontSize: "0.84rem",
                          color: "#5b21b6",
                        }}
                      >
                        {p.name}
                      </Box>
                      <OpenInNew sx={{ fontSize: 12, color: "#7c3aed", opacity: 0.7 }} />
                    </Box>
                  ))}
                </Box>
              </TileCard>
            </Box>
          )}
        </Grid>
      </Grid>
    </Box>
  );
}
