import { Box, Typography, styled, keyframes } from "@mui/material";
import { useTranslation } from "react-i18next";

const pulse = keyframes`
  0%   { opacity: 1;   transform: scale(1); }
  50%  { opacity: 0.6; transform: scale(1.3); }
  100% { opacity: 1;   transform: scale(1); }
`;

// Provider detection is fuzzy by design — users can name their LLM
// anything and we only really get the model's display name + class.
// The map below is a best-effort; fall back to a neutral indigo so the
// fleet never renders blank because of a new provider we don't know.
const PROVIDER_STYLES = [
  { match: /openai|gpt-|o1|o3|o4/i,         label: "OpenAI",    color: "#10a37f" },
  { match: /anthropic|claude/i,             label: "Anthropic", color: "#d97757" },
  { match: /google|gemini|palm|vertex/i,    label: "Google",    color: "#4285f4" },
  { match: /ollama/i,                       label: "Ollama",    color: "#000000" },
  { match: /grok|xai/i,                     label: "xAI",       color: "#111827" },
  { match: /mistral/i,                      label: "Mistral",   color: "#ff7000" },
  { match: /azure/i,                        label: "Azure",     color: "#0078d4" },
  { match: /bedrock|aws|amazon/i,           label: "AWS",       color: "#ff9900" },
  { match: /llama/i,                        label: "Meta",      color: "#0668e1" },
  { match: /deepseek/i,                     label: "DeepSeek",  color: "#4d6bfe" },
  { match: /qwen/i,                         label: "Qwen",      color: "#615ced" },
  { match: /litellm/i,                      label: "LiteLLM",   color: "#22c55e" },
  { match: /vllm/i,                         label: "vLLM",      color: "#1976d2" },
];

function detectProvider(name) {
  if (!name) return { label: "LLM", color: "#1976d2" };
  const hit = PROVIDER_STYLES.find((p) => p.match.test(name));
  return hit || { label: "Custom", color: "#1976d2" };
}

function formatCompact(num) {
  if (num == null) return "0";
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
  if (num >= 1_000) return (num / 1_000).toFixed(1) + "K";
  return num.toLocaleString();
}

// First letters for the avatar square. For "gpt-4o-mini" we want "GP",
// for "claude-3-opus" we want "CL", etc. Bare numbers or punctuation
// get skipped so the avatar stays legible.
function initials(name) {
  if (!name) return "?";
  const clean = name.replace(/[^a-z]/gi, "");
  return (clean.slice(0, 2) || "?").toUpperCase();
}

const FleetRow = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(1.5),
  overflowX: "auto",
  padding: theme.spacing(0.5, 0.5, 1.5, 0.5),
  // Hide scrollbar but still allow touch/trackpad scroll.
  scrollbarWidth: "thin",
  "&::-webkit-scrollbar": { height: 6 },
  "&::-webkit-scrollbar-thumb": {
    background: theme.palette.action.hover,
    borderRadius: 3,
  },
}));

const ModelCard = styled(Box, {
  shouldForwardProp: (p) => p !== "accent",
})(({ theme, accent }) => ({
  position: "relative",
  minWidth: 240,
  maxWidth: 260,
  padding: theme.spacing(2),
  borderRadius: 14,
  border: "1px solid",
  borderColor: theme.palette.divider,
  background:
    theme.palette.mode === "dark"
      ? "linear-gradient(135deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0) 100%)"
      : "linear-gradient(135deg, #ffffff 0%, #fafbff 100%)",
  overflow: "hidden",
  transition: "transform 0.2s, box-shadow 0.2s, border-color 0.2s",
  "&::before": {
    content: '""',
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 3,
    background: `linear-gradient(90deg, ${accent}, ${accent}00)`,
  },
  "&:hover": {
    transform: "translateY(-3px)",
    boxShadow: `0 12px 28px -14px ${accent}66`,
    borderColor: `${accent}55`,
  },
}));

