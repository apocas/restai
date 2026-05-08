import { useState, useEffect } from "react";
import {
  Box,
  styled,
  Typography,
  Chip,
  Alert,
  Card,
  IconButton,
  Tooltip,
  Tab,
  Tabs,
} from "@mui/material";
import { Psychology, Image, Speaker, DataArray, ContentCopy, Check, Hub } from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import { Trans, useTranslation } from "react-i18next";
import api from "app/utils/api";
import { FONT_MONO, sweep } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Per-endpoint accents — every section card gets a coloured rail + glow
// + chip tint so the page reads as four distinct surfaces, not one
// monotone scroll. Same vocabulary as the project library cards.
const ENDPOINT_ACCENTS = {
  chat:       { color: "#10b981", soft: "rgba(16,185,129,0.12)" }, // emerald
  embeddings: { color: "#6366f1", soft: "rgba(99,102,241,0.12)" }, // indigo
  images:     { color: "#a855f7", soft: "rgba(168,85,247,0.12)" }, // violet
  audio:      { color: "#0891b2", soft: "rgba(8,145,178,0.12)"  }, // cyan
};

// ── Section card — same anatomy as the project library cards
// (accent rail, hover glow), but bigger and laid out for docs.
const SectionCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease",
  marginBottom: 24,
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
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
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

// ── Terminal-style code block: dark slate background, traffic-light
// dots in the title bar, language label, copy button. Matches the
// "alive AI platform" vibe of the page hero.
function CodeTerminal({ language, code }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Box
      sx={{
        borderRadius: 2,
        overflow: "hidden",
        border: "1px solid rgba(15,23,42,0.08)",
        backgroundColor: "#0b1220",
        boxShadow: "0 8px 22px rgba(15,23,42,0.18)",
      }}
    >
      {/* Title bar */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 1,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          backgroundColor: "rgba(255,255,255,0.02)",
        }}
      >
        {/* Traffic-light dots */}
        <Box sx={{ display: "flex", gap: 0.6, mr: 1 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <Box
              key={c}
              sx={{
                width: 11,
                height: 11,
                borderRadius: "50%",
                backgroundColor: c,
                opacity: 0.85,
              }}
            />
          ))}
        </Box>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            color: "rgba(255,255,255,0.55)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontWeight: 600,
            flex: 1,
          }}
        >
          {language}
        </Typography>
        <Tooltip title={copied ? "Copied" : "Copy"}>
          <IconButton
            size="small"
            onClick={handleCopy}
            sx={{
              color: copied ? "#28c840" : "rgba(255,255,255,0.55)",
              "&:hover": {
                color: "#fff",
                backgroundColor: "rgba(255,255,255,0.08)",
              },
            }}
          >
            {copied ? <Check fontSize="small" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>
      <Box
        component="pre"
        sx={{
          margin: 0,
          padding: "16px 20px",
          fontFamily: FONT_MONO,
          fontSize: "0.78rem",
          lineHeight: 1.65,
          color: "#cbd5e1",
          overflowX: "auto",
          tabSize: 4,
          // Subtle horizontal cyan glow at the bottom — a thin
          // "connection" cue that ties this to the page hero.
          background:
            "linear-gradient(180deg, rgba(255,255,255,0) 70%, rgba(56,189,248,0.04))",
        }}
      >
        <code>{code}</code>
      </Box>
    </Box>
  );
}

