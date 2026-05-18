import { useState, useEffect } from "react";
import {
  Box, Card, Chip, IconButton, Tab, Tabs, Tooltip, Typography, styled,
} from "@mui/material";
import { ContentCopy, Check, Code, ChatBubbleOutline, QuestionAnswer } from "@mui/icons-material";
import PageHero from "app/components/page/PageHero";
import ProjectTrailBar from "./components/ProjectTrailBar";
import { useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO, cleanCardSx } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Sleek dark code well — kept the navy terminal look that already
// pairs well with the playground's terminal lane, just retuned the
// border radius/inset so it nests cleanly inside the white card.
const CodeBlock = styled(Box)(() => ({
  background: "#0f172a",
  color: "#e2e8f0",
  padding: "18px 22px 18px 22px",
  borderRadius: 10,
  fontFamily: FONT_MONO,
  fontSize: "0.8rem",
  lineHeight: 1.65,
  overflowX: "auto",
  whiteSpace: "pre",
  position: "relative",
  tabSize: 4,
  border: "1px solid rgba(15,23,42,0.08)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.04)",
}));

const LangTab = styled(Tab)(() => ({
  textTransform: "none",
  fontFamily: FONT_MONO,
  fontWeight: 600,
  fontSize: "0.78rem",
  letterSpacing: "0.04em",
  minHeight: 36,
  minWidth: 70,
  padding: "4px 14px",
  color: "rgba(15,23,42,0.55)",
  "&.Mui-selected": { color: "#0f172a" },
}));

const LANGUAGES = [
  { id: "curl", label: "cURL" },
  { id: "python", label: "Python" },
  { id: "javascript", label: "JavaScript" },
  { id: "php", label: "PHP" },
  { id: "go", label: "Go" },
  { id: "ruby", label: "Ruby" },
];

function replaceVars(code, project) {
  const url = window.location.protocol + "//" + window.location.host;
  const question = project.default_prompt || "What can you help me with?";
  return code
    .replaceAll("<URL>", url)
    .replaceAll("<PROJECT>", project.id || "1")
    .replaceAll("<QUESTION>", question);
}

// ── Code templates ──────────────────────────────────────────────────────