const StatusDot = styled(Box, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  width: 8,
  height: 8,
  borderRadius: "50%",
  background: accent,
  boxShadow: `0 0 10px ${accent}`,
  animation: `${pulse} 2.4s ease-in-out infinite`,
  flexShrink: 0,
}));

export default function ModelFleet({ llms = [] }) {
  const { t } = useTranslation();
  if (!llms || llms.length === 0) return null;

  const maxTokens = Math.max(...llms.map((l) => l.total_tokens || 0), 1);

  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", mb: 1.5 }}>
        <Box>
          <Typography
            variant="overline"
            sx={{ color: "text.secondary", letterSpacing: 1.5, fontWeight: 600 }}
          >
            {t("dashboard.fleet.title")}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
            {t("dashboard.fleet.subtitle", { count: llms.length })}
          </Typography>
        </Box>
      </Box>

      <FleetRow>
        {llms.map((llm) => {
          const prov = detectProvider(llm.name);
          const share = ((llm.total_tokens || 0) / maxTokens) * 100;
          return (
            <ModelCard key={llm.name} accent={prov.color}>
              <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, mb: 1.25 }}>
                {/* Provider avatar square */}
                <Box
                  sx={{
                    width: 40,
                    height: 40,
                    borderRadius: 2,
                    flexShrink: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: prov.color,
                    color: "#fff",
                    fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                    fontWeight: 700,
                    fontSize: "0.9rem",
                    letterSpacing: "0.5px",
                    boxShadow: `0 4px 12px -4px ${prov.color}88`,
                  }}
                >
                  {initials(llm.name)}
                </Box>

                <Box sx={{ minWidth: 0, flex: 1 }}>
                  <Typography
                    sx={{
                      fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                      fontSize: "0.82rem",
                      fontWeight: 600,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      lineHeight: 1.3,
                    }}
                    title={llm.name}
                  >
                    {llm.name}
                  </Typography>
                  <Box
                    sx={{
                      mt: 0.5,
                      display: "flex",
                      alignItems: "center",
                      gap: 0.75,
                    }}
                  >
                    <StatusDot accent={prov.color} />
                    <Typography
                      variant="caption"
                      sx={{
                        color: prov.color,
                        fontWeight: 600,
                        fontSize: "0.68rem",
                        letterSpacing: 0.5,
                        textTransform: "uppercase",
                      }}
                    >
                      {prov.label}
                    </Typography>
                  </Box>
                </Box>
              </Box>

              {/* Metrics row */}
              <Box sx={{ display: "flex", gap: 2, mb: 1 }}>
                <Box>
                  <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: 0.8 }}>
                    {t("dashboard.fleet.tokens")}
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                      fontWeight: 700,
                      fontSize: "1rem",
                      fontVariantNumeric: "tabular-nums",
                      lineHeight: 1.1,
                    }}
                  >
                    {formatCompact(llm.total_tokens || 0)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.65rem", textTransform: "uppercase", letterSpacing: 0.8 }}>
                    {t("dashboard.fleet.requests")}
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
                      fontWeight: 700,
                      fontSize: "1rem",
                      fontVariantNumeric: "tabular-nums",
                      lineHeight: 1.1,
                    }}
                  >
                    {formatCompact(llm.request_count || 0)}
                  </Typography>
                </Box>
              </Box>

              {/* Share bar */}
              <Box
                sx={{
                  height: 4,
                  borderRadius: 999,
                  background: (theme) =>
                    theme.palette.mode === "dark"
                      ? "rgba(255,255,255,0.06)"
                      : "rgba(0,0,0,0.05)",
                  overflow: "hidden",
                }}
              >
                <Box
                  sx={{
                    height: "100%",
                    width: `${Math.max(share, 4)}%`,
                    background: `linear-gradient(90deg, ${prov.color}, ${prov.color}aa)`,
                    transition: "width 0.3s",
                  }}
                />
              </Box>
            </ModelCard>
          );
        })}
      </FleetRow>
    </Box>
  );
}
