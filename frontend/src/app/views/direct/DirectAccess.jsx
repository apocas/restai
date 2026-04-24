import { useState, useEffect } from "react";
import {
  Box,
  styled,
  Card,
  Typography,
  Chip,
  Divider,
  Alert,
} from "@mui/material";
import { Psychology, Image, Speaker, DataArray } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import { Breadcrumb } from "app/components";
import { Trans, useTranslation } from "react-i18next";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" },
  "& .breadcrumb": {
    marginBottom: "30px",
    [theme.breakpoints.down("sm")]: { marginBottom: "16px" },
  },
}));

const StyledCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(3),
  marginBottom: theme.spacing(3),
}));

const CodeBlock = styled("pre")(({ theme }) => ({
  backgroundColor: theme.palette.grey[100],
  padding: theme.spacing(2),
  borderRadius: theme.shape.borderRadius,
  overflow: "auto",
  fontSize: "0.85rem",
  lineHeight: 1.6,
  "& code": {
    fontFamily: '"Fira Code", "Consolas", monospace',
  },
}));

export default function DirectAccess() {
  const { t } = useTranslation();
  const [models, setModels] = useState({ llms: [], embeddings: [], image_generators: [], audio_generators: [] });
  const [loading, setLoading] = useState(true);
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
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("direct.breadcrumb"), path: "/direct" }]} />
      </Box>

      <StyledCard>
        <Typography variant="h4" gutterBottom>
          {t("direct.title")}
        </Typography>
        <Typography variant="body1" color="textSecondary" paragraph>
          {t("direct.subtitle")}
        </Typography>

        <Alert severity="info" sx={{ mb: 0 }}>
          <Trans i18nKey="direct.baseUrlLine" values={{ url: baseUrl }} components={{ strong: <strong /> }} />
        </Alert>
      </StyledCard>

      {/* LLMs Section */}
      <StyledCard>
        <Box display="flex" alignItems="center" gap={1} mb={2}>
          <Psychology color="primary" />
          <Typography variant="h5">{t("direct.chat")}</Typography>
        </Box>
        <Typography variant="body2" color="textSecondary" paragraph>
          <strong>POST</strong> {baseUrl}/v1/chat/completions
        </Typography>
        <Typography variant="body2" paragraph>
          {t("direct.chatDesc")}
        </Typography>

        {models.llms.length > 0 ? (
          <Box mb={2}>
            <Typography variant="subtitle2" gutterBottom>{t("direct.availableModels")}</Typography>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {models.llms.map((llm) => (
                <Chip key={llm.name} label={llm.name} size="small" variant="outlined" />
              ))}
            </Box>
          </Box>
        ) : (
          !loading && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t("direct.noLlms")}
            </Alert>
          )
        )}

        <Divider sx={{ my: 2 }} />
        <Typography variant="subtitle2" gutterBottom>{t("direct.pythonSdk")}</Typography>
        <CodeBlock>
          <code>{`from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

response = client.chat.completions.create(
    model="${models.llms[0]?.name || 'your-model'}",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    stream=False,
)
print(response.choices[0].message.content)`}</code>
        </CodeBlock>

        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>{t("direct.streamingExample")}</Typography>
        <CodeBlock>
          <code>{`stream = client.chat.completions.create(
    model="${models.llms[0]?.name || 'your-model'}",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")`}</code>
        </CodeBlock>

        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>{t("direct.curl")}</Typography>
        <CodeBlock>
          <code>{`curl ${baseUrl}/v1/chat/completions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${models.llms[0]?.name || 'your-model'}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`}</code>
        </CodeBlock>
      </StyledCard>

      {/* Embeddings Section */}
      <StyledCard>
        <Box display="flex" alignItems="center" gap={1} mb={2}>
          <DataArray color="primary" />
          <Typography variant="h5">{t("direct.embeddings")}</Typography>
        </Box>
        <Typography variant="body2" color="textSecondary" paragraph>
          <strong>POST</strong> {baseUrl}/v1/embeddings
        </Typography>
        <Typography variant="body2" paragraph>
          {t("direct.embeddingsDesc")}
        </Typography>

        {models.embeddings.length > 0 ? (
          <Box mb={2}>
            <Typography variant="subtitle2" gutterBottom>{t("direct.availableModels")}</Typography>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {models.embeddings.map((emb) => (
                <Chip key={emb.name} label={t("direct.embeddingChip", { name: emb.name, dim: emb.dimension })} size="small" variant="outlined" />
              ))}
            </Box>
          </Box>
        ) : (
          !loading && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t("direct.noEmbeddings")}
            </Alert>
          )
        )}

        <Divider sx={{ my: 2 }} />
        <Typography variant="subtitle2" gutterBottom>{t("direct.pythonSdk")}</Typography>
        <CodeBlock>
          <code>{`from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

response = client.embeddings.create(
    model="${models.embeddings[0]?.name || 'your-embedding-model'}",
    input="Hello, world!",
)
print(response.data[0].embedding[:5])  # first 5 dimensions`}</code>
        </CodeBlock>

        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>{t("direct.batchExample")}</Typography>
        <CodeBlock>
          <code>{`response = client.embeddings.create(
    model="${models.embeddings[0]?.name || 'your-embedding-model'}",
    input=["First text", "Second text", "Third text"],
)
for item in response.data:
    print(f"Index {item.index}: {len(item.embedding)} dimensions")`}</code>
        </CodeBlock>

        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>{t("direct.curl")}</Typography>
        <CodeBlock>
          <code>{`curl ${baseUrl}/v1/embeddings \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${models.embeddings[0]?.name || 'your-embedding-model'}",
    "input": "Hello, world!"
  }'`}</code>
        </CodeBlock>
      </StyledCard>

      {/* Image Generators Section */}
      <StyledCard>
        <Box display="flex" alignItems="center" gap={1} mb={2}>
          <Image color="primary" />
          <Typography variant="h5">{t("direct.images")}</Typography>
        </Box>
        <Typography variant="body2" color="textSecondary" paragraph>
          <strong>POST</strong> {baseUrl}/v1/images/generations
        </Typography>
        <Typography variant="body2" paragraph>
          {t("direct.imagesDesc")}
        </Typography>

        {models.image_generators.length > 0 ? (
          <Box mb={2}>
            <Typography variant="subtitle2" gutterBottom>{t("direct.availableGenerators")}</Typography>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {models.image_generators.map((gen) => (
                <Chip key={gen} label={gen} size="small" variant="outlined" />
              ))}
            </Box>
          </Box>
        ) : (
          !loading && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t("direct.noImage")}
            </Alert>
          )
        )}

        <Divider sx={{ my: 2 }} />
        <Typography variant="subtitle2" gutterBottom>{t("direct.pythonSdk")}</Typography>
        <CodeBlock>
          <code>{`from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

response = client.images.generate(
    model="${models.image_generators[0] || 'dalle3'}",
    prompt="A sunset over mountains",
    response_format="b64_json",
)
print(response.data[0].b64_json[:50] + "...")`}</code>
        </CodeBlock>

        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>{t("direct.curl")}</Typography>
        <CodeBlock>
          <code>{`curl ${baseUrl}/v1/images/generations \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${models.image_generators[0] || 'dalle3'}",
    "prompt": "A sunset over mountains",
    "response_format": "b64_json"
  }'`}</code>
        </CodeBlock>
      </StyledCard>

      {/* Audio Transcription Section */}
      <StyledCard>
        <Box display="flex" alignItems="center" gap={1} mb={2}>
          <Speaker color="primary" />
          <Typography variant="h5">{t("direct.audio")}</Typography>
        </Box>
        <Typography variant="body2" color="textSecondary" paragraph>
          <strong>POST</strong> {baseUrl}/v1/audio/transcriptions
        </Typography>
        <Typography variant="body2" paragraph>
          {t("direct.audioDesc")}
        </Typography>

        {models.audio_generators.length > 0 ? (
          <Box mb={2}>
            <Typography variant="subtitle2" gutterBottom>{t("direct.availableModels")}</Typography>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {models.audio_generators.map((gen) => (
                <Chip key={gen} label={gen} size="small" variant="outlined" />
              ))}
            </Box>
          </Box>
        ) : (
          !loading && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t("direct.noAudio")}
            </Alert>
          )
        )}

        <Divider sx={{ my: 2 }} />
        <Typography variant="subtitle2" gutterBottom>{t("direct.pythonSdk")}</Typography>
        <CodeBlock>
          <code>{`from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}/v1",
    api_key="YOUR_API_KEY",
)

with open("audio.mp3", "rb") as f:
    transcript = client.audio.transcriptions.create(
        model="${models.audio_generators[0] || 'whisper'}",
        file=f,
        language="en",
    )
print(transcript.text)`}</code>
        </CodeBlock>

        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>{t("direct.curl")}</Typography>
        <CodeBlock>
          <code>{`curl ${baseUrl}/v1/audio/transcriptions \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -F model="${models.audio_generators[0] || 'whisper'}" \\
  -F file=@audio.mp3 \\
  -F language=en`}</code>
        </CodeBlock>
      </StyledCard>
    </Container>
  );
}