const snippets = {
  curl: {
    question: `curl -X POST '<URL>/projects/<PROJECT>/question' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{
    "question": "<QUESTION>"
  }'`,
    chat: `# First message — omit "id" to start a new conversation
curl -X POST '<URL>/projects/<PROJECT>/chat' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{
    "question": "<QUESTION>"
  }'

# Follow-up — include the "id" from the first response
curl -X POST '<URL>/projects/<PROJECT>/chat' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{
    "question": "Tell me more",
    "id": "CHAT_ID_FROM_FIRST_RESPONSE"
  }'`,
  },
  python: {
    question: `import requests

API_KEY = "YOUR_API_KEY"

response = requests.post(
    "<URL>/projects/<PROJECT>/question",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    },
    json={"question": "<QUESTION>"},
)

data = response.json()
print(data["answer"])`,
    chat: `import requests

API_KEY = "YOUR_API_KEY"

def chat(question, chat_id=None):
    body = {"question": question}
    if chat_id:
        body["id"] = chat_id

    response = requests.post(
        "<URL>/projects/<PROJECT>/chat",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        json=body,
    )
    return response.json()

# Start a new conversation
result = chat("<QUESTION>")
print(result["answer"])

# Continue the conversation using the returned id
result = chat("Tell me more", chat_id=result["id"])
print(result["answer"])`,
  },
  javascript: {
    question: `const API_KEY = "YOUR_API_KEY";

const response = await fetch("<URL>/projects/<PROJECT>/question", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": \`Bearer \${API_KEY}\`,
  },
  body: JSON.stringify({ question: "<QUESTION>" }),
});

const data = await response.json();
console.log(data.answer);`,
    chat: `const API_KEY = "YOUR_API_KEY";

async function chat(question, chatId) {
  const body = { question };
  if (chatId) body.id = chatId;

  const response = await fetch("<URL>/projects/<PROJECT>/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": \`Bearer \${API_KEY}\`,
    },
    body: JSON.stringify(body),
  });

  return response.json();
}

// Start a new conversation
const result = await chat("<QUESTION>");
console.log(result.answer);

// Continue the conversation using the returned id
const followUp = await chat("Tell me more", result.id);
console.log(followUp.answer);`,
  },
  php: {
    question: `<?php

$apiKey = "YOUR_API_KEY";

$ch = curl_init("<URL>/projects/<PROJECT>/question");
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode([
        "question" => "<QUESTION>",
    ]),
    CURLOPT_HTTPHEADER => [
        "Content-Type: application/json",
        "Authorization: Bearer " . $apiKey,
    ],
]);

$response = curl_exec($ch);
curl_close($ch);

$data = json_decode($response, true);
echo $data["answer"];`,
    chat: `<?php

$apiKey = "YOUR_API_KEY";

function chat($question, $chatId = null) {
    global $apiKey;

    $body = ["question" => $question];
    if ($chatId) {
        $body["id"] = $chatId;
    }

    $ch = curl_init("<URL>/projects/<PROJECT>/chat");
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => json_encode($body),
        CURLOPT_HTTPHEADER => [
            "Content-Type: application/json",
            "Authorization: Bearer " . $apiKey,
        ],
    ]);

    $response = curl_exec($ch);
    curl_close($ch);

    return json_decode($response, true);
}

// Start a new conversation
$result = chat("<QUESTION>");
echo $result["answer"];

// Continue the conversation using the returned id
$result = chat("Tell me more", $result["id"]);
echo $result["answer"];`,
  },
  go: {
    question: `package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

func main() {
	apiKey := "YOUR_API_KEY"

	body, _ := json.Marshal(map[string]string{
		"question": "<QUESTION>",
	})

	req, _ := http.NewRequest("POST",
		"<URL>/projects/<PROJECT>/question",
		bytes.NewBuffer(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	var data map[string]interface{}
	json.Unmarshal(respBody, &data)
	fmt.Println(data["answer"])
}`,
    chat: `package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

func chat(apiKey, question string, chatID *string) map[string]interface{} {
	body := map[string]string{"question": question}
	if chatID != nil {
		body["id"] = *chatID
	}

	payload, _ := json.Marshal(body)
	req, _ := http.NewRequest("POST",
		"<URL>/projects/<PROJECT>/chat",
		bytes.NewBuffer(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	resp, _ := http.DefaultClient.Do(req)
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)

	var data map[string]interface{}
	json.Unmarshal(respBody, &data)
	return data
}

func main() {
	apiKey := "YOUR_API_KEY"

	// Start a new conversation
	result := chat(apiKey, "<QUESTION>", nil)
	fmt.Println(result["answer"])

	// Continue using the returned id
	id := result["id"].(string)
	result = chat(apiKey, "Tell me more", &id)
	fmt.Println(result["answer"])
}`,
  },
  ruby: {
    question: `require "net/http"
require "json"
require "uri"

api_key = "YOUR_API_KEY"

uri = URI("<URL>/projects/<PROJECT>/question")
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = uri.scheme == "https"

request = Net::HTTP::Post.new(uri)
request["Content-Type"] = "application/json"
request["Authorization"] = "Bearer #{api_key}"
request.body = { question: "<QUESTION>" }.to_json

response = http.request(request)
data = JSON.parse(response.body)
puts data["answer"]`,
    chat: `require "net/http"
require "json"
require "uri"

api_key = "YOUR_API_KEY"

def chat(api_key, question, chat_id = nil)
  uri = URI("<URL>/projects/<PROJECT>/chat")
  http = Net::HTTP.new(uri.host, uri.port)
  http.use_ssl = uri.scheme == "https"

  body = { question: question }
  body[:id] = chat_id if chat_id

  request = Net::HTTP::Post.new(uri)
  request["Content-Type"] = "application/json"
  request["Authorization"] = "Bearer #{api_key}"
  request.body = body.to_json

  response = http.request(request)
  JSON.parse(response.body)
end

# Start a new conversation
result = chat(api_key, "<QUESTION>")
puts result["answer"]

# Continue using the returned id
result = chat(api_key, "Tell me more", result["id"])
puts result["answer"]`,
  },
};

// ── Copy button ─────────────────────────────────────────────────────────

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };
  return (
    <Tooltip title={copied ? "Copied!" : "Copy code"} arrow>
      <IconButton
        size="small"
        onClick={handleCopy}
        sx={{
          position: "absolute", top: 8, right: 8,
          color: "#94a3b8",
          background: "rgba(255,255,255,0.04)",
          backdropFilter: "blur(2px)",
          "&:hover": { color: "#e2e8f0", background: "rgba(255,255,255,0.1)" },
          transition: "color 0.15s ease, background 0.15s ease",
        }}
      >
        {copied ? <Check fontSize="small" /> : <ContentCopy fontSize="small" />}
      </IconButton>
    </Tooltip>
  );
}

// ── Endpoint section — header strip + code block, sits inside the
// outer documentation card. Reuses the section vocabulary other
// sub-pages use (mono eyebrow, then content).
function EndpointSection({ title, description, endpoint, method, code, icon }) {
  return (
    <Box sx={{ pt: 2.5, pb: 0.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
        {icon}
        <Typography sx={{ fontWeight: 700, fontSize: "1rem", color: "#0f172a" }}>
          {title}
        </Typography>
        <Chip
          label={method}
          size="small"
          sx={{
            height: 20, fontSize: "0.66rem", fontWeight: 700,
            fontFamily: FONT_MONO, letterSpacing: "0.06em",
            background: "rgba(8,145,178,0.1)", color: "#0e7490",
            borderRadius: 0.75,
          }}
        />
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO, fontSize: "0.74rem",
            color: "#475569",
            background: "rgba(15,23,42,0.04)",
            border: "1px solid rgba(15,23,42,0.08)",
            px: 1, py: 0.25, borderRadius: 0.75,
          }}
        >
          {endpoint}
        </Box>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5, maxWidth: 720 }}>
        {description}
      </Typography>
      <Box sx={{ position: "relative" }}>
        <CopyButton text={code} />
        <CodeBlock>{code}</CodeBlock>
      </Box>
    </Box>
  );
}