// ── Per-section block: header strip with icon + title + endpoint
// pill, available-models row, then a code-sample area with language
// tabs.
function EndpointSection({
  accentKey, icon, title, endpoint, description, models,
  modelLabel, emptyWarning, samples,
}) {
  const accent = ENDPOINT_ACCENTS[accentKey];
  const [tab, setTab] = useState(0);

  return (
    <SectionCard elevation={0} accent={accent.color}>
      {/* Header strip */}
      <Box sx={{ p: 3, pt: 2.75, display: "flex", flexDirection: "column", gap: 1.5 }}>
        <Box sx={{ display: "flex", gap: 1.75, alignItems: "center", flexWrap: "wrap" }}>
          <Box
            sx={{
              width: 44,
              height: 44,
              flexShrink: 0,
              borderRadius: 2,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              background: accent.soft,
              color: accent.color,
              "& svg": { fontSize: 22 },
            }}
          >
            {icon}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
              {title}
            </Typography>
            <Box
              sx={{
                display: "inline-flex",
                alignItems: "center",
                gap: 0.75,
                mt: 0.5,
                px: 1,
                py: 0.4,
                borderRadius: 1,
                backgroundColor: "rgba(15,23,42,0.04)",
                border: "1px solid rgba(15,23,42,0.08)",
              }}
            >
              <Box
                component="span"
                sx={{
                  fontFamily: FONT_MONO,
                  fontSize: "0.62rem",
                  fontWeight: 700,
                  letterSpacing: "0.1em",
                  color: accent.color,
                }}
              >
                POST
              </Box>
              <Box
                component="span"
                sx={{
                  fontFamily: FONT_MONO,
                  fontSize: "0.72rem",
                  color: "text.secondary",
                  wordBreak: "break-all",
                }}
              >
                {endpoint}
              </Box>
            </Box>
          </Box>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ ml: { xs: 0, sm: 7.75 } }}>
          {description}
        </Typography>
      </Box>

      {/* Available models */}
      <Box sx={{ px: 3, pb: 2.5 }}>
        {models && models.length > 0 ? (
          <Box>
            <Typography
              variant="overline"
              sx={{
                color: "text.secondary",
                fontWeight: 600,
                letterSpacing: 1.2,
                fontSize: "0.65rem",
                display: "block",
                mb: 1,
              }}
            >
              {modelLabel}
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {models.map((m) => (
                <Chip
                  key={m.key}
                  label={m.label}
                  size="small"
                  sx={{
                    height: 24,
                    fontSize: "0.72rem",
                    fontFamily: FONT_MONO,
                    fontWeight: 500,
                    color: accent.color,
                    backgroundColor: accent.soft,
                    border: `1px solid ${accent.color}33`,
                    "& .MuiChip-label": { px: 1 },
                  }}
                />
              ))}
            </Box>
          </Box>
        ) : (
          emptyWarning && (
            <Alert severity="warning" sx={{ mt: 0 }}>
              {emptyWarning}
            </Alert>
          )
        )}
      </Box>

      {/* Code samples — language tabs */}
      <Box sx={{ borderTop: "1px solid rgba(15,23,42,0.06)", backgroundColor: "rgba(15,23,42,0.015)" }}>
        <Tabs
          value={tab}
          onChange={(e, v) => setTab(v)}
          sx={{
            minHeight: 38,
            px: 2,
            "& .MuiTab-root": {
              minHeight: 38,
              textTransform: "none",
              fontWeight: 500,
              fontSize: "0.78rem",
              fontFamily: FONT_MONO,
              color: "text.secondary",
              minWidth: "auto",
              px: 1.5,
            },
            "& .Mui-selected": {
              color: `${accent.color} !important`,
            },
            "& .MuiTabs-indicator": {
              backgroundColor: accent.color,
              height: 2,
            },
          }}
        >
          {samples.map((s, i) => (
            <Tab key={i} label={s.tab} />
          ))}
        </Tabs>
        <Box sx={{ p: 2, pt: 1.5 }}>
          <CodeTerminal language={samples[tab].language} code={samples[tab].code} />
        </Box>
      </Box>
    </SectionCard>
  );
}

