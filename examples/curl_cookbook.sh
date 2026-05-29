#!/usr/bin/env bash
#
# RESTai API cookbook — the whole lifecycle as annotated curl commands.
#
# Walks through: discover models → ensure a team → create a RAG project → ingest
# → ask → search → classify → direct (OpenAI-compatible) call → cleanup.
#
# Requires: curl, jq.  Config via env (defaults target local dev):
#   RESTAI_URL      default http://localhost:9000
#   RESTAI_API_KEY  Bearer key (preferred). If unset, uses Basic auth below.
#   RESTAI_USER     default admin
#   RESTAI_PASSWORD default admin
#
#   ./curl_cookbook.sh
#
set -euo pipefail

BASE="${RESTAI_URL:-http://localhost:9000}"
command -v jq >/dev/null || { echo "This script needs 'jq' (https://jqlang.github.io/jq/)."; exit 1; }

# Build the auth args once. Prefer a Bearer API key; fall back to Basic.
if [[ -n "${RESTAI_API_KEY:-}" ]]; then
  AUTH=(-H "Authorization: Bearer ${RESTAI_API_KEY}")
else
  AUTH=(-u "${RESTAI_USER:-admin}:${RESTAI_PASSWORD:-admin}")
fi

# api METHOD PATH [JSON_BODY] — curl wrapper that fails on HTTP errors.
api() {
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -fsS -X "$method" "${BASE}${path}" "${AUTH[@]}" \
      -H 'Content-Type: application/json' -d "$body"
  else
    curl -fsS -X "$method" "${BASE}${path}" "${AUTH[@]}"
  fi
}

echo "→ RESTai at ${BASE}"

# 1. Discover models. RESTai ships with none configured — add them in /admin.
LLM=$(api GET /llms | jq -r '.[0].name // empty')
EMB=$(api GET /embeddings | jq -r '.[0].name // empty')
[[ -n "$LLM" && -n "$EMB" ]] || { echo "Configure an LLM + embeddings in /admin first."; exit 1; }
echo "→ using LLM '$LLM' and embeddings '$EMB'"

# 2. Ensure a team that can use those models (projects belong to a team).
TEAM_ID=$(api GET /teams | jq -r '.teams[] | select(.name=="examples") | .id' | head -n1)
if [[ -z "$TEAM_ID" ]]; then
  # Passing llms/embeddings name lists grants access as part of creation.
  TEAM_ID=$(api POST /teams "$(jq -n --arg l "$LLM" --arg e "$EMB" \
    '{name:"examples", description:"RESTai examples", llms:[$l], embeddings:[$e]}')" | jq -r '.id')
fi
echo "→ team id ${TEAM_ID}"

# 3. Create a RAG project (note: returns {"project": <id>}).
PROJECT_ID=$(api POST /projects "$(jq -n --arg l "$LLM" --arg e "$EMB" --argjson t "$TEAM_ID" \
  '{name:"examples_curl", type:"rag", llm:$l, embeddings:$e, vectorstore:"chroma", team_id:$t}')" \
  | jq -r '.project')
echo "→ project id ${PROJECT_ID}"

# 4. Ingest some text into the knowledge base.
api POST "/projects/${PROJECT_ID}/embeddings/ingest/text" \
  '{"text":"The meaning of life, the universe, and everything is 42.","source":"meaning-of-life"}' \
  | jq -c '{source, documents, chunks}'

# 5. Ask a grounded question (note the integer id and the /chat endpoint).
echo "── chat ────────────────────────────────────────────"
api POST "/projects/${PROJECT_ID}/chat" \
  '{"question":"What is the meaning of life?","k":2,"score":0.0}' \
  | jq -r '"A: " + .answer + "\n   (\(.sources | length) source chunk(s))"'

# 6. Pure semantic search (no LLM call).
echo "── search ──────────────────────────────────────────"
api POST "/projects/${PROJECT_ID}/embeddings/search" \
  '{"text":"meaning of life","k":2}' | jq -c '.embeddings'

# 7. Zero-shot classifier (a standalone tool — no project needed).
echo "── classify ────────────────────────────────────────"
api POST /tools/classifier \
  '{"sequence":"I was double charged on my invoice","labels":["billing","technical","general"]}' \
  | jq -c '{top: .labels[0], scores: ([.labels, .scores] | transpose | map({(.[0]): .[1]}))}'

# 8. Direct access — OpenAI-compatible, no project required.
echo "── /v1/chat/completions ────────────────────────────"
api POST /v1/chat/completions "$(jq -n --arg m "$LLM" \
  '{model:$m, messages:[{role:"user", content:"Say hi in one short sentence."}]}')" \
  | jq -r '.choices[0].message.content'

# 9. Cleanup (set KEEP=1 to keep the project for inspection).
if [[ "${KEEP:-}" != "1" ]]; then
  api DELETE "/projects/${PROJECT_ID}" >/dev/null
  echo "→ deleted project ${PROJECT_ID} (set KEEP=1 to keep it)"
fi
