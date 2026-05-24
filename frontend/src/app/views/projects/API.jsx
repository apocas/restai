import { useState, useEffect } from "react";
import {
  Box, Card, Chip, IconButton, Tab, Tabs, Tooltip, Typography, styled,
} from "@mui/material";
import { ContentCopy, Check, Code, ChatBubbleOutline, Stream } from "@mui/icons-material";
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

const snippets = {
  curl: {
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
    stream: `# Stream responses via Server-Sent Events
curl -N -X POST '<URL>/projects/<PROJECT>/chat' \\
  -H 'Content-Type: application/json' \\
  -H 'Accept: text/event-stream' \\
  -H 'Authorization: Bearer YOUR_API_KEY' \\
  -d '{
    "question": "<QUESTION>",
    "stream": true
  }'

# Each SSE line is: data: {"text": "partial token..."}
# Final line:       data: {"answer": "full answer", "sources": [...], ...}
# Stream ends with: event: close`,
  },
  python: {
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
    stream: `import requests
import json

API_KEY = "YOUR_API_KEY"

response = requests.post(
    "<URL>/projects/<PROJECT>/chat",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    },
    json={"question": "<QUESTION>", "stream": True},
    stream=True,
)

for line in response.iter_lines():
    line = line.decode("utf-8")
    if line.startswith("data: "):
        data = json.loads(line[6:])
        if "text" in data and "answer" not in data:
            print(data["text"], end="", flush=True)
        elif "answer" in data:
            print()  # newline after streaming
            print("Sources:", data.get("sources", []))
    elif line.startswith("event: close"):
        break`,
  },
  javascript: {
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
    stream: `const API_KEY = "YOUR_API_KEY";

const response = await fetch("<URL>/projects/<PROJECT>/chat", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": \`Bearer \${API_KEY}\`,
  },
  body: JSON.stringify({ question: "<QUESTION>", stream: true }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });

  const lines = buffer.split("\\n");
  buffer = lines.pop(); // keep incomplete line

  for (const line of lines) {
    if (line.startsWith("data: ")) {
      const data = JSON.parse(line.slice(6));
      if (data.text && !data.answer) {
        process.stdout.write(data.text); // or append to DOM
      } else if (data.answer) {
        console.log("\\nFinal:", data.answer);
      }
    }
  }
}`,
  },
  php: {
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
    stream: `<?php

$apiKey = "YOUR_API_KEY";

$ch = curl_init("<URL>/projects/<PROJECT>/chat");
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode([
        "question" => "<QUESTION>",
        "stream" => true,
    ]),
    CURLOPT_HTTPHEADER => [
        "Content-Type: application/json",
        "Accept: text/event-stream",
        "Authorization: Bearer " . $apiKey,
    ],
    CURLOPT_WRITEFUNCTION => function ($ch, $data) {
        foreach (explode("\\n", $data) as $line) {
            if (str_starts_with($line, "data: ")) {
                $json = json_decode(substr($line, 6), true);
                if (isset($json["text"]) && !isset($json["answer"])) {
                    echo $json["text"];
                    flush();
                } elseif (isset($json["answer"])) {
                    echo "\\nDone: " . $json["answer"] . "\\n";
                }
            }
        }
        return strlen($data);
    },
]);

curl_exec($ch);
curl_close($ch);`,
  },
  go: {
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
    stream: `package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
)

func main() {
	apiKey := "YOUR_API_KEY"

	payload, _ := json.Marshal(map[string]interface{}{
		"question": "<QUESTION>",
		"stream":   true,
	})

	req, _ := http.NewRequest("POST",
		"<URL>/projects/<PROJECT>/chat",
		bytes.NewBuffer(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()

	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "data: ") {
			var data map[string]interface{}
			json.Unmarshal([]byte(line[6:]), &data)
			if text, ok := data["text"]; ok {
				if _, hasAnswer := data["answer"]; !hasAnswer {
					fmt.Print(text)
				} else {
					fmt.Println("\\nFinal:", data["answer"])
				}
			}
		}
	}
}`,
  },
  ruby: {
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
    stream: `require "net/http"
require "json"
require "uri"

api_key = "YOUR_API_KEY"

uri = URI("<URL>/projects/<PROJECT>/chat")
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = uri.scheme == "https"

request = Net::HTTP::Post.new(uri)
request["Content-Type"] = "application/json"
request["Accept"] = "text/event-stream"
request["Authorization"] = "Bearer #{api_key}"
request.body = { question: "<QUESTION>", stream: true }.to_json

http.request(request) do |response|
  response.read_body do |chunk|
    chunk.each_line do |line|
      next unless line.start_with?("data: ")
      data = JSON.parse(line[6..])
      if data["text"] && !data.key?("answer")
        print data["text"]
        $stdout.flush
      elsif data["answer"]
        puts "\\nFinal: #{data["answer"]}"
      end
    end
  end
end`,
  },
};

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
  const chatCode = replaceVars(langSnippets.chat, project);
  const streamCode = replaceVars(langSnippets.stream, project);

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

      <Card variant="outlined" sx={{
        ...cleanCardSx,
        p: 0,
        "&:hover": { transform: "none", borderColor: "divider", boxShadow: "none" },
      }}>
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
            title="Chat"
            description="Start or continue a conversation. Omit the id on the first request; include the returned id for follow-ups so the server can resume the session and the same per-chat tool sandbox."
            endpoint={`POST /projects/${project.id || "—"}/chat`}
            method="POST"
            code={chatCode}
            icon={<ChatBubbleOutline sx={{ fontSize: 18, color: "#0e7490" }} />}
          />

          <Box sx={{ height: 1, background: "rgba(15,23,42,0.06)", my: 1 }} />

          <EndpointSection
            title="Chat (Streaming)"
            description={'Add "stream": true to receive Server-Sent Events. Partial tokens arrive as data: {"text": "..."} lines; the final line contains the full answer, sources, and metadata. The stream closes with event: close.'}
            endpoint={`POST /projects/${project.id || "—"}/chat`}
            method="POST"
            code={streamCode}
            icon={<Stream sx={{ fontSize: 18, color: "#0e7490" }} />}
          />
        </Box>
      </Card>
    </Container>
  );
}