export default function DirectAccess() {
  const { t } = useTranslation();
  const [models, setModels] = useState({ llms: [], embeddings: [], image_generators: [], audio_generators: [] });
  const [loading, setLoading] = useState(true);
  const [baseUrlCopied, setBaseUrlCopied] = useState(false);
  const { user } = useAuth();

  const baseUrl = process.env.REACT_APP_RESTAI_API_URL || window.location.origin;

  useEffect(() => {
    document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - ${t("direct.title")}`;

    const fetchModels = async () => {
      try {
        const data = await api.get("/direct/models", user.token);
        setModels(data);
      } catch (error) {
        // errors auto-toasted
      } finally {
        setLoading(false);
      }
    };
    fetchModels();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const copyBaseUrl = () => {
    navigator.clipboard.writeText(`${baseUrl}/v1`);
    setBaseUrlCopied(true);
    toast.success("Base URL copied");
    setTimeout(() => setBaseUrlCopied(false), 1500);
  };

  const llmModel = models.llms[0]?.name || "your-model";
  const embedModel = models.embeddings[0]?.name || "your-embedding-model";
  const imgModel = models.image_generators[0] || "dalle3";
  const audioModel = models.audio_generators[0] || "whisper";

  return (
    <Container>
      <PageHero
        icon={<Hub sx={{ color: "#fff" }} />}
        eyebrow="OPENAI-COMPATIBLE API"
        title={t("direct.title") || "Direct Access"}
        subtitle={t("direct.subtitle")}
        showStatusDot
        statusLabel="Live"
        stats={[
          { glyph: "◆", color: "#7dd3fc", label: `${models.llms.length} LLMs` },
          { glyph: "⊞", color: "#a78bfa", label: `${models.embeddings.length} embeddings` },
          { glyph: "▲", color: "#f0abfc", label: `${models.image_generators.length} image gen` },
          { glyph: "↯", color: "#67e8f9", label: `${models.audio_generators.length} audio` },
        ]}
      />

      {/* Base URL banner — terminal-style strip with copy */}
      <Box
        sx={{
          mb: 3,
          borderRadius: 2.5,
          backgroundColor: "#0b1220",
          color: "#cbd5e1",
          p: 1.5,
          pl: 2,
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexWrap: "wrap",
          border: "1px solid rgba(15,23,42,0.12)",
          boxShadow: "0 8px 22px rgba(15,23,42,0.10)",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0 }}>
          <Box
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.65rem",
              letterSpacing: "0.18em",
              fontWeight: 700,
              color: "#7dd3fc",
            }}
          >
            BASE URL
          </Box>
          <Box
            component="code"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.85rem",
              color: "#fff",
              wordBreak: "break-all",
            }}
          >
            {baseUrl}/v1
          </Box>
        </Box>
        <Tooltip title={baseUrlCopied ? "Copied" : "Copy base URL"}>
          <IconButton
            size="small"
            onClick={copyBaseUrl}
            sx={{
              color: baseUrlCopied ? "#28c840" : "rgba(255,255,255,0.7)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 1.5,
              "&:hover": { color: "#fff", backgroundColor: "rgba(255,255,255,0.08)" },
            }}
          >
            {baseUrlCopied ? <Check fontSize="small" /> : <ContentCopy fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>

      {/* Tip banner */}
      <Alert
        severity="info"
        variant="outlined"
        icon={false}
        sx={{
          mb: 3,
          borderColor: "rgba(25,118,210,0.25)",
          backgroundColor: "rgba(25,118,210,0.04)",
          "& .MuiAlert-message": { width: "100%" },
        }}
      >
        <Trans
          i18nKey="direct.baseUrlLine"
          values={{ url: baseUrl }}
          components={{ strong: <strong /> }}
        />
      </Alert>

      {/* ── LLMs / Chat ───────────────────────────────────────── */}
      <EndpointSection
        accentKey="chat"
        icon={<Psychology />}
        title={t("direct.chat")}
        endpoint={`${baseUrl}/v1/chat/completions`}
        description={t("direct.chatDesc")}
        modelLabel={t("direct.availableModels")}
        emptyWarning={!loading && t("direct.noLlms")}
        models={models.llms.map((l) => ({ key: l.name, label: l.name }))}
        samples={[
          {
            tab: "Python",
            language: "Python · OpenAI SDK",
            code: `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

response = client.chat.completions.create(
    model="${llmModel}",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    stream=False,
)
print(response.choices[0].message.content)`,
          },
          {
            tab: "Streaming",
            language: "Python · streaming",
            code: `stream = client.chat.completions.create(
    model="${llmModel}",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")`,
          },
          {
            tab: "cURL",
            language: "Shell · cURL",
            code: `curl ${baseUrl}/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${llmModel}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`,
          },
        ]}
      />

      {/* ── Embeddings ────────────────────────────────────────── */}
      <EndpointSection
        accentKey="embeddings"
        icon={<DataArray />}
        title={t("direct.embeddings")}
        endpoint={`${baseUrl}/v1/embeddings`}
        description={t("direct.embeddingsDesc")}
        modelLabel={t("direct.availableModels")}
        emptyWarning={!loading && t("direct.noEmbeddings")}
        models={models.embeddings.map((e) => ({
          key: e.name,
          label: t("direct.embeddingChip", { name: e.name, dim: e.dimension }),
        }))}
        samples={[
          {
            tab: "Python",
            language: "Python · OpenAI SDK",
            code: `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

response = client.embeddings.create(
    model="${embedModel}",
    input="Hello, world!",
)
print(response.data[0].embedding[:5])  # first 5 dimensions`,
          },
          {
            tab: "Batch",
            language: "Python · batch",
            code: `response = client.embeddings.create(
    model="${embedModel}",
    input=["First text", "Second text", "Third text"],
)
for item in response.data:
    print(f"Index {item.index}: {len(item.embedding)} dimensions")`,
          },
          {
            tab: "cURL",
            language: "Shell · cURL",
            code: `curl ${baseUrl}/v1/embeddings \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${embedModel}",
    "input": "Hello, world!"
  }'`,
          },
        ]}
      />

      {/* ── Image generation ──────────────────────────────────── */}
      <EndpointSection
        accentKey="images"
        icon={<Image />}
        title={t("direct.images")}
        endpoint={`${baseUrl}/v1/images/generations`}
        description={t("direct.imagesDesc")}
        modelLabel={t("direct.availableGenerators")}
        emptyWarning={!loading && t("direct.noImage")}
        models={models.image_generators.map((g) => ({ key: g, label: g }))}
        samples={[
          {
            tab: "Python",
            language: "Python · OpenAI SDK",
            code: `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

response = client.images.generate(
    model="${imgModel}",
    prompt="A sunset over mountains",
    response_format="b64_json",
)
print(response.data[0].b64_json[:50] + "...")`,
          },
          {
            tab: "cURL",
            language: "Shell · cURL",
            code: `curl ${baseUrl}/v1/images/generations \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${imgModel}",
    "prompt": "A sunset over mountains",
    "response_format": "b64_json"
  }'`,
          },
        ]}
      />

      {/* ── Audio transcription ───────────────────────────────── */}
      <EndpointSection
        accentKey="audio"
        icon={<Speaker />}
        title={t("direct.audio")}
        endpoint={`${baseUrl}/v1/audio/transcriptions`}
        description={t("direct.audioDesc")}
        modelLabel={t("direct.availableModels")}
        emptyWarning={!loading && t("direct.noAudio")}
        models={models.audio_generators.map((g) => ({ key: g, label: g }))}
        samples={[
          {
            tab: "Python",
            language: "Python · OpenAI SDK",
            code: `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

with open("audio.mp3", "rb") as f:
    transcript = client.audio.transcriptions.create(
        model="${audioModel}",
        file=f,
        language="en",
    )
print(transcript.text)`,
          },
          {
            tab: "cURL",
            language: "Shell · cURL",
            code: `curl ${baseUrl}/v1/audio/transcriptions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -F model="${audioModel}" \\
  -F file=@audio.mp3 \\
  -F language=en`,
          },
        ]}
      />
    </Container>
  );
}
