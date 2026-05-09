import { useState, useEffect } from "react";
import { Box, styled } from "@mui/material";
import { Psychology } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import LLMEdit from "./components/LLMEdit";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Per-provider palette — same map as the LLM list/info pages so the
// hero glyph hue tracks whatever provider this LLM uses.
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

export default function LLMEditView() {
  const { id } = useParams();
  const [llm, setLLM] = useState({});
  const auth = useAuth();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Edit LLM - " + id;
    api.get("/llms/" + id, auth.user.token)
      .then(setLLM)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const meta = providerMeta(llm.class_name);
  const ctx = formatContext(llm.context_window);
  const inC = formatCost(llm.input_cost);
  const outC = formatCost(llm.output_cost);

  return (
    <Container>
      <PageHero
        icon={<Psychology sx={{ color: "#fff" }} />}
        eyebrow={`LLM/${String(llm.id || 0).padStart(4, "0")} · EDIT`}
        title={llm.name || id}
        subtitle="Tune provider, options, context window, and pricing for this language model."
        stats={[
          { glyph: "◆", color: "#7dd3fc", label: meta.short },
          { glyph: "▸", color: "#bae6fd", label: llm.privacy || "—" },
          ...(ctx ? [{ glyph: "⌬", color: "#a5b4fc", label: `${ctx} ctx` }] : []),
          ...(inC || outC
            ? [{ glyph: "$", color: "#a7f3d0", label: `$${inC || "0"}/$${outC || "0"}` }]
            : []),
        ]}
        compact
      />

      <Box sx={{ mt: 2.5 }}>
        {llm.name && <LLMEdit llm={llm} />}
      </Box>
    </Container>
  );
}