// ── Main ────────────────────────────────────────────────────────────────

export default function ProjectAPI() {
  const { id } = useParams();
  const [project, setProject] = useState({});
  const [lang, setLang] = useState("curl");
  const auth = useAuth();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - API - " + id;
    api.get("/projects/" + id, auth.user.token)
      .then((d) => setProject(d))
      .catch(() => {});
  }, [id, auth.user.token]);

  const projectName = project.name || "my-project";
  const langSnippets = snippets[lang] || snippets.curl;
  const questionCode = replaceVars(langSnippets.question, project);
  const chatCode = replaceVars(langSnippets.chat, project);

  return (
    <Container>
      <PageHero
        icon={<Code sx={{ color: "#fff" }} />}
        eyebrow={`PROJECT/${String(id).padStart(4, "0")}`}
        title="API"
        subtitle={`Programmatic access to ${projectName}.`}
        stats={[
          { glyph: "◆", color: "#93c5fd", label: project.name || "—" },
          { glyph: "⚡", color: "#7dd3fc", label: project.type || "—" },
        ]}
        compact
      />

      <ProjectTrailBar project={project} label="API" />

      {/* Single contained documentation card — matches the cleanCard
          vocabulary used by Evals / Guards / Logs. Inside: a
          sticky-style toolbar with language tabs, then per-endpoint
          sections separated by a hairline divider. */}
      <Card variant="outlined" sx={{
        ...cleanCardSx,
        p: 0,
        // Override the hover lift — this is the entire page surface,
        // it shouldn't jiggle on cursor entry.
        "&:hover": { transform: "none", borderColor: "divider", boxShadow: "none" },
      }}>
        {/* Toolbar — monospace eyebrow + language tabs. Matches the
            section-shell pattern used elsewhere in project edits. */}
        <Box sx={{
          display: "flex",
          flexDirection: { xs: "column", sm: "row" },
          alignItems: { xs: "flex-start", sm: "center" },
          justifyContent: "space-between",
          gap: 1.5,
          px: 2.5, py: 1.5,
          borderBottom: "1px solid",
          borderColor: "divider",
          background: "linear-gradient(180deg, rgba(15,23,42,0.02), transparent)",
        }}>
          <Box>
            <Typography sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.62rem",
              letterSpacing: "0.2em",
              fontWeight: 700,
              color: "rgba(15,23,42,0.5)",
              textTransform: "uppercase",
              mb: 0.25,
            }}>
              REFERENCE
            </Typography>
            <Typography sx={{ fontSize: "0.92rem", color: "text.primary", fontWeight: 600 }}>
              Interact with{" "}
              <Box component="span" sx={{
                fontFamily: FONT_MONO,
                fontWeight: 700,
                color: "#0e7490",
                px: 0.5, borderRadius: 0.5,
                background: "rgba(8,145,178,0.08)",
              }}>
                {projectName}
              </Box>
              {" "}using your API key.
            </Typography>
          </Box>
          <Tabs
            value={lang}
            onChange={(_, v) => setLang(v)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              minHeight: 36,
              maxWidth: "100%",
              "& .MuiTabs-indicator": {
                height: 2.5,
                borderRadius: 1.5,
                backgroundColor: "#0e7490",
              },
            }}
          >
            {LANGUAGES.map((l) => (
              <LangTab key={l.id} value={l.id} label={l.label} />
            ))}
          </Tabs>
        </Box>

        <Box sx={{ px: 2.5, pb: 2.5 }}>
          <EndpointSection
            title="Question"
            description="Send a one-shot question. Each request is independent — the server keeps no conversation memory between calls."
            endpoint={`POST /projects/${project.id || "—"}/question`}
            method="POST"
            code={questionCode}
            icon={<QuestionAnswer sx={{ fontSize: 18, color: "#0e7490" }} />}
          />

          {/* Hairline rule between endpoint sections. */}
          <Box sx={{ height: 1, background: "rgba(15,23,42,0.06)", my: 1 }} />

          <EndpointSection
            title="Chat"
            description="Start or continue a conversation. Omit the id on the first request; include the returned id for follow-ups so the server can resume the session and the same per-chat tool sandbox."
            endpoint={`POST /projects/${project.id || "—"}/chat`}
            method="POST"
            code={chatCode}
            icon={<ChatBubbleOutline sx={{ fontSize: 18, color: "#0e7490" }} />}
          />
        </Box>
      </Card>
    </Container>
  );
}
