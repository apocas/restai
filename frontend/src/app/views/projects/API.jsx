import { useState, useEffect } from "react";
import {
  Box, Card, Chip, IconButton, Tab, Tabs, Tooltip, Typography, styled,
} from "@mui/material";
import { ContentCopy, Check } from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

const CodeBlock = styled(Box)(() => ({
  background: "#1e1e2e",
  color: "#cdd6f4",
  padding: "20px 24px",
  borderRadius: "0 0 10px 10px",
  fontFamily: "'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace",
  fontSize: "0.82rem",
  lineHeight: 1.7,
  overflowX: "auto",
  whiteSpace: "pre",
  position: "relative",
  tabSize: 4,
}));

const LangTab = styled(Tab)(() => ({
  textTransform: "none",
  fontWeight: 500,
  fontSize: "0.85rem",
  minHeight: 40,
  minWidth: 80,
  padding: "6px 16px",
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
    .replaceAll("<PROJECT>", project.name || "my-project")
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
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <Tooltip title={copied ? "Copied!" : "Copy code"}>
      <IconButton
        size="small"
        onClick={handleCopy}
        sx={{
          position: "absolute", top: 10, right: 10,
          color: "#6c7086",
          "&:hover": { color: "#cdd6f4", background: "rgba(255,255,255,0.08)" },
        }}
      >
        {copied ? <Check fontSize="small" /> : <ContentCopy fontSize="small" />}
      </IconButton>
    </Tooltip>
  );
}

// ── Example card ────────────────────────────────────────────────────────

function ExampleCard({ title, description, endpoint, method, code }) {
  return (
    <Card
      variant="outlined"
      sx={{
        borderRadius: "10px",
        overflow: "hidden",
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Box sx={{ p: 2.5, pb: 1.5 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
          <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
          <Chip label={method} size="small" variant="outlined"
            sx={{ fontSize: "0.7rem", height: 22, fontFamily: "monospace", fontWeight: 600 }} />
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {description}
        </Typography>
        <Typography
          variant="caption"
          sx={{
            fontFamily: "monospace",
            color: "primary.main",
            background: (t) => t.palette.mode === "dark" ? "rgba(99,102,241,0.1)" : "rgba(99,102,241,0.08)",
            px: 1, py: 0.3, borderRadius: 1,
          }}
        >
          {endpoint}
        </Typography>
      </Box>
      <CodeBlock>
        <CopyButton text={code} />
        {code}
      </CodeBlock>
    </Card>
  );
}

// ── Main component ──────────────────────────────────────────────────────

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
  }, [id]);

  const projectName = project.name || "my-project";
  const langSnippets = snippets[lang] || snippets.curl;
  const questionCode = replaceVars(langSnippets.question, project);
  const chatCode = replaceVars(langSnippets.chat, project);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: "Projects", path: "/projects" },
            { name: projectName, path: "/project/" + id },
            { name: "API" },
          ]}
        />
      </Box>

      <Box>
        <Typography variant="h5" fontWeight={700} sx={{ mb: 0.5 }}>
          API Reference
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Use your API key to interact with the <strong>{projectName}</strong> project programmatically.
        </Typography>

        {/* Language selector */}
        <Tabs
          value={lang}
          onChange={(_, v) => setLang(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            mb: 3,
            minHeight: 40,
            "& .MuiTabs-indicator": { height: 2.5, borderRadius: 2 },
          }}
        >
          {LANGUAGES.map((l) => (
            <LangTab key={l.id} value={l.id} label={l.label} />
          ))}
        </Tabs>

        {/* Examples */}
        <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <ExampleCard
            title="Question"
            description="Send a one-shot question. Each request is independent with no conversation memory."
            endpoint={`POST /projects/${projectName}/question`}
            method="POST"
            code={questionCode}
          />
          <ExampleCard
            title="Chat"
            description="Start or continue a conversation. Omit the id on the first request; include the returned id for follow-ups."
            endpoint={`POST /projects/${projectName}/chat`}
            method="POST"
            code={chatCode}
          />
        </Box>
      </Box>
    </Container>
  );
}
